import json
import os


EXPAND = """MATCH (seed:Evidence)<-[:SUPPORTED_BY]-(a:Claim)-[:ABOUT]->(entity:Entity)<-[:ABOUT]-(b:Claim)-[:SUPPORTED_BY]->(related:Evidence)
WHERE seed.id IN $ids AND NOT related.id IN $ids
RETURN DISTINCT seed.id, a.id, entity.id, b.id, related.id LIMIT $limit"""


class LocalGraph:
    def __init__(self, store):
        self.store = store

    def ingest(self, documents, evidence, claims):
        return None

    def status(self):
        return {"provider": "local", "available": True, "persistent_graph": False, "execution_plan": False}

    def expand(self, evidence_ids, limit=20):
        claims = self.store.records("claims")
        seeds = set(evidence_ids)
        paths = []
        for a in claims:
            for seed in seeds.intersection(a["evidence_ids"]):
                for b in claims:
                    for entity in sorted({a["subject"], a["object"]}.intersection({b["subject"], b["object"]})):
                        for eid in b["evidence_ids"]:
                            path = [seed, a["id"], entity, b["id"], eid]
                            if eid not in seeds and path not in paths:
                                paths.append(path)
        return {"provider": "local", "query": "shared-entity expansion, one entity hop", "parameters": {"ids": evidence_ids, "limit": limit}, "paths": paths[:limit], "truncated": len(paths) > limit}


class FalkorGraph:
    def __init__(self):
        from falkordb import FalkorDB
        db = FalkorDB(host=os.getenv("FALKOR_HOST", "localhost"), port=int(os.getenv("FALKOR_PORT", "6379")), username=os.getenv("FALKOR_USERNAME"), password=os.getenv("FALKOR_PASSWORD"))
        self.graph = db.select_graph(os.getenv("FALKOR_GRAPH", "evidence_engine"))

    def status(self):
        try:
            self.graph.ro_query("RETURN 1", timeout=2000)
            return {"provider": "falkordb", "available": True, "persistent_graph": True, "execution_plan": True}
        except Exception:
            return {"provider": "falkordb", "available": False, "persistent_graph": True, "execution_plan": True}

    def ingest(self, documents, evidence, claims):
        for label in ["Document", "Evidence", "Claim", "Entity"]:
            self.graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        for d in documents:
            self.graph.query("MERGE (d:Document {id:$id}) SET d.title=$title, d.uri=$uri, d.revision=$revision", params={"id": d.id, "title": d.title, "uri": d.uri, "revision": d.revision})
        for e in evidence:
            self.graph.query("MATCH (d:Document {id:$doc}) MERGE (e:Evidence {id:$id}) SET e.start=$start, e.end=$end MERGE (e)-[:IN_DOCUMENT]->(d)", params={"doc": e.document_id, "id": e.id, "start": e.start, "end": e.end})
        for c in claims:
            self.graph.query("MERGE (c:Claim {id:$id}) SET c.predicate=$predicate, c.status=$status, c.subject=$subject, c.object=$object, c.qualifiers_json=$qualifiers MERGE (s:Entity {id:$subject}) MERGE (o:Entity {id:$object}) MERGE (c)-[:HAS_SUBJECT]->(s) MERGE (c)-[:HAS_OBJECT]->(o) MERGE (c)-[:ABOUT]->(s) MERGE (c)-[:ABOUT]->(o)", params={"id": c.id, "predicate": c.predicate, "status": c.status, "subject": c.subject, "object": c.object, "qualifiers": json.dumps(c.qualifiers, sort_keys=True)})
            for eid in c.evidence_ids:
                self.graph.query("MATCH (c:Claim {id:$id}), (e:Evidence {id:$eid}) MERGE (c)-[:SUPPORTED_BY]->(e)", params={"id": c.id, "eid": eid})

    def expand(self, evidence_ids, limit=20):
        params = {"ids": evidence_ids, "limit": limit}
        result = self.graph.ro_query(EXPAND, params=params, timeout=2000)
        return {"provider": "falkordb", "query": EXPAND, "parameters": params, "paths": result.result_set, "database_ms": result.run_time_ms, "execution_plan": str(self.graph.explain(EXPAND, params=params)), "truncated": None}
