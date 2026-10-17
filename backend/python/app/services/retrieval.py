import time
import uuid
from psycopg.types.json import Jsonb
from app.database import connection
from app.services import corpus, graph


def search(query,options):
    started=time.perf_counter()
    run_id=str(uuid.uuid4())
    limit=max(1,min(30,int(options.get("limit") or 12)))
    rows=corpus.lexical(query,limit,options.get("documentId"))
    results=[]
    for index,row in enumerate(rows):
        chunk=row["payload"]
        doc=corpus.document(row["document_id"])
        results.append({**chunk,"chunkId":chunk["id"],"documentTitle":doc["title"],"score":row["score"],"scoreType":"bm25","rank":index+1,"reasons":["Matched source text using Postgres pg_search BM25"],"pathIds":[f"{doc['id']}|HAS_SECTION|{chunk['sectionId']}",f"{chunk['sectionId']}|HAS_CHUNK|{chunk['id']}"],"retrieval":"lexical"})
    elapsed=(time.perf_counter()-started)*1000
    projection=graph.inspect(ids=[item["id"] for item in results])
    response={"runId":run_id,"query":query,"corpusVersion":corpus.catalog().get("updatedAt"),"results":results,"trace":[{"id":run_id+":lexical","stage":"lexical retrieval","status":"complete","durationMs":elapsed,"outputCount":len(results),"details":{"engine":"Postgres pg_search","ranking":"BM25","scoreInterpretation":"BM25 relevance, not confidence or probability."}},{"id":run_id+":expansion","stage":"graph expansion","status":"unavailable","durationMs":0,"details":{"reason":"Python slice 1–3 provides source graph inspection; bounded hybrid traversal tools arrive in slice 4."}}],"timings":{"totalMs":(time.perf_counter()-started)*1000},"options":{"graphExpansion":False,"limit":limit,"documentId":options.get("documentId")},"capabilities":{"lexical":True,"graph":projection["source"]=="falkordb","vector":False,"generation":False,"reranking":False},"warnings":["Graph-assisted retrieval is pending slice 4. Results currently use Postgres BM25; graph inspection remains available."],"graph":projection,"offsetUnit":"unicode_codepoint"}
    with connection() as conn:
        conn.execute("INSERT INTO api_runs(id,payload) VALUES(%s,%s)",(run_id,Jsonb(response)))
    return response
