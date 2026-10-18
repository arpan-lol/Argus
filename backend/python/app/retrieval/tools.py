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
    rows = session.cypher("MATCH (c:Chunk)-[:HAS_MENTION]->(m:Mention)-[:RESOLVED_TO]->(e:Entity) WHERE c.active=true AND m.active=true AND c.jobId IN $jobs AND m.jobId=c.jobId AND (toLower(e.label) CONTAINS toLower($query) OR toLower(m.text) CONTAINS toLower($query)) WITH DISTINCT e,CASE WHEN toLower(e.label)=toLower($query) THEN 0 ELSE 1 END AS priority ORDER BY priority,e.label,e.id LIMIT 80 OPTIONAL MATCH (e)<-[:SUBJECT|OBJECT]-(a:Assertion) WHERE a.active=true AND a.jobId IN $jobs RETURN e.id,e.label,priority,count(DISTINCT a) AS links ORDER BY priority,links DESC,e.label,e.id LIMIT $limit", {"query": args.query, "limit": args.limit + 1}, "published entity names")
    if len(rows) > args.limit:
        session.truncate("Entity lookup result limit reached; refine the name")
    items = []
    for row in rows[:args.limit]:
        entity = session.entity(row[0])
        if entity:
            items.append({**entity, "assertionLinks": row[3]})
    return {"items": items, "ambiguous": len(items) > 1, "matchMeaning": "Exact names rank first; within a name, currently published assertion links rank first. Link count is structural connectivity, not identity certainty or factual confidence. Historical aliases are not searched"}


def read_chunks(session, args):
    requested = list(dict.fromkeys(args.chunk_ids))
    rows = session.chunks(requested)
    unknown = [key for key in requested if key not in rows]
    following = session.cypher("MATCH (c:Chunk)-[:NEXT_CHUNK]->(n:Chunk) WHERE c.id IN $ids AND c.active=true AND n.active=true AND c.jobId IN $jobs AND n.jobId=c.jobId AND n.documentId=c.documentId RETURN c.id,n.id ORDER BY c.id,n.id LIMIT 11", {"ids": list(rows)}, "adjacent source context") if rows else []
    neighbors = list(dict.fromkeys(row[1] for row in following if row[1] not in requested))
    if len(neighbors) > 10 - len(requested):
        session.truncate("Adjacent source context capped at 10 total chunks")
    adjacent = neighbors[:10 - len(requested)]
    rows.update(session.chunks(adjacent) if adjacent else {})
    items = []
    for chunk_id in requested + adjacent:
        if chunk_id not in rows:
            continue
        entities = session.cypher("MATCH (c:Chunk {id:$chunk})-[:MENTIONS]->(e:Entity) WHERE c.active=true AND c.jobId IN $jobs RETURN e.id,e.label,e.type ORDER BY e.label,e.id LIMIT 41", {"chunk": chunk_id}, "chunk entities")
        if len(entities) > 40:
            session.truncate("Chunk entity list capped at 40")
        items.append({**session.excerpt(rows[chunk_id]), "entities": [{"id": row[0], "name": row[1], "type": row[2]} for row in entities[:40]]})
    return {"items": items, "unknownChunkIds": unknown, "adjacentChunkIds": [key for key in adjacent if key in rows], "connectionMeaning": "Additional chunks follow requested passages in the same published source. Adjacency and shared mentions do not assert semantic relationships."}


