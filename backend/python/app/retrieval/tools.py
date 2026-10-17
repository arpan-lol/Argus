import json
from collections import deque

from .session import BudgetReached


def search_sources(session, args):
    limit = args.limit
    candidates = min(90, limit * 3)
    ranked = {}
    failures = []
    if args.mode in ("lexical", "hybrid"):
        try:
            rows = session.sql("SELECT c.id,paradedb.score(c.id) AS score FROM published_chunks c JOIN ingestion_publications p ON p.source_id=c.document_id AND p.active JOIN ingestion_jobs j ON j.id=p.job_id WHERE c.id @@@ paradedb.match('text',%s) AND j.id=ANY(%s) AND c.payload->>'revisionId'=j.revision AND c.payload->>'processingVersion'=j.processing_version AND (%s::text IS NULL OR c.document_id=%s) ORDER BY score DESC,c.id LIMIT %s", (args.query, session.jobs, args.document_id, args.document_id, candidates), "published BM25")
            ranked["bm25"] = [(row["id"], row["score"]) for row in rows]
        except Exception:
            if args.mode == "lexical":
                raise
            failures.append("BM25 retrieval unavailable")
    if args.mode in ("vector", "hybrid"):
        try:
            vector = session.query_vector(args.query)
            rows = session.cypher("CALL db.idx.vector.queryNodes('Chunk','embedding',$cap,vecf32($vector)) YIELD node,score WHERE node.active=true AND node.jobId IN $jobs AND ($document IS NULL OR node.documentId=$document) RETURN node.id,score ORDER BY score ASC,node.id LIMIT $limit", {"vector": vector, "cap": session.limits["annCandidates"], "document": args.document_id, "limit": candidates}, "published vector seeds")
            ranked["cosine_distance"] = [(row[0], row[1]) for row in rows]
            session.warnings.append("ANN searches at most 240 indexed candidates before publication/document filtering; returned neighbors can be underfilled and are not exhaustive.")
        except BudgetReached:
            raise
        except Exception:
            if args.mode == "vector":
                raise
            failures.append("Vector retrieval unavailable; hybrid ranking contains lexical results only")
    fused = {}
    if not ranked:
        raise RuntimeError("No requested retrieval channel is available")
    for channel, rows in ranked.items():
        for rank, (chunk_id, score) in enumerate(rows, 1):
            item = fused.setdefault(chunk_id, {"id": chunk_id, "score": 0, "signals": []})
            item["score"] += 1 / (60 + rank)
            item["signals"].append({"channel": channel, "rank": rank, "score": score, "interpretation": "lower distance is nearer" if channel == "cosine_distance" else "higher BM25 is more relevant"})
    ordered = sorted(fused.values(), key=lambda row: (-row["score"], row["id"]))[:limit]
    supported = session.chunks([item["id"] for item in ordered])
    items = [{**session.excerpt(supported[item["id"]]), "score": item["score"], "scoreType": "reciprocal_rank_fusion", "rank": rank, "signals": item["signals"]} for rank, item in enumerate(ordered, 1) if item["id"] in supported]
    session.warnings.extend(failures)
    return {"items": items, "ranking": {"algorithm": "RRF", "constant": 60, "candidateLimitPerChannel": candidates, "scoreMeaning": "Rank-fusion relevance, not confidence or scientific support strength"}, "requestedMode": args.mode, "availableChannels": list(ranked), "partial": bool(failures)}


def find_entities(session, args):
    rows = session.cypher("MATCH (c:Chunk)-[:HAS_MENTION]->(m:Mention)-[:RESOLVED_TO]->(e:Entity) WHERE c.active=true AND m.active=true AND c.jobId IN $jobs AND m.jobId=c.jobId AND (toLower(e.label) CONTAINS toLower($query) OR toLower(m.text) CONTAINS toLower($query)) RETURN DISTINCT e.id,e.label ORDER BY e.label,e.id LIMIT $limit", {"query": args.query, "limit": args.limit + 1}, "published entity names")
    if len(rows) > args.limit:
        session.truncate("Entity lookup result limit reached; refine the name")
    items = []
    for row in rows[:args.limit]:
        entity = session.entity(row[0])
        if entity:
            items.append(entity)
    return {"items": items, "ambiguous": len(items) > 1, "matchMeaning": "Literal canonical name/current source mention lookup; historical aliases are not searched. Multiple matches are not automatically resolved"}


def read_chunks(session, args):
    rows = session.chunks(args.chunk_ids)
    items = []
    for chunk_id in dict.fromkeys(args.chunk_ids):
        if chunk_id not in rows:
            continue
        entities = session.cypher("MATCH (c:Chunk {id:$chunk})-[:MENTIONS]->(e:Entity) WHERE c.active=true AND c.jobId IN $jobs RETURN e.id,e.label,e.type ORDER BY e.label,e.id LIMIT 41", {"chunk": chunk_id}, "chunk entities")
        if len(entities) > 40:
            session.truncate("Chunk entity list capped at 40")
        items.append({**session.excerpt(rows[chunk_id]), "entities": [{"id": row[0], "name": row[1], "type": row[2]} for row in entities[:40]]})
    return {"items": items, "unknownChunkIds": [key for key in args.chunk_ids if key not in rows], "connectionMeaning": "Chunk mentions an entity; this alone does not assert a semantic relationship"}


