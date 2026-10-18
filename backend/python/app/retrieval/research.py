from datetime import datetime, timedelta, timezone


def source_authors(session, args):
    jobs = [row for row in session.manifest.values() if row["source_id"] == args.document_id]
    if not jobs:
        return {"items": [], "unknownDocumentIds": [args.document_id]}
    job = jobs[0]
    rows = session.sql("SELECT d.title,d.metadata,a.payload->'metadata'->'authors' AS authors FROM published_documents d JOIN ingestion_artifacts a ON a.job_id=%s AND a.stage='normalize' WHERE d.id=%s", (job["job_id"], args.document_id), "source author metadata")
    if not rows:
        return {"items": [], "metadataStatus": "unavailable"}
    row = rows[0]
    authors = row["authors"]
    if not isinstance(authors, list) or not authors:
        return {"items": [], "metadataStatus": "not_recorded", "interpretation": "No credited authors were recorded by this source parser; this does not establish anonymous authorship."}
    if len(authors) > args.limit:
        session.truncate("Author list capped; request a higher limit for additional credited authors")
    items = []
    for index, author in enumerate(authors[:args.limit]):
        if not isinstance(author, str) or not author.strip():
            continue
        items.append({"author": author, "text": author, "citation": {"sourceKind": "metadata", "metadataField": "authors", "metadataIndex": index, "documentId": args.document_id, "documentTitle": row["title"], "sectionTitle": "Authors", "jobId": job["job_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"], "sourceUrl": row["metadata"].get("sourceUrl")}})
    return {"items": items, "metadataStatus": "recorded", "interpretation": "Credited author strings preserved from parsed source metadata. Affiliations or reference markers may be included; no contact information or availability is inferred."}


def recent_source_updates(session, args):
    if args.document_id and not any(row["source_id"] == args.document_id for row in session.manifest.values()):
        return {"items": [], "unknownDocumentIds": [args.document_id]}
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    jobs = sorted((row for row in session.manifest.values() if row["published_at"] >= since and (not args.document_id or row["source_id"] == args.document_id)), key=lambda row: (row["published_at"], row["source_id"]), reverse=True)
    if len(jobs) > args.limit:
        session.truncate("Recent source updates capped; narrow the time window or increase the limit")
    jobs = jobs[:args.limit]
    if not jobs:
        return {"items": [], "since": since.isoformat(), "asOf": now.isoformat(), "timestampMeaning": "Argus indexing time, not paper publication date; only current active publications are listed."}
    rows = session.sql("SELECT DISTINCT ON (c.document_id) c.document_id,c.id,d.title,d.metadata->>'year' AS year FROM published_chunks c JOIN published_documents d ON d.id=c.document_id WHERE c.document_id=ANY(%s) ORDER BY c.document_id,c.start_offset,c.id", ([job["source_id"] for job in jobs],), "recent publication sources")
    documents = {row["document_id"]: row for row in rows}
    chunks = session.chunks([row["id"] for row in rows])
    items = []
    for job in jobs:
        document = documents.get(job["source_id"])
        chunk = chunks.get(document["id"]) if document else None
        if chunk:
            indexed_at = job["published_at"].isoformat()
            event = {"text": indexed_at, "citation": {"sourceKind": "metadata", "metadataField": "indexedAt", "metadataIndex": 0, "documentId": job["source_id"], "documentTitle": document["title"], "sectionTitle": "Indexing date", "jobId": job["job_id"], "revisionId": job["revision"], "processingVersion": job["processing_version"]}}
            items.append({**session.excerpt(chunk), "indexedAt": indexed_at, "articleYear": document["year"], "indexingEvent": event})
    return {"items": items, "since": since.isoformat(), "asOf": now.isoformat(), "timestampMeaning": "Argus indexing time, not paper publication date; only current active publications are listed. This is not a complete revision history."}


