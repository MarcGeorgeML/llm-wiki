from sentence_transformers import SentenceTransformer
from contextlib import asynccontextmanager
import chromadb
from chromadb.config import Settings
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Annotated, cast
from enum import Enum


from utils.llm_utils import ask_ollama_stream, ask_groq_stream
from services.ingestion import IngestionService


WIKI_DIR = Path("wiki")
RAW_DIR = Path("raw")

app = FastAPI()

class ModelChoice(str, Enum):
    ollama = "ollama"
    groq   = "groq"


app.state.embedder = None
app.state.collection = None
app.state.ingestion = None
app.state.model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    chroma_client = chromadb.PersistentClient(path="wiki/chroma_db", settings=Settings(allow_reset=True))
    
    app.state.collection = chroma_client.get_or_create_collection("wiki")
    
    app.state.ingestion = IngestionService(
        embedder = app.state.embedder,
        collection = app.state.collection,
        WIKI_DIR = WIKI_DIR,
        RAW_DIR = RAW_DIR,
        stream_fn = ask_ollama_stream # default to local model for ingestion
    )  
    yield
    
@app.get("/")
def root():
    return {"message": "LLM Wiki API is running."}


@app.post("/ingest")
async def ingest_pdfs(
    files: Annotated[list[UploadFile], 
    File(description="Upload one or more PDF files")], 
    model: ModelChoice = ModelChoice.ollama
):
    
    app.state.ingestion.set_stream(
        ask_groq_stream if model == ModelChoice.groq else ask_ollama_stream
    )
    
    all_results = []
    for file in files:
        pdf_bytes = await file.read()
        result = app.state.ingestion.execute(
            filename=cast(str, file.filename),
            pdf_bytes=pdf_bytes
        )
        all_results.append(result)
    
    return JSONResponse(content={"files": all_results})