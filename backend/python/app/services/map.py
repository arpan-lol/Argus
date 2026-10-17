import math
from functools import lru_cache
from fastapi import HTTPException
from app.database import connection
from app.services import corpus, graph

CELL = 512


def edge(source, target, kind, **extra):
    return {"id": f"{source}|{kind}|{target}", "source": source, "target": target, "type": kind, **extra}


@lru_cache(maxsize=2)
def layout(mode):
    with connection() as conn:
        rows = conn.execute("SELECT p.*,d.title FROM layout_positions p LEFT JOIN legacy_documents d ON d.id=p.id WHERE mode=%s", (mode,)).fetchall()
    return {row["id"]: row for row in rows}


@lru_cache(maxsize=1)
def memberships():
    with connection() as conn:
        rows = conn.execute("SELECT d.id,e->>'id' AS entity_id,e->>'label' AS label,e->>'type' AS kind FROM legacy_documents d CROSS JOIN LATERAL jsonb_array_elements(d.metadata->'entities') e").fetchall()
    terms = {}
    for row in rows:
        terms.setdefault(row["entity_id"], {"label": row["label"], "kind": row["kind"], "documents": []})["documents"].append(row["id"])
    return terms


def document_node(row):
    return {"id": row["id"], "type": "document", "label": row["title"][:70], "preview": row["title"], "documentId": row["id"], "x": row["x"]+CELL/2, "y": row["y"]+38, "radius": 12}


def entity_node(row):
    return {"id": row["id"], "type": "entity", "label": row["label"], "entityType": row["entity_type"], "x": row["x"], "y": row["y"], "radius": 8, "count": len(memberships().get(row["id"], {}).get("documents", []))}


def group_id(row):
    return f"map-group:{int(row['slot'])%80//8}:{int(row['slot'])//80//8}"


def groups():
    result = {}
    for row in layout("grouped").values():
        if row["kind"] != "document":
            continue
        identifier = group_id(row)
        if identifier not in result:
            _, x, y = identifier.split(":")
            result[identifier] = {"id": identifier, "type": "group", "label": "Source neighborhood", "preview": "Fixed navigation grouping, not a topic cluster.", "x": int(x)*CELL*8+CELL*4, "y": int(y)*CELL*8+CELL*4, "count": 0, "radius": 28}
        result[identifier]["count"] += 1
        result[identifier]["label"] = f"{result[identifier]['count']} documents"
    return list(result.values())


@lru_cache(maxsize=2)
def overview_edges(mode):
    positions = layout(mode)
    links = {}
    for entity_id, term in memberships().items():
        members = sorted((positions[item] for item in term["documents"] if item in positions), key=lambda row: (row["x"],row["y"]))
        pairs = []
        if mode == "grouped":
            identifiers = sorted(set(group_id(row) for row in members))
            pairs = list(zip(identifiers, identifiers[1:]))
        else:
            for index, row in enumerate(members):
                nearby = sorted((item for item in members[max(0,index-18):index+19] if item["id"]!=row["id"]), key=lambda item: math.hypot(row["x"]-item["x"],row["y"]-item["y"]))[:2]
                pairs.extend((row["id"],item["id"]) for item in nearby)
        for a,b in pairs:
            a,b = sorted((a,b))
            key = f"{a}|SHARES_TERM|{b}"
            item = links.setdefault(key, edge(a,b,"SHARES_TERM",derived=True,viaEntityIds=[],labels=[],count=0,meaning="Shared legacy dictionary mention; a navigation connection, not a scientific assertion.",membershipSource="legacy-source-ledger"))
            if entity_id not in item["viaEntityIds"]:
                item["viaEntityIds"].append(entity_id)
                item["labels"].append(term["label"])
                item["count"] += 1
    if mode == "grouped":
        return list(links.values())[:200]
    ordered = sorted(links.values(), key=lambda item: math.hypot(positions[item["source"]]["x"]-positions[item["target"]]["x"], positions[item["source"]]["y"]-positions[item["target"]]["y"]))
    degree, result = {}, []
    for item in ordered:
        a,b = item["source"],item["target"]
        if degree.get(a,0)>=3 or degree.get(b,0)>=3:
            continue
        degree[a] = degree.get(a,0)+1
        degree[b] = degree.get(b,0)+1
        result.append(item)
    return result[:9000]


