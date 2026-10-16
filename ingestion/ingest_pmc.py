import argparse
import gzip
import os
import shutil
import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
QUERIES = {
    "materials_remediation": '(adsor*[Title/Abstract] AND (water[Title/Abstract] OR wastewater[Title/Abstract] OR pollutant*[Title/Abstract])) AND open access[filter]',
    "catalysis": 'catalys*[Title/Abstract] AND open access[filter]',
}
TERMS = {
    "material": ["activated carbon", "biochar", "metal-organic framework", "metal organic framework", "zeolite", "graphene", "chitosan", "hydrogel", "bentonite", "nanocomposite", "cellulose", "silica", "magnetic nanoparticles"],
    "pollutant": ["methylene blue", "methyl orange", "rhodamine b", "tetracycline", "ciprofloxacin", "lead", "cadmium", "arsenic", "chromium", "copper", "mercury", "bisphenol a", "phenol", "fluoride", "nitrate", "phosphate"],
    "condition": ["pH", "temperature", "contact time", "initial concentration", "ionic strength", "competing ions", "regeneration", "desorption", "reusability"],
    "method": ["adsorption", "photocatalysis", "isotherm", "kinetics", "Langmuir", "Freundlich", "pseudo-second-order"],
}
PATTERNS = [(kind, term, re.compile(r"(?<!\w)" + re.escape(term) + r"s?(?!\w)", re.I)) for kind, terms in TERMS.items() for term in terms]


def now():
    return datetime.now(timezone.utc).isoformat()


