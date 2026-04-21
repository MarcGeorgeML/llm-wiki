# llm-wiki

**Overview**

llm-wiki is a document ingestion and question-answering project that extracts content from PDFs, converts them into structured markdown wiki pages, and indexes those pages into a persistent Chroma vector store for retrieval. The repository is focused on the backend ingestion pipeline implemented with FastAPI. The ingestion phase (PDF -> wiki pages -> Chroma index) is implemented and functional.

**Status**

- **Completed:** Ingestion pipeline (upload or place PDFs -> extract -> chunk -> LLM-driven page extraction -> write markdown pages -> index into Chroma).
- **In progress / Not provided here:** Query UI and a production front-end. The canonical backend services and helpers for querying and prompt building exist but the frontend is not bundled as the primary entrypoint.

**Architecture (high level)**

- **Input:** PDF files placed into the `raw/` directory or uploaded via the API.
- **Processing:** `backend/services/ingestion.py` (PDF extraction, chunking, building ingestion prompts, streaming LLM output, parsing JSON page objects, writing markdown pages, indexing to Chroma).
- **Storage:** Generated markdown pages are saved to `wiki/` and vector embeddings are stored in `chroma_db/`.
- **Server:** `backend/main.py` exposes FastAPI endpoints used to upload files, trigger ingestion, and clear the wiki/index.

**Key files and responsibilities**

- `backend/main.py` — FastAPI entrypoint and lifecycle (creates embedder and Chroma client).
- `backend/schema.py` — Prompt templates and strict ingestion/query schema strings.
- `backend/services/ingestion.py` — IngestionService: orchestrates extraction, parsing, writing, and indexing.
- `backend/services/query_service.py` — Helpers to load relevant context and build query prompts.
- `backend/services/clear_wiki.py` — ClearWikiService: remove wiki files and reset the Chroma collection.
- `backend/utils/pdf_utils.py` — PDF extraction (PyMuPDF) and OCR fallback (EasyOCR).
- `backend/utils/llm_utils.py` — Streaming adapters for Ollama and Groq cloud.
- `chroma_db/`, `raw/`, `wiki/` — runtime storage locations for DB, raw files, and generated content.

**How the ingestion pipeline works (conceptual)**

1. PDF uploaded (or placed in `raw/`).
2. `PDFService.extract_pdf_text` extracts text via PyMuPDF; EasyOCR is used as a fallback for scanned pages.
3. Text is chunked; each chunk is combined with an ingestion prompt (from `backend/schema.py`).
4. An LLM streaming adapter produces a JSON array describing page objects for the chunk (`name`, `url`, `category`, `text`).
5. `IngestionService._parse_pages` extracts the JSON, `_write_wiki_pages` saves markdown pages to `wiki/`, and `_index_wiki_page` embeds and upserts pages into Chroma.

**Development / Run instructions**

1. Set up a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate    # on Windows use: .\.venv\Scripts\activate
pip install -r backend/requirements.txt
```

2. Environment variables (examples):

- `OLLAMA_URL` — e.g. `http://localhost:11434/api/generate` (if using Ollama locally).
- `MODEL` — model name used by the Ollama adapter.
- `GROQ_API_KEY` and `GROQ_MODEL` — if using Groq cloud.
- `OCR_GPU` — set to `false` on CPU-only systems to prevent EasyOCR from trying to use CUDA.

3. Run the FastAPI backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

4. Use the ingestion-focused endpoints described below to upload and ingest PDFs.

**API endpoints (ingestion-focused)**

- `POST /upload` — Upload a PDF. Saves the file into `raw/`.
  - Example:

- `POST /ingest` — Trigger ingestion for PDFs in `raw/`. Extracts text, streams the LLM parsing, writes wiki pages, and indexes content.
  - Example:

- `DELETE /wiki/clear` — Clears the `wiki/` directory and resets the Chroma collection (destructive).

**Data locations**

- Raw PDFs: `raw/`
- Generated wiki pages: `wiki/`
- Persistent vector DB: `chroma_db/`

Keep these directories if you want to persist indexed content.

**Known issues & caveats**

- The ingestion parser assumes the LLM emits a JSON array. If the model outputs extra text, parsing may fail — the code writes the raw response to `wiki/_last_response.txt` and falls back to a safe behavior.
- EasyOCR may attempt to use GPU by default; set `OCR_GPU=false` or change the code if running on CPU-only environments.
- Some older UI helper modules (prompt/writer utilities) may not be present; use the `backend/services/` implementations as authorities for ingestion behavior.
- There is some duplication between query helper modules; consider consolidating before extensive query feature work.
- Filenames for wiki pages are taken from model outputs; sanitize these values before trusting them in untrusted environments.

**Next steps (recommended)**

- [ ] Improve chunking strategy to sentence level rather than just hard stop.
- [ ] Add unit tests.
- [ ] Complete QueryService Backend integration.
- [x] Make OCR GPU usage configurable and add graceful fallback handling.