def assertion_rows(session, entity_id, direction="both", predicates=None, polarity=None, limit=20, include_context_review=False):
    rows = session.cypher("MATCH (s:Entity)<-[:SUBJECT]-(a:Assertion)-[:OBJECT]->(o:Entity),(a)-[:SUPPORTED_BY]->(c:Chunk) WHERE a.active=true AND c.active=true AND a.jobId IN $jobs AND c.jobId=a.jobId AND (($direction='outgoing' AND s.id=$entity) OR ($direction='incoming' AND o.id=$entity) OR ($direction='both' AND (s.id=$entity OR o.id=$entity))) AND (size($predicates)=0 OR a.predicate IN $predicates) AND ($polarity IS NULL OR a.polarity=$polarity) AND ($review OR NOT coalesce(a.traversalStatus,'legacy_unclassified') IN ['needs_context_review','revoked','deprecated']) RETURN a.id,a.jobId,a.predicate,a.polarity,a.conditions,a.quote,a.startOffset,a.endOffset,c.id,s.id,s.label,o.id,o.label,a.extractionMethod,a.confidence,a.resolution,a.llmVerified,a.polarityStatus,a.traversalStatus,a.context ORDER BY a.id LIMIT $limit", {"entity": entity_id, "direction": direction, "predicates": predicates or [], "polarity": polarity, "review": include_context_review, "limit": limit + 1}, "assertion adjacency")
    if len(rows) > limit:
        session.truncate("Assertion fanout/result limit reached; traversal is incomplete")
    return supported_assertions(session, rows[:limit])


def supported_assertions(session, rows):
    support = session.chunks([row[8] for row in rows])
    assertions = []
    seen = set()
    for row in rows:
        if row[0] in seen:
            continue
        chunk = support.get(row[8])
        if not chunk or chunk["job_id"] != row[1]:
            continue
        text = chunk["payload"]["text"]
        relative = row[6] - chunk["payload"]["startOffset"]
        if relative < 0 or row[7] > chunk["payload"]["endOffset"] or row[7] - row[6] != len(row[5]) or text[relative:relative + row[7] - row[6]] != row[5]:
            session.warnings.append("Assertion with inconsistent source support withheld")
            continue
        seen.add(row[0])
        provenance = {'method': row[13] if len(row) > 13 else None, 'score': row[14] if len(row) > 14 else None, 'resolution': row[15] if len(row) > 15 else None, 'llmVerified': row[16] is True if len(row) > 16 else False, 'polarityStatus': row[17] if len(row) > 17 else None, 'traversalStatus': row[18] if len(row) > 18 else 'legacy_unclassified', 'sourceContext': json.loads(row[19] or '{}') if len(row) > 19 else {}, 'meaning': 'Local model predictions are unverified. Native structured records describe their source fields; syntax records describe code structure, not runtime execution.'}
        assertions.append({"id": row[0], "predicate": row[2], "polarity": row[3], "conditions": json.loads(row[4] or "[]"), "quote": row[5], "subject": {"id": row[9], "name": row[10]}, "object": {"id": row[11], "name": row[12]}, "citation": session.citation(chunk, row[6], row[7]), "extraction": provenance})
    return assertions


def inspect_assertions(session, args):
    entity = session.entity(args.entity_id)
    if not entity:
        return {"items": [], "unknownEntityIds": [args.entity_id]}
    return {"entity": entity, "items": assertion_rows(session, args.entity_id, predicates=[args.predicate] if args.predicate else [], polarity=args.polarity, limit=args.limit, include_context_review=True), "interpretation": "Reported assertions retain uncertainty/negation; source grounding is not independent scientific validation"}


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
    explored = len(edges)
    if target:
        selected = {hop["assertionId"] for path in paths for hop in path["hops"]}
        edges = {identifier: assertion for identifier, assertion in edges.items() if identifier in selected}
        tree = paths[0]["hops"] if paths else []
    return {"items": list(edges.values()), "paths": paths, "discoveryTree": tree, "depthByEntity": distance, "exploredAssertionCount": explored, "searchDepth": depth, "direction": direction, "pathMeaning": "Paths compose reported assertions for inspection, not a newly established causal/scientific conclusion. Negated or uncertain assertions remain labeled.", "coverage": "Bounded search only; no-path does not prove absence of a connection"}


def expand_connections(session, args):
    return traverse(session, list(dict.fromkeys(args.entity_ids)), args.depth, args.direction, args.predicates, args.limit)


