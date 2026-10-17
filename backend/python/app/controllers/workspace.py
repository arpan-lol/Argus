import math
from typing import Literal
from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field
from app.config import settings
from app.database import connection
from app.services import corpus,graph,map,retrieval

Mode=Literal["network","grouped"]


def compact(value):
    if isinstance(value,dict):
        return {key:compact(item) for key,item in value.items() if key not in ("pmcids","ids","discoveryIds")}
    if isinstance(value,list):
        return [compact(item) for item in value]
    return value


def health(request:Request):
    workers=getattr(request.app.state,"ingestion_workers",None)
    return {"status":"ok","service":"argus-python","storage":"postgres","corpus":corpus.counts(),"graph":graph.status(),"workers":workers.status() if workers else {"configuredWorkers":0},"capabilities":{"lexical":True,"vector":False,"generation":False}}


def collection():
    catalog=corpus.catalog()
    return {"schemaVersion":2,"collection":catalog["collection"],"updatedAt":catalog["updatedAt"],"counts":corpus.counts(),"discovery":compact(catalog.get("discovery",{})),"ingestion":compact(catalog.get("ingestion",{})),"capabilities":{"lexical":True,"graph":graph.status()["status"]=="ready","vector":False,"generation":False,"reranking":False},"graph":graph.status(),"offsetUnit":"unicode_codepoint","legacyCorpus":True,"legacyNotice":"Imported source and dictionary graph records remain visible. Standardized jobs report their own processing and publication status."}


def documents(limit:int=Query(24,ge=1,le=100),offset:int=Query(0,ge=0)):
    return {"documents":corpus.summaries(limit,offset),"total":corpus.counts()["documents"],"limit":limit,"offset":offset}


def document(identifier:str):
    return corpus.document(identifier)


def overview(mode:Mode="network"):
    return map.overview(mode)


def view(minX:float,minY:float,maxX:float,maxY:float,zoom:float,limit:int=800,mode:Mode="network"):
    if not all(math.isfinite(item) for item in (minX,minY,maxX,maxY,zoom)) or minX>=maxX or minY>=maxY or zoom<=0 or maxX-minX>1000000 or maxY-minY>1000000:
        raise HTTPException(400,"Invalid source map viewport")
    return map.view({"minX":minX,"minY":minY,"maxX":maxX,"maxY":maxY},zoom,max(50,min(800,limit)),mode)


def locate(identifier:str,mode:Mode="network"):
    return map.locate(identifier,mode)


def node(identifier:str,mode:Mode="network"):
    return map.node(identifier,mode)


def neighborhood(identifier:str,mode:Mode="network"):
    return map.neighborhood(identifier,mode)


def inspect(documentId:str|None=None,sectionId:str|None=None,chunkId:str|None=None):
    return graph.inspect({key:value for key,value in {"documentId":documentId,"sectionId":sectionId,"chunkId":chunkId}.items() if value})


def diagnostics():
    result=graph.status()
    if result["status"]=="ready":
        result.update(nodes=graph.query("MATCH (n) RETURN count(n)")[0][0],edges=graph.query("MATCH ()-[r]->() RETURN count(r)")[0][0])
    return {**result,"capabilities":{"graphTraversal":True,"propertyIndexes":True,"vectorIndex":False},"note":"Source graph inspection runs in FalkorDB; lexical retrieval runs in Postgres pg_search. Legacy graph facts are not newly validated assertions."}


def sync():
    return {"error":"Legacy dictionary backfill is retired. Submit sources through standardized ingestion."}


class Search(BaseModel):
    query:str=Field(min_length=1,max_length=2000)
    options:dict=Field(default_factory=dict)


def search(body:Search):
    if not body.query.strip():
        raise HTTPException(400,"A nonempty query is required")
    return retrieval.search(body.query.strip(),body.options)


def runs():
    with connection() as conn:
        return {"runs":conn.execute("SELECT id,created_at FROM api_runs ORDER BY created_at DESC LIMIT 100").fetchall()}


def run(identifier:str):
    with connection() as conn:
        row=conn.execute("SELECT payload FROM api_runs WHERE id=%s",(identifier,)).fetchone()
    if not row:
        raise HTTPException(404,"Run not found")
    return row["payload"]