def assertion_rows(session, entity_id, direction="both", predicates=None, polarity=None, limit=20):
    rows = session.cypher("MATCH (s:Entity)<-[:SUBJECT]-(a:Assertion)-[:OBJECT]->(o:Entity),(a)-[:SUPPORTED_BY]->(c:Chunk) WHERE a.active=true AND c.active=true AND a.jobId IN $jobs AND c.jobId=a.jobId AND (($direction='outgoing' AND s.id=$entity) OR ($direction='incoming' AND o.id=$entity) OR ($direction='both' AND (s.id=$entity OR o.id=$entity))) AND (size($predicates)=0 OR a.predicate IN $predicates) AND ($polarity IS NULL OR a.polarity=$polarity) RETURN a.id,a.jobId,a.predicate,a.polarity,a.conditions,a.quote,a.startOffset,a.endOffset,c.id,s.id,s.label,o.id,o.label ORDER BY a.id LIMIT $limit", {"entity": entity_id, "direction": direction, "predicates": predicates or [], "polarity": polarity, "limit": limit + 1}, "assertion adjacency")
    if len(rows) > limit:
        session.truncate("Assertion fanout/result limit reached; traversal is incomplete")
    return supported_assertions(session, rows[:limit])


def supported_assertions(session, rows):
    support = session.chunks([row[8] for row in rows])
    assertions = []
    for row in rows:
        chunk = support.get(row[8])
        if not chunk or chunk["job_id"] != row[1]:
            continue
        text = chunk["payload"]["text"]
        relative = row[6] - chunk["payload"]["startOffset"]
        if relative < 0 or row[7] > chunk["payload"]["endOffset"] or row[7] - row[6] != len(row[5]) or text[relative:relative + row[7] - row[6]] != row[5]:
            session.warnings.append("Assertion with inconsistent source support withheld")
            continue
        assertions.append({"id": row[0], "predicate": row[2], "polarity": row[3], "conditions": json.loads(row[4] or "[]"), "quote": row[5], "subject": {"id": row[9], "name": row[10]}, "object": {"id": row[11], "name": row[12]}, "citation": session.citation(chunk, row[6], row[7])})
    return assertions


def inspect_assertions(session, args):
    entity = session.entity(args.entity_id)
    if not entity:
        return {"items": [], "unknownEntityIds": [args.entity_id]}
    return {"entity": entity, "items": assertion_rows(session, args.entity_id, predicates=[args.predicate] if args.predicate else [], polarity=args.polarity, limit=args.limit), "interpretation": "Reported assertions retain uncertainty/negation; source grounding is not independent scientific validation"}


def traverse(session, roots, depth, direction, predicates, edge_limit, target=None, path_limit=3):
    known = {}
    unknown = []
    for entity_id in dict.fromkeys(roots + ([target] if target else [])):
        entity = session.entity(entity_id)
        if entity is None:
            unknown.append(entity_id)
        else:
            known[entity_id] = entity
    if unknown:
        return {"items": [], "paths": [], "unknownEntityIds": unknown}
    if target and target in roots:
        return {"items": [], "paths": [{"entities": [target], "hops": [], "hopCount": 0}], "entities": list(known.values())}
    queue = deque((root, 0) for root in roots)
    distance = {root: 0 for root in roots}
    adjacency = {}
    edges = {}
    tree = []
    found_depth = None
    try:
        while queue:
            current, level = queue.popleft()
            if level >= depth or (found_depth is not None and level >= found_depth):
                continue
            assertions = assertion_rows(session, current, direction, predicates, limit=session.limits["fanout"])
            adjacency[current] = []
            for assertion in assertions:
                neighbor = assertion["object"]["id"] if assertion["subject"]["id"] == current else assertion["subject"]["id"]
                if neighbor not in distance and len(distance) >= session.limits["frontier"]:
                    session.truncate("Traversal entity budget reached")
                    continue
                if assertion["id"] not in edges and len(edges) >= edge_limit:
                    session.truncate("Traversal assertion budget reached")
                    break
                edges[assertion["id"]] = assertion
                hop = {"from": current, "to": neighbor, "assertionId": assertion["id"], "traversedForward": assertion["subject"]["id"] == current}
                adjacency[current].append(hop)
                if neighbor not in distance:
                    distance[neighbor] = level + 1
                    queue.append((neighbor, level + 1))
                    tree.append(hop)
                if target == neighbor:
                    found_depth = level + 1
            if len(edges) >= edge_limit:
                session.truncate("Traversal assertion budget reached")
                break
    except BudgetReached:
        pass
    paths = []
    if target and found_depth is not None:
        stack = [(root, [root], []) for root in roots]
        while stack and len(paths) < path_limit:
            node, entities, hops = stack.pop()
            if node == target:
                paths.append({"entities": entities, "hops": hops, "hopCount": len(hops)})
                continue
            for hop in reversed(adjacency.get(node, [])):
                if hop["to"] not in entities and distance.get(hop["to"]) == distance[node] + 1:
                    stack.append((hop["to"], [*entities, hop["to"]], [*hops, hop]))
        if stack:
            session.truncate("Returned path count capped")
    return {"items": list(edges.values()), "paths": paths, "discoveryTree": tree, "depthByEntity": distance, "searchDepth": depth, "direction": direction, "pathMeaning": "Paths compose reported assertions for inspection, not a newly established causal/scientific conclusion. Negated or uncertain assertions remain labeled.", "coverage": "Bounded search only; no-path does not prove absence of a connection"}


def expand_connections(session, args):
    return traverse(session, list(dict.fromkeys(args.entity_ids)), args.depth, args.direction, args.predicates, args.limit)


def find_paths(session, args):
    return traverse(session, [args.source_entity_id], args.max_depth, args.direction, args.predicates, 100, args.target_entity_id, args.limit)


from .research import rank_entities, recent_source_updates, source_authors
