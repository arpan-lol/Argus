import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres import PostgresSaver
from app.config import settings
from app.database import migrate
from app.routes.api import router
from app.services.worker import IngestionWorkers
from app.retrieval.routes import router as retrieval_router

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger=logging.getLogger("argus")


@asynccontextmanager
async def lifespan(app):
    migrate()
    with PostgresSaver.from_conn_string(settings.database_url) as saver:
        saver.setup()
    from app.ingestion.pipeline import initialize
    initialize()
    workers=IngestionWorkers()
    app.state.ingestion_workers=workers
    workers.start()
    try:
        yield
    finally:
        workers.stop()


app=FastAPI(title="Argus",version="0.2.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_methods=["GET","POST"],allow_headers=["*"])
app.include_router(router,prefix="/api")
app.include_router(retrieval_router,prefix="/api")
try:
    from app.ingestion.routes import router as ingestion_router
    app.include_router(ingestion_router,prefix="/api")
except ModuleNotFoundError:
    logger.warning("Ingestion package is not installed")


@app.exception_handler(HTTPException)
async def http_error(request:Request,error:HTTPException):
    return JSONResponse(status_code=error.status_code,content={"error":error.detail})


@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,error:RequestValidationError):
    return JSONResponse(status_code=400,content={"error":"Invalid request","details":[{"field":".".join(str(item) for item in issue["loc"]),"message":issue["msg"]} for issue in error.errors()]})


@app.exception_handler(Exception)
async def internal_error(request:Request,error:Exception):
    logger.exception("Request failed: %s",request.url.path)
    return JSONResponse(status_code=503,content={"error":"The requested service is unavailable. Inspect server logs for details."})