def compact(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Client:
    def __init__(self):
        self.last = 0.0

    def get(self, endpoint, **parameters):
        url = BASE + endpoint + "?" + urllib.parse.urlencode({"db": "pmc", "tool": "FalkorEvidenceWorkspace", **parameters})
        for attempt in range(6):
            time.sleep(max(0, 0.4 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "FalkorEvidenceWorkspace/0.1 (noncommercial evidence research)"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read(), url
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 5:
                    raise
                time.sleep(min(30, 2 ** (attempt + 1)))


def discover(client, directory, key, refresh=False):
    target = directory / f"{key}.json"
    if target.exists() and not refresh:
        return json.loads(target.read_text(encoding="utf-8"))
    ids = []
    raw, first_url = client.get("esearch.fcgi", term=QUERIES[key], retmode="json", retmax=0)
    total = int(json.loads(raw)["esearchresult"]["count"])
    partitions = []

    def fetch_partition(low, high):
        query = QUERIES[key] + f' AND ({low}:{high}[UID])'
        raw, url = client.get("esearch.fcgi", term=query, retmode="json", retmax=9999)
        result = json.loads(raw)["esearchresult"]
        count = int(result["count"])
        if count > 9000 and low < high:
            middle = (low + high) // 2
            fetch_partition(low, middle)
            fetch_partition(middle + 1, high)
            return
        partition_ids = ["PMC" + item for item in result.get("idlist", [])]
        ids.extend(partition_ids)
        partitions.append({"fromUid": low, "toUid": high, "count": count, "discovered": len(partition_ids), "sourceUrl": url})
        print(f"discovery {key}: {len(set(ids))}/{total}", flush=True)

    fetch_partition(1, 20000000)
    manifest = {"key": key, "query": QUERIES[key], "count": total, "discovered": len(set(ids)), "pmcids": list(dict.fromkeys(ids)), "sourceUrl": first_url, "observedAt": now(), "complete": len(set(ids)) == total, "partitions": partitions, "partitionMethod": "disjoint PMC UID ranges"}
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def decode_payload(value):
    return json.loads(gzip.decompress(value).decode("utf-8") if isinstance(value, bytes) else value)


def migrate_storage(directory):
    raw_directory = (directory / "raw").resolve()
    for source in raw_directory.glob("*.xml"):
        retained = source.read_bytes()
        compressed = gzip.compress(retained, compresslevel=6, mtime=0)
        target = source.with_suffix(".xml.gz")
        temporary = target.with_suffix(".gz.tmp")
        temporary.write_bytes(compressed)
        if hashlib.sha256(gzip.decompress(temporary.read_bytes())).digest() != hashlib.sha256(retained).digest():
            raise ValueError(f"raw compression verification failed: {source.name}")
        temporary.replace(target)
        if source.resolve().parent != raw_directory:
            raise ValueError("raw migration source escapes raw directory")
        source.unlink()
    database = directory / "corpus.sqlite3"
    if not database.exists():
        return
    connection = sqlite3.connect(database, timeout=60)
    ids = [row[0] for row in connection.execute("SELECT id FROM documents")]
    for offset in range(0, len(ids), 25):
        with connection:
            for ident in ids[offset:offset + 25]:
                payload, metadata = connection.execute("SELECT payload,metadata_json FROM documents WHERE id=?", (ident,)).fetchone()
                doc = decode_payload(payload)
                meta = json.loads(metadata)
                if doc["rawPath"].endswith(".xml"):
                    doc["rawPath"] += ".gz"
                    meta["rawPath"] = doc["rawPath"]
                doc["textLength"] = len(doc["text"])
                meta["textLength"] = len(doc["text"])
                compressed = gzip.compress(json.dumps(doc, ensure_ascii=False).encode("utf-8"), compresslevel=6, mtime=0)
                connection.execute("UPDATE documents SET payload=?,metadata_json=?,text=NULL WHERE id=?", (compressed, json.dumps(meta, ensure_ascii=False), ident))
        if offset % 250 == 0:
            connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
            print(f"storage migration {min(offset + 25, len(ids))}/{len(ids)}", flush=True)
    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    connection.close()
    print(json.dumps({"storageMigration": "complete", "documents": len(ids), "checkpoint": checkpoint}), flush=True)


def parse_article(article, raw, raw_path):
    meta = article.find("./front/article-meta")
    if meta is None:
        raise ValueError("article metadata unavailable")
    identifiers = {node.get("pub-id-type"): compact(node) for node in meta.findall("article-id")}
    pmcid = identifiers.get("pmcid") or identifiers.get("pmc")
    if not pmcid:
        raise ValueError("PMCID missing")
    if not pmcid.startswith("PMC"):
        pmcid = "PMC" + pmcid
    revision = hashlib.sha256(raw).hexdigest()
    sections = []
    parts = []
    position = 0

    def section(title, parent=None):
        sid = f"{pmcid}:s{len(sections) + 1}"
        result = {"id": sid, "title": title, "ordinal": len(sections) + 1, "parentId": parent, "startOffset": position, "endOffset": position, "locationKind": "section"}
        sections.append(result)
        return result

    def append(value):
        nonlocal position
        value = " ".join(value.split())
        if not value:
            return
        if parts:
            position += 2
        parts.append(value)
        position += len(value)

    def visit(element, current):
        for child in element:
            tag = child.tag.split("}")[-1]
            if tag == "sec":
                nested = section(compact(child.find("title")) or "Untitled section", current["id"])
                visit(child, nested)
                nested["endOffset"] = position
            elif tag in ("p", "table-wrap", "fig", "disp-quote", "list", "disp-formula"):
                append(compact(child))
            elif tag not in ("title", "label", "ref-list", "supplementary-material"):
                visit(child, current)
        current["endOffset"] = position

    abstract = meta.find("abstract")
    if abstract is not None:
        abstract_section = section("Abstract")
        visit(abstract, abstract_section)
    body = article.find("body")
    if body is None:
        raise ValueError("full text body unavailable")
    body_section = section("Article body")
    visit(body, body_section)
    text = "\n\n".join(parts)
    if len(text) < 300:
        raise ValueError("full text below minimum usable length")
    leaves = sorted([item for item in sections if not any(other["parentId"] == item["id"] for other in sections)], key=lambda item: item["startOffset"])
    boundaries = sorted(set([0, len(text)] + [item["startOffset"] for item in leaves] + [item["endOffset"] for item in leaves]))
    chunks = []
    for left, right in zip(boundaries, boundaries[1:]):
        start = left
        while start < right:
            while start < right and text[start].isspace():
                start += 1
            if start >= right:
                break
            end = min(start + 1400, right)
            if end < right:
                candidate = text.rfind(" ", start + 700, end)
                if candidate > start:
                    end = candidate
            while end > start and text[end - 1].isspace():
                end -= 1
            owners = [item for item in sections if item["startOffset"] <= start < item["endOffset"]]
            owner = max(owners, key=lambda item: item["ordinal"]) if owners else body_section
            cid = f"{pmcid}:{revision[:12]}:c{len(chunks) + 1}"
            chunks.append({"id": cid, "documentId": pmcid, "revisionId": revision, "sectionId": owner["id"], "sectionTitle": owner["title"], "ordinal": len(chunks) + 1, "text": text[start:end], "startOffset": start, "endOffset": end, "sourceUrl": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/", "locationKind": "section"})
            start = end
    entities = []
    for kind, term, pattern in PATTERNS:
        mentions = []
        for chunk in chunks:
            for match in pattern.finditer(chunk["text"]):
                mentions.append({"chunkId": chunk["id"], "startOffset": chunk["startOffset"] + match.start(), "endOffset": chunk["startOffset"] + match.end(), "text": match.group()})
        if mentions:
            slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
            entities.append({"id": f"ent:{kind}:{slug}", "label": term, "type": kind, "extractionMethod": "dictionary_exact_mention", "mentions": mentions})
    authors = []
    for contributor in meta.findall("./contrib-group/contrib"):
        if contributor.get("contrib-type", "author") != "author":
            continue
        name = contributor.find("name")
        label = " ".join(filter(None, [compact(name.find("given-names")), compact(name.find("surname"))])) if name is not None else compact(contributor.find("collab"))
        if label:
            authors.append(label)
    license_element = meta.find("./permissions/license")
    license_url = next((value for key, value in license_element.attrib.items() if key.endswith("href")), None) if license_element is not None else None
    return {"id": pmcid, "revisionId": revision, "pmcid": pmcid, "title": compact(meta.find("./title-group/article-title")), "authors": authors, "doi": identifiers.get("doi"), "journal": compact(article.find("./front/journal-meta/journal-title-group/journal-title")), "year": compact(meta.find("./pub-date/year")), "license": compact(license_element), "licenseUrl": license_url, "sourceUrl": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/", "fullTextUrl": BASE + "efetch.fcgi?db=pmc&id=" + pmcid[3:], "rawPath": str(raw_path.relative_to(ROOT)).replace("\\", "/"), "text": text, "sections": sections, "chunks": chunks, "entities": entities, "parsedAt": now(), "offsetUnit": "unicode_codepoint", "textNormalization": "XML itertext; whitespace collapsed within blocks; blocks joined with two newlines; Unicode code-point offsets into this text", "extractionBoundary": "Dictionary mentions are not verified material-property claims. Tables flattened to text; no PDF pagination or supplements."}


def publish(directory, documents, discovery, ledger, target=None):
    connection = sqlite3.connect(directory / "corpus.sqlite3", timeout=60)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, revision_id TEXT, title TEXT, text TEXT, metadata_json TEXT, payload TEXT); CREATE TABLE IF NOT EXISTS sections(id TEXT PRIMARY KEY, document_id TEXT, title TEXT, start_offset INTEGER, end_offset INTEGER, metadata_json TEXT); CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, document_id TEXT, section_id TEXT, text TEXT, start_offset INTEGER, end_offset INTEGER, payload TEXT); CREATE TABLE IF NOT EXISTS ingestion_ledger(pmcid TEXT PRIMARY KEY, status TEXT, detail_json TEXT); CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED,text,title,section_title); CREATE INDEX IF NOT EXISTS sections_document_id ON sections(document_id); CREATE INDEX IF NOT EXISTS chunks_document_id ON chunks(document_id); CREATE INDEX IF NOT EXISTS chunks_section_id ON chunks(section_id); CREATE INDEX IF NOT EXISTS documents_pmcid_order ON documents(CAST(substr(id,4) AS INTEGER) DESC);")
    with connection:
        for doc in documents.values():
            metadata = {key: value for key, value in doc.items() if key not in ("text", "chunks", "sections")}
            previous = connection.execute("SELECT revision_id FROM documents WHERE id=?", (doc["id"],)).fetchone()
            if previous and previous[0] == doc["revisionId"]:
                continue
            connection.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?)", (doc["id"], doc["revisionId"], doc["title"], None, json.dumps(metadata, ensure_ascii=False), gzip.compress(json.dumps(doc, ensure_ascii=False).encode("utf-8"), compresslevel=6, mtime=0)))
            old_ids = connection.execute("SELECT id FROM chunks WHERE document_id=?", (doc["id"],)).fetchall()
            connection.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", old_ids)
            connection.execute("DELETE FROM chunks WHERE document_id=?", (doc["id"],))
            connection.execute("DELETE FROM sections WHERE document_id=?", (doc["id"],))
            connection.executemany("INSERT INTO sections VALUES(?,?,?,?,?,?)", [(section["id"], doc["id"], section["title"], section["startOffset"], section["endOffset"], json.dumps(section)) for section in doc["sections"]])
            connection.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)", [(chunk["id"], doc["id"], chunk["sectionId"], chunk["text"], chunk["startOffset"], chunk["endOffset"], json.dumps(chunk, ensure_ascii=False)) for chunk in doc["chunks"]])
            connection.executemany("INSERT INTO chunks_fts VALUES(?,?,?,?)", [(chunk["id"], chunk["text"], doc["title"], chunk["sectionTitle"]) for chunk in doc["chunks"]])
        connection.executemany("INSERT OR REPLACE INTO ingestion_ledger VALUES(?,?,?)", [(pmcid, entry["status"], json.dumps(entry)) for pmcid, entry in ledger.items()])
    counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("documents", "sections", "chunks")}
    entity_ids = set()
    mentions = 0
    for (metadata,) in connection.execute("SELECT metadata_json FROM documents"):
        for entity in json.loads(metadata).get("entities", []):
            entity_ids.add(entity["id"])
            mentions += len(entity["mentions"])
    counts.update({"entities": len(entity_ids), "entityMentions": mentions})
    visible = [decode_payload(row[0]) for row in connection.execute("SELECT payload FROM documents ORDER BY CAST(substr(id,4) AS INTEGER) DESC LIMIT 150")]
    connection.close()
    ingestion = {"downloaded": sum(item["status"] in ("parsed", "parse_failed") for item in ledger.values()), "parsed": counts["documents"], "failed": sum(item["status"] != "parsed" for item in ledger.values()), "attempted": len(ledger), "pending": max(0, discovery[0]["discovered"] - counts["documents"]), "catalogPreviewDocuments": len(visible), "searchStore": "corpus.sqlite3", "runningTarget": target}
    catalog = {"schemaVersion": 1, "collection": "materials-remediation", "updatedAt": now(), "discovery": {"queries": discovery}, "documents": visible, "ingestion": ingestion, "tableCounts": counts, "offsetUnit": "unicode_codepoint"}
    temporary = directory / "corpus.json.tmp"
    temporary.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    temporary.replace(directory / "corpus.json")
    (directory / "ledger.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"tableCounts": counts, "ingestion": ingestion}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--refresh-discovery", action="store_true")
    parser.add_argument("--skip-catalysis", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--migrate-storage", action="store_true")
    parser.add_argument("--minimum-free-mb", type=int, default=750)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    (directory / "raw").mkdir(parents=True, exist_ok=True)
    (directory / "discovery").mkdir(exist_ok=True)
    if args.migrate_storage:
        migrate_storage(directory)
    client = Client()
    discovery = [discover(client, directory / "discovery", key, args.refresh_discovery) for key in QUERIES if key != "catalysis" or not args.skip_catalysis]
    previous = json.loads((directory / "corpus.json").read_text(encoding="utf-8")) if (directory / "corpus.json").exists() else {"documents": []}
    documents = {doc["id"]: doc for doc in previous["documents"]}
    ledger = json.loads((directory / "ledger.json").read_text(encoding="utf-8")) if (directory / "ledger.json").exists() else {}
    database = directory / "corpus.sqlite3"
    parsed_ids = set(documents)
    if database.exists():
        with sqlite3.connect(database) as connection:
            parsed_ids.update(row[0] for row in connection.execute("SELECT id FROM documents"))
            ledger.update({pmcid: json.loads(detail) for pmcid, detail in connection.execute("SELECT pmcid,detail_json FROM ingestion_ledger")})
    candidates = [pmcid for pmcid in sorted(discovery[0]["pmcids"], key=lambda item: int(item[3:]), reverse=True) if pmcid not in parsed_ids and (args.retry_failed or pmcid not in ledger)]
    job = {"pid": os.getpid(), "status": "running", "target": args.limit, "startedAt": now(), "minimumFreeMb": args.minimum_free_mb}
    (directory / "ingestion-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    while len(parsed_ids) < args.limit and candidates:
        free_bytes = shutil.disk_usage(directory).free
        if free_bytes < args.minimum_free_mb * 1024 * 1024:
            job.update({"status": "paused_disk_space", "updatedAt": now(), "parsed": len(parsed_ids), "freeBytes": free_bytes, "reason": f"Free disk below {args.minimum_free_mb} MiB safety floor; target not complete"})
            (directory / "ingestion-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
            print(json.dumps(job), flush=True)
            break
        documents = {}
        batch = candidates[:min(args.batch_size, args.limit - len(parsed_ids))]
        candidates = candidates[len(batch):]
        batch_set = set(batch)
        try:
            raw, url = client.get("efetch.fcgi", id=",".join(pmcid[3:] for pmcid in batch))
            root = ET.fromstring(raw)
            articles = [root] if root.tag == "article" else root.findall(".//article")
            seen = set()
            for article in articles:
                article_raw = ET.tostring(article, encoding="utf-8")
                identifiers = [compact(item) for item in article.findall("./front/article-meta/article-id") if item.get("pub-id-type") in ("pmc", "pmcid")]
                if not identifiers:
                    continue
                pmcid = identifiers[0] if identifiers[0].startswith("PMC") else "PMC" + identifiers[0]
                if pmcid not in batch_set:
                    continue
                seen.add(pmcid)
                raw_path = directory / "raw" / f"{pmcid}.xml.gz"
                raw_path.write_bytes(gzip.compress(article_raw, compresslevel=6, mtime=0))
                try:
                    document = parse_article(article, article_raw, raw_path)
                    documents[pmcid] = document
                    parsed_ids.add(pmcid)
                    ledger[pmcid] = {"status": "parsed", "at": now(), "bytes": len(article_raw), "sha256": document["revisionId"], "sourceUrl": url}
                except Exception as error:
                    ledger[pmcid] = {"status": "parse_failed", "at": now(), "error": str(error), "sourceUrl": url}
            for pmcid in batch_set - seen:
                ledger[pmcid] = {"status": "download_failed", "at": now(), "error": "Article absent from efetch response", "sourceUrl": url}
        except Exception as error:
            for pmcid in batch:
                ledger[pmcid] = {"status": "download_failed", "at": now(), "error": str(error)}
        publish(directory, documents, discovery, ledger, args.limit)
        job.update({"updatedAt": now(), "parsed": len(parsed_ids), "freeBytes": shutil.disk_usage(directory).free})
        (directory / "ingestion-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    publish(directory, documents, discovery, ledger, args.limit)
    if job["status"] == "running":
        job.update({"status": "complete" if len(parsed_ids) >= args.limit else "exhausted_candidates", "updatedAt": now(), "parsed": len(parsed_ids)})
        (directory / "ingestion-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