def overview(mode="network"):
    documents = [row for row in layout(mode).values() if row["kind"]=="document"]
    if not documents:
        bounds = {"minX":0,"minY":0,"maxX":CELL,"maxY":CELL}
    elif mode=="grouped":
        bounds = {"minX":0,"minY":0,"maxX":80*CELL,"maxY":math.ceil((max(row["slot"] for row in documents)+1)/80)*CELL}
    else:
        bounds = {"minX":min(row["x"] for row in documents)-CELL,"minY":min(row["y"] for row in documents)-CELL,"maxX":max(row["x"] for row in documents)+CELL*2,"maxY":max(row["y"] for row in documents)+CELL*2}
    nodes = groups() if mode=="grouped" else [document_node(row) for row in documents]
    return {"version":2,"mode":mode,"bounds":bounds,"worldBounds":bounds,"nodes":nodes,"groups":nodes if mode=="grouped" else [],"edges":overview_edges(mode),"source":"postgres","counts":corpus.counts(),"layout":{"cellSize":CELL,"groupSize":8,"columns":80,"kind":"persistent-grouped-map" if mode=="grouped" else "persistent-organic-network","coordinateMeaning":"Imported stable navigation positions. Legacy dictionary co-mentions do not establish scientific relationships."}}


@lru_cache(maxsize=512)
def child_positions(document_id, mode):
    row = layout(mode).get(document_id)
    if not row:
        raise HTTPException(404,"Map document not found")
    with connection() as conn:
        sections = conn.execute("SELECT id FROM legacy_sections WHERE document_id=%s ORDER BY start_offset,id",(document_id,)).fetchall()
        chunks = conn.execute("SELECT id,section_id FROM legacy_chunks WHERE document_id=%s ORDER BY start_offset,id",(document_id,)).fetchall()
    children = {}
    for chunk in chunks:
        children.setdefault(chunk["section_id"],[]).append(chunk["id"])
    leaves = sum(max(1,len(children.get(section["id"],[]))) for section in sections)
    spacing = min(18,384/max(1,leaves-1))
    start = row["x"]+CELL/2-(leaves-1)*spacing/2
    result, slot = {},0
    for section in sections:
        entries = children.get(section["id"],[])
        width = max(1,len(entries))
        result[section["id"]] = {"x":start+(slot+(width-1)/2)*spacing,"y":row["y"]+116}
        for index, identifier in enumerate(entries):
            result[identifier] = {"x":start+(slot+index)*spacing,"y":row["y"]+206}
        slot += width
    return result


def child_node(identifier,document_id,mode):
    document=corpus.document(document_id)
    chunk=next((item for item in document["chunks"] if item["id"]==identifier),None)
    if chunk:
        return {"id":identifier,"type":"chunk","label":chunk["text"][:52],"preview":chunk["text"][:220],"documentId":document_id,"sectionId":chunk["sectionId"],"chunkId":identifier,"radius":4,"ordinal":chunk["ordinal"],"startOffset":chunk["startOffset"],"endOffset":chunk["endOffset"],**child_positions(document_id,mode)[identifier]}
    section=next((item for item in document["sections"] if item["id"]==identifier),None)
    if section:
        return {"id":identifier,"type":"section","label":section["title"],"preview":section["title"],"documentId":document_id,"sectionId":identifier,"radius":6,**child_positions(document_id,mode)[identifier]}
    raise HTTPException(404,"Source child not found")


