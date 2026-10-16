import json
import sqlite3
from dataclasses import asdict
from pathlib import Path


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    def connect(self):
        return sqlite3.connect(self.path)

    def save(self, table, records):
        if table not in {"documents", "evidence", "claims"}:
            raise ValueError("Invalid collection")
        with self.connect() as db:
            db.executemany(f"INSERT INTO {table}(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", [(r.id, json.dumps(asdict(r))) for r in records])

    def records(self, table, limit=None):
        if table not in {"documents", "evidence", "claims"}:
            raise ValueError("Invalid collection")
        with self.connect() as db:
            query = f"SELECT payload FROM {table} ORDER BY id"
            params = ()
            if limit is not None:
                if not isinstance(limit, int) or limit < 1:
                    raise ValueError("Invalid inspection limit")
                query += " LIMIT ?"
                params = (limit,)
            return [json.loads(row[0]) for row in db.execute(query, params)]

    def counts(self):
        with self.connect() as db:
            return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["documents", "evidence", "claims"]}

    def event(self, run_id, event):
        with self.connect() as db:
            db.execute("INSERT INTO events(run_id,payload) VALUES (?,?)", (run_id, json.dumps(event)))

    def events(self, run_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE run_id=? ORDER BY seq", (run_id,))]

    def runs(self):
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT run_id FROM events GROUP BY run_id ORDER BY MAX(seq) DESC LIMIT 100")]
