import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"


from pathlib import Path
from typing import cast
from enum import Enum
import json
import asyncio


from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings


from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse


from utils.llm_utils import ask_ollama_stream, ask_groq_stream
from services.ingestion import IngestionService
from services.clear_wiki import ClearWikiService


BASE_DIR  = Path(__file__).parent.parent  # goes up from backend/ to llm-wiki/
WIKI_DIR  = BASE_DIR / "wiki"
RAW_DIR   = BASE_DIR / "raw"
CHROMA_DIR = BASE_DIR / "chroma_db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    app.state.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(allow_reset=True))
    
    app.state.collection = app.state.chroma_client.get_or_create_collection("wiki")
    
    app.state.ingestion = IngestionService(
        embedder = app.state.embedder,
        collection = app.state.collection,
        WIKI_DIR = WIKI_DIR,
        RAW_DIR = RAW_DIR,
        stream_fn = ask_ollama_stream # default to local model for ingestion
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
        return JSONResponse(content={"error": "No PDFs found in raw folder"})

    async def generate():
        for pdf in pdfs:
            yield json.dumps({"status": "processing", "file": pdf.name}) + "\n"
            result = await asyncio.to_thread(app.state.ingestion.execute,
                pdf.name,
                pdf.read_bytes()
            )
            yield json.dumps(result) + "\n"
        yield json.dumps({"status": "all_done"}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")

@app.delete("/wiki/clear")
def clear_wiki():
    result = app.state.clear_wiki.execute(
        chroma_client=app.state.chroma_client,
        ingestion_service=app.state.ingestion
    )
    return JSONResponse(content=result)