def locate(identifier,mode="network"):
    row = layout(mode).get(identifier)
    if row:
        node = document_node(row) if row["kind"]=="document" else entity_node(row)
    elif identifier.startswith("map-group:"):
        node = next((row for row in groups() if row["id"]==identifier),None)
    else:
        with connection() as conn:
            chunk = conn.execute("SELECT payload,document_id,section_id FROM legacy_chunks WHERE id=%s",(identifier,)).fetchone()
            section = None if chunk else conn.execute("SELECT * FROM legacy_sections WHERE id=%s",(identifier,)).fetchone()
        if chunk:
            content = chunk["payload"]
            node = {"id":identifier,"type":"chunk","label":content["text"][:52],"preview":content["text"][:220],"documentId":chunk["document_id"],"sectionId":chunk["section_id"],"chunkId":identifier,"radius":4,"ordinal":content["ordinal"],"startOffset":content["startOffset"],"endOffset":content["endOffset"],**child_positions(chunk["document_id"],mode)[identifier]}
        elif section:
            node = {"id":identifier,"type":"section","label":section["title"],"preview":section["title"],"documentId":section["document_id"],"sectionId":identifier,"radius":6,**child_positions(section["document_id"],mode)[identifier]}
        else:
            node = None
    if not node:
        raise HTTPException(404,"Source map node not found")
    return {"node":node,"zoom":0.16 if node["type"]=="group" else 1.2 if node["type"]=="document" else 2.5,**{key:node[key] for key in ("documentId","sectionId","chunkId") if key in node}}


def view(bounds,zoom,limit=800,mode="network"):
    level = "overview" if zoom<0.08 else "documents" if zoom<0.45 else "detail"
    def inside(node, margin=0):
        return bounds["minX"]-margin<=node["x"]<=bounds["maxX"]+margin and bounds["minY"]-margin<=node["y"]<=bounds["maxY"]+margin
    if level=="overview":
        nodes = [node for node in overview(mode)["nodes"] if inside(node,CELL*4 if mode=="grouped" else CELL)]
        identifiers = {node["id"] for node in nodes}
        return {"nodes":nodes,"edges":[item for item in overview_edges(mode) if item["source"] in identifiers and item["target"] in identifiers],"level":"groups" if mode=="grouped" else level,"bounds":bounds,"truncated":False,"source":"postgres","status":"ready","note":"Stable source navigation; legacy shared mentions are not scientific assertions."}
    cx,cy = (bounds["minX"]+bounds["maxX"])/2,(bounds["minY"]+bounds["maxY"])/2
    candidates = sorted((row for row in layout(mode).values() if row["kind"]=="document" and inside(row,CELL*2)),key=lambda row:math.hypot(row["x"]+CELL/2-cx,row["y"]+CELL/2-cy))
    chosen = candidates[:12 if level=="detail" else 220]
    nodes,edges = {},{}
    for row in chosen:
        node = document_node(row)
        nodes[node["id"]] = node
        if level=="detail":
            for identifier,position in child_positions(row["id"],mode).items():
                if not inside(position,90) or len(nodes)>=limit:
                    continue
                child = child_node(identifier,row["id"],mode)
                nodes[identifier]=child
                if child["type"]=="chunk" and child["sectionId"] not in nodes:
                    parent=child_node(child["sectionId"],row["id"],mode)
                    nodes[parent["id"]]=parent
    for item in overview_edges(mode):
        if item["source"] in nodes and item["target"] in nodes:
            edges[item["id"]]=item
    source,status="postgres","ready"
    if nodes and level=="detail":
        try:
            relations=graph.query("MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id,b.id,type(r) LIMIT 1500",{"ids":list(nodes)})
            for a,b,kind in relations:
                item=edge(a,b,kind)
                edges[item["id"]]=item
            source="falkordb"
        except Exception:
            status="graph unavailable"
    return {"nodes":list(nodes.values()),"edges":list(edges.values())[:1500],"level":level,"bounds":bounds,"truncated":len(candidates)>len(chosen) or len(nodes)>=limit,"source":source,"status":status,"note":"Legacy imported sources; new standardized jobs are listed separately until published."}


