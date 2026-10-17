import gzip
import json
import sqlite3
import sys
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.database import connection, migrate


def transfer():
    migrate()
    source = sqlite3.connect(f"file:{settings.data_dir / 'corpus.sqlite3'}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    with connection() as conn:
        if conn.execute("SELECT count(*) AS n FROM legacy_documents").fetchone()["n"] == 0:
            with conn.cursor().copy("COPY legacy_documents(id,title,metadata,payload) FROM STDIN") as copy:
                for row in source.execute("SELECT id,title,metadata_json,payload FROM documents"):
                    payload = row["payload"]
                    if isinstance(payload, str):
                        payload = gzip.compress(payload.encode())
                    copy.write_row((row["id"], row["title"], Jsonb(json.loads(row["metadata_json"])), payload))
            print("Imported documents", flush=True)
            with conn.cursor().copy("COPY legacy_sections(id,document_id,title,start_offset,end_offset,payload) FROM STDIN") as copy:
                for row in source.execute("SELECT * FROM sections"):
                    copy.write_row((row["id"], row["document_id"], row["title"], row["start_offset"], row["end_offset"], Jsonb(json.loads(row["metadata_json"]))))
            print("Imported sections", flush=True)
            conn.execute("DROP INDEX IF EXISTS legacy_chunks_bm25")
            titles = dict(source.execute("SELECT id,title FROM documents"))
            with conn.cursor().copy("COPY legacy_chunks(id,document_id,section_id,start_offset,text,document_title,section_title,payload) FROM STDIN") as copy:
                for row in source.execute("SELECT * FROM chunks"):
                    payload = json.loads(row["payload"])
                    copy.write_row((row["id"], row["document_id"], row["section_id"], row["start_offset"], row["text"], titles[row["document_id"]], payload.get("sectionTitle", ""), Jsonb(payload)))
            print("Imported chunks; building BM25 index", flush=True)
            conn.execute("CREATE INDEX legacy_chunks_bm25 ON legacy_chunks USING bm25(id,text,document_title,section_title) WITH(key_field='id')")
        catalog = json.loads((settings.data_dir / "corpus.json").read_text(encoding="utf-8"))
        catalog.pop("documents", None)
        conn.execute("INSERT INTO catalog_metadata(id,payload) VALUES('legacy',%s) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (Jsonb(catalog),))
        layout = settings.data_dir / "graph-layout.sqlite"
        if layout.exists():
            old = sqlite3.connect(f"file:{layout}?mode=ro", uri=True)
            old.row_factory = sqlite3.Row
            for table, mode, kind in [("network_document_positions", "network", "document"), ("network_entity_positions", "network", "entity"), ("document_positions", "grouped", "document"), ("entity_positions", "grouped", "entity")]:
                for row in old.execute(f"SELECT * FROM {table}"):
                    row = dict(row)
                    conn.execute("INSERT INTO layout_positions(mode,kind,id,slot,x,y,label,entity_type) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (mode, kind, row["id"], row.get("slot"), row["x"], row["y"], row.get("label"), row.get("kind")))
        runs = settings.data_dir / "runs.sqlite"
        if runs.exists():
            old = sqlite3.connect(f"file:{runs}?mode=ro", uri=True)
            for row in old.execute("SELECT id,created_at,payload FROM runs"):
                conn.execute("INSERT INTO api_runs(id,created_at,payload) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (row[0], row[1], Jsonb(json.loads(row[2]))))
    print("Legacy import committed; runtime uses Postgres only", flush=True)


if __name__ == "__main__":
    transfer()