def find_paths(session, args):
    source = session.entity(args.source_entity_id)
    target = session.entity(args.target_entity_id)
    if not source or not target:
        return {"items": [], "paths": [], "unknownEntityIds": [identifier for identifier, entity in ((args.source_entity_id, source), (args.target_entity_id, target)) if not entity]}
    if args.source_entity_id == args.target_entity_id:
        return {"items": [], "paths": [{"entities": [args.source_entity_id], "hops": [], "hopCount": 0}], "searchDepth": 0}
    for depth in range(1, args.max_depth + 1):
        matches = ["MATCH (e0:Entity {id:$source})"]
        matches.extend(f"MATCH (e{index - 1})<-[:SUBJECT|OBJECT]-(a{index}:Assertion)-[:SUBJECT|OBJECT]->(e{index}:Entity)" for index in range(1, depth + 1))
        constraints = [f"e{depth}.id=$target"]
        constraints.extend(f"a{index}.active=true AND a{index}.jobId IN $jobs" for index in range(1, depth + 1))
        constraints.extend(f"a{left}.id<>a{right}.id" for left in range(1, depth + 1) for right in range(left + 1, depth + 1))
        constraints.extend(f"e{left}.id<>e{right}.id" for left in range(depth + 1) for right in range(left + 1, depth + 1))
        matches.append("WHERE " + " AND ".join(constraints))
        matches.append("RETURN [" + ",".join(f"a{index}.id" for index in range(1, depth + 1)) + "] AS assertions,[" + ",".join(f"e{index}.id" for index in range(depth + 1)) + "] AS entities LIMIT 17")
        candidates = session.cypher(" ".join(matches), {"source": args.source_entity_id, "target": args.target_entity_id}, "targeted path candidates")
        if len(candidates) > 16:
            session.truncate("Path candidate cap reached; returned paths may be incomplete")
        identifiers = list(dict.fromkeys(identifier for candidate in candidates[:16] for identifier in candidate[0]))
        if not identifiers:
            continue
        rows = session.cypher("MATCH (s:Entity)<-[:SUBJECT]-(a:Assertion)-[:OBJECT]->(o:Entity),(a)-[:SUPPORTED_BY]->(c:Chunk) WHERE a.id IN $ids AND a.active=true AND c.active=true AND a.jobId IN $jobs AND c.jobId=a.jobId RETURN a.id,a.jobId,a.predicate,a.polarity,a.conditions,a.quote,a.startOffset,a.endOffset,c.id,s.id,s.label,o.id,o.label,a.extractionMethod,a.confidence,a.resolution,a.llmVerified,a.polarityStatus,a.traversalStatus,a.context ORDER BY a.id", {"ids": identifiers}, "path assertion support")
        assertions = {item["id"]: item for item in supported_assertions(session, rows)}
        paths = []
        for assertion_ids, entity_ids in candidates[:16]:
            hops = []
            for index, assertion_id in enumerate(assertion_ids):
                assertion = assertions.get(assertion_id)
                if not assertion or (args.predicates and assertion["predicate"] not in args.predicates):
                    break
                forward = assertion["subject"]["id"] == entity_ids[index] and assertion["object"]["id"] == entity_ids[index + 1]
                backward = assertion["object"]["id"] == entity_ids[index] and assertion["subject"]["id"] == entity_ids[index + 1]
                if not (forward or backward) or args.direction == "outgoing" and not forward or args.direction == "incoming" and not backward:
                    break
                if assertion["extraction"].get("traversalStatus") in ("needs_context_review", "revoked", "deprecated"):
                    break
                hops.append({"from": entity_ids[index], "to": entity_ids[index + 1], "assertionId": assertion_id, "traversedForward": forward})
            if len(hops) == depth:
                paths.append({"entities": entity_ids, "hops": hops, "hopCount": depth})
            if len(paths) >= args.limit:
                break
        if paths:
            chosen = {hop["assertionId"] for path in paths for hop in path["hops"]}
            return {"items": [assertions[identifier] for identifier in chosen], "paths": paths, "discoveryTree": paths[0]["hops"], "exploredAssertionCount": len(identifiers), "searchDepth": depth, "direction": args.direction, "pathMeaning": "Paths compose source-supported assertions for inspection, not a new causal or scientific conclusion. Each hop preserves its recorded direction.", "coverage": "Bounded candidate search only; unreturned paths are not proof of absence"}
    return {"items": [], "paths": [], "searchDepth": args.max_depth, "direction": args.direction, "coverage": "Bounded path search only; no path does not prove no connection"}


from .research import rank_entities, recent_source_updates, source_authors