def pagerank(assertions, node_limit=100, damping=.85, iterations=50, tolerance=1e-9):
    nodes, pairs = set(), set()
    truncated = False
    for assertion in assertions:
        pair = (assertion["subject"]["id"], assertion["object"]["id"])
        added = set(pair) - nodes
        if len(nodes) + len(added) > node_limit:
            truncated = True
            continue
        nodes.update(pair)
        pairs.add(pair)
    if not nodes:
        return {}, {"nodes": 0, "edges": 0, "iterations": 0, "converged": True, "nodeLimitReached": truncated}
    ordered = sorted(nodes)
    outgoing = {node: [] for node in ordered}
    for left, right in sorted(pairs):
        outgoing[left].append(right)
    scores = {node: 1 / len(nodes) for node in ordered}
    converged = False
    for step in range(iterations):
        dangling = sum(scores[node] for node in ordered if not outgoing[node])
        updated = {node: (1 - damping) / len(nodes) + damping * dangling / len(nodes) for node in ordered}
        for left in ordered:
            for right in outgoing[left]:
                updated[right] += damping * scores[left] / len(outgoing[left])
        error = sum(abs(updated[node] - scores[node]) for node in ordered)
        scores = updated
        if error < tolerance:
            converged = True
            break
    return scores, {"nodes": len(nodes), "edges": len(pairs), "iterations": step + 1, "converged": converged, "nodeLimitReached": truncated, "damping": damping}


def rank_entities(session, args):
    from .tools import supported_assertions, traverse
    if args.entity_id:
        projection = traverse(session, [args.entity_id], args.depth, "both", [], 200)
        if projection.get("unknownEntityIds"):
            return projection
        assertions = [row for row in projection["items"] if row["polarity"] == "affirmed"]
        scope = "Bounded neighborhood of the requested entity"
    else:
        rows = session.cypher("MATCH (s:Entity)<-[:SUBJECT]-(a:Assertion)-[:OBJECT]->(o:Entity),(a)-[:SUPPORTED_BY]->(c:Chunk) WHERE a.active=true AND c.active=true AND a.jobId IN $jobs AND c.jobId=a.jobId AND a.polarity='affirmed' RETURN a.id,a.jobId,a.predicate,a.polarity,a.conditions,a.quote,a.startOffset,a.endOffset,c.id,s.id,s.label,o.id,o.label ORDER BY a.id LIMIT 201", {}, "bounded assertion ranking projection")
        if len(rows) > 200:
            session.truncate("Ranking projection capped at 200 assertions; this is not a corpus-wide ranking")
        assertions = supported_assertions(session, rows[:200])
        scope = "Deterministic sample of up to 200 current affirmed assertions"
    scores, statistics = pagerank(assertions)
    if statistics["nodeLimitReached"]:
        session.truncate("Ranking projection capped at 100 entities")
    if not statistics["converged"]:
        session.warnings.append("PageRank iteration limit reached; scores are approximate")
    items = []
    for rank, (entity_id, score) in enumerate(sorted(scores.items(), key=lambda row: (-row[1], row[0]))[:args.limit], 1):
        entity = session.entity(entity_id)
        if not entity:
            session.warnings.append("A ranking candidate lacked a current verified source mention and was withheld")
            continue
        supporting = [row for row in assertions if row["subject"]["id"] in scores and row["object"]["id"] in scores and entity_id in (row["subject"]["id"], row["object"]["id"])]
        items.append({**entity, "rank": rank, "score": score, "supportingAssertions": supporting[:2]})
    return {"items": items, "algorithm": "PageRank", "implementation": "Bounded in-process projection of FalkorDB assertion rows; the native whole-label procedure is not used because it cannot isolate active publication jobs.", "projection": {**statistics, "scope": scope, "assertionCount": len(assertions), "nodeLimit": 100, "assertionLimit": 200}, "scoreMeaning": "Connectivity within the returned affirmed-assertion projection only; not scientific importance, confidence, evidence quality, truth or causality. Duplicate entity pairs contribute one directed edge. Negated and uncertain assertions are excluded."}
