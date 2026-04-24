import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"


from pathlib import Path
from typing import cast
from enum import Enum


from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel


from utils.llm_utils import ask_ollama_stream, ask_groq_stream


from services.ingestion_service import IngestionService
from services.cleanup_service import CleanupService
from services.clear_wiki import ClearWikiService
from services.query_service import QueryService
from services.wiki_service import WikiService


BASE_DIR  = Path(__file__).parent.parent
WIKI_DIR  = BASE_DIR / "wiki"
RAW_DIR   = BASE_DIR / "raw"
CHROMA_DIR = BASE_DIR / "chroma_db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    app.state.ingestion = IngestionService(
        WIKI_DIR = WIKI_DIR,
        RAW_DIR = RAW_DIR,
        stream_fn = ask_ollama_stream # default to local model for ingestion
    )
    app.state.cleanup_service = CleanupService(WIKI_DIR, stream_fn = ask_ollama_stream)

    app.state.query_service = QueryService(
        WIKI_DIR = WIKI_DIR,
        stream_fn = ask_ollama_stream
    )
    app.state.wiki_service = WikiService(
        WIKI_DIR = WIKI_DIR
    )
    
    app.state.clear_wiki = ClearWikiService(
        WIKI_DIR = WIKI_DIR,
        RAW_DIR  = RAW_DIR
    )
    yield


app = FastAPI(lifespan=lifespan)

class ModelChoice(str, Enum):
    ollama = "ollama"
    groq   = "groq"

class QueryRequest(BaseModel):
    query: str


@app.get("/")
def root():
    return {"message": "LLM Wiki API is running."}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(description="Upload a PDF file")):
    RAW_DIR.mkdir(exist_ok=True)
    dest = RAW_DIR / cast(str, file.filename)
    dest.write_bytes(await file.read())
    return {"uploaded": file.filename}


@app.post("/ingest")
async def ingest_pdfs(model: ModelChoice = ModelChoice.ollama):
    app.state.ingestion.set_stream(ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream)
    pdfs = list(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        return {"status": "error", "message": "No PDFs found in raw folder"}
    results = [app.state.ingestion.execute(pdf.name, pdf.read_bytes()) for pdf in pdfs]
    return JSONResponse(content = results)


@app.post("/ingest/single")
async def ingest_single_pdf(file: UploadFile = File(description="Upload a PDF file"), model: ModelChoice = ModelChoice.ollama):
    RAW_DIR.mkdir(exist_ok=True)
    dest = RAW_DIR / cast(str, file.filename)
    pdf_bytes = await file.read()
    dest.write_bytes(pdf_bytes)
    app.state.ingestion.set_stream(ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream)
    result = app.state.ingestion.execute(file.filename, pdf_bytes)
    return JSONResponse(content = result)


@app.post("/lint")
async def lint_wiki(model: ModelChoice = ModelChoice.ollama):
    app.state.cleanup_service.set_stream(ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream)
    result = app.state.cleanup_service.execute()
    return JSONResponse(content=result)


@app.post("/query/simple")
async def query_simple(req: QueryRequest, model: ModelChoice = Form(ModelChoice.ollama),):
    stream_fn = ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream
    app.state.query_service.set_stream(stream_fn)
    result = app.state.query_service.execute_query(query=req.query,)
    if isinstance(result, dict):
        return result
    return StreamingResponse(result, media_type="text/plain")


@app.post("/query/pdf")
async def query_pdf(q_pdf: UploadFile = File(...), model: ModelChoice = Form(ModelChoice.ollama)):
    stream_fn = ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream
    app.state.query_service.set_stream(stream_fn)
    result = app.state.query_service.execute_pdf(q_pdf=q_pdf)
    if isinstance(result, dict):
        return result
    return StreamingResponse(result, media_type="text/plain")


@app.get("/wiki/pages")
def list_pages():
    return app.state.wiki_service.list_pages()


@app.get("/wiki/page/{page_name}")
def get_page(page_name: str, download: bool = False):
    service = app.state.wiki_service
    path = service.resolve_page_path(page_name)
    if not path:
        return {"status": "error", "message": f"Page '{page_name}' not found"}
    if download:
        return FileResponse(
            path=path,
            media_type="text/markdown",
            filename=path.name
        )
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown"
    )


@app.delete("/wiki/clear")
def clear_wiki():
    result = app.state.clear_wiki.execute()
    return JSONResponse(content=result)