def neighborhood(identifier,mode="network"):
    focus=locate(identifier,mode)["node"]
    nodes={identifier:focus}
    edges,paths={},[]
    def add_chunk(chunk_id):
        node=locate(chunk_id,mode)["node"]
        nodes[chunk_id]=node
        for parent_id in (node["documentId"],node["sectionId"]):
            nodes[parent_id]=locate(parent_id,mode)["node"]
        for a,b,kind in [(node["documentId"],node["sectionId"],"HAS_SECTION"),(node["sectionId"],chunk_id,"HAS_CHUNK")]:
            item=edge(a,b,kind)
            edges[item["id"]]=item
        return node
    if focus["type"]!="chunk":
        return {"nodes":list(nodes.values()),"edges":[],"paths":[],"truncated":False,"note":"Select a chunk to follow its actual connections.","source":"postgres","status":"ready","focusId":identifier}
    add_chunk(identifier)
    try:
        rows=graph.query("MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE c.id=$id RETURN DISTINCT e.id,e.label LIMIT 50",{"id":identifier})
        rows.sort(key=lambda row:len(memberships().get(row[0],{}).get("documents",[])))
        targets=set()
        for entity_id,label in rows[:3]:
            if entity_id not in layout(mode):
                continue
            nodes[entity_id]=entity_node(layout(mode)[entity_id])
            item=edge(identifier,entity_id,"MENTIONS")
            edges[item["id"]]=item
            candidates=graph.query("MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE e.id=$entity AND c.documentId<>$document RETURN DISTINCT c.documentId LIMIT 4",{"entity":entity_id,"document":focus["documentId"]})
            for document_row in candidates:
                document_id=document_row[0]
                if document_id not in layout(mode) or document_id not in targets and len(targets)>=3:
                    continue
                targets.add(document_id)
                chunks=graph.query("MATCH (c:Chunk)-[:MENTIONS]->(e:Entity) WHERE e.id=$entity AND c.documentId=$document RETURN DISTINCT c.id LIMIT 2",{"entity":entity_id,"document":document_id})
                for chunk_row in chunks:
                    node=add_chunk(chunk_row[0])
                    item=edge(node["id"],entity_id,"MENTIONS")
                    edges[item["id"]]=item
                    paths.append({"sourceChunkId":identifier,"targetChunkId":node["id"],"entityId":entity_id,"label":label,"documentId":document_id,"documentTitle":layout(mode)[document_id]["title"]})
        for adjacent,a,b in graph.query("MATCH (a:Chunk)-[r:NEXT_CHUNK]-(b:Chunk) WHERE a.id=$id RETURN DISTINCT b.id,startNode(r).id,endNode(r).id LIMIT 4",{"id":identifier}):
            add_chunk(adjacent)
            item=edge(a,b,"NEXT_CHUNK")
            edges[item["id"]]=item
        return {"nodes":list(nodes.values()),"edges":list(edges.values()),"paths":paths,"truncated":True,"note":"Bounded legacy shared-mention paths. Co-mentions do not establish scientific agreement or relationships.","source":"falkordb","status":"ready","focusId":identifier}
    except Exception:
        return {"nodes":list(nodes.values()),"edges":[],"paths":[],"truncated":True,"note":"Graph connections unavailable.","source":"postgres","status":"graph unavailable","focusId":identifier}


def node(identifier,mode="network"):
    location=locate(identifier,mode)
    item=location["node"]
    content=None
    if item["type"]=="chunk":
        content=corpus.chunk(identifier)["chunk"]
    elif item["type"]=="document":
        content={key:value for key,value in corpus.document(identifier).items() if key not in ("text","entities","chunks","sections")}
    elif item["type"]=="section":
        with connection() as conn:
            content=conn.execute("SELECT title,start_offset,end_offset FROM legacy_sections WHERE id=%s",(identifier,)).fetchone()
    return {**location,"description":{"document":"Parsed source document.","section":"Heading-delimited region of the source.","chunk":"Text segment with exact source offsets.","entity":"Legacy dictionary mention; not a validated assertion.","group":"Fixed navigation group."}[item["type"]],"content":content,"neighbors":[],"source":"postgres"}
