# llm-wiki

**Overview**

llm-wiki is a backend service that turns PDFs into a simple markdown wiki and lets you ask questions about that content using an LLM. The FastAPI backend handles PDF uploads, runs the ingestion pipeline (text extraction → LLM-driven page creation → markdown files), and exposes endpoints to ingest, query, list, and manage the wiki.

**Quick summary**

- **Input:** PDFs uploaded via the API or placed into the `raw/` folder.
- **Output:** Structured markdown pages written to the `wiki/` folder.
- **Core runtime:** FastAPI app in `backend/main.py` with small services in `backend/services/`.

**What's included**

- **Prompt templates and strict schemas:** backend/schema.py
- **Ingestion orchestration:** backend/services/ingestion_service.py (`IngestionService`)
- **Query orchestration:** backend/services/query_service.py (`QueryService`)
- **Cleanup & pruning:** backend/services/cleanup_service.py (`CleanupService`)
- **Wiki helpers:** backend/services/wiki_service.py (`WikiService`) and backend/services/clear_wiki.py (`ClearWikiService`)
- **PDF & OCR utilities:** backend/utils/utils.py (`PDFService`) — PyMuPDF extraction with EasyOCR fallback
- **LLM streaming adapters:** backend/utils/llm_utils.py (Groq and Ollama streaming)

**How the system works (data flow)**

1. A PDF is uploaded to the backend (POST /upload) or placed in `raw/`.
2. The ingestion endpoint (`POST /ingest`) reads PDFs from `raw/`, and `POST /ingest/single` accepts a single uploaded PDF.
3. The service extracts text from the PDF (PyMuPDF; EasyOCR fallback for scanned pages) and splits the text into chunks.
4. For each chunk the backend builds an ingestion prompt (see `backend/schema.py`) and streams an LLM response that should be a JSON array of page and index objects.
5. The ingestion service parses the JSON and writes or appends markdown files under `wiki/`. Each page includes a `## Sources` section with the original filename. If parsing fails, the raw model response is saved to `wiki/_last_response.txt`.

**Runtime / environment**

Prerequisites:

- Python 3.10+ recommended
- GPU optional for EasyOCR; code supports CPU-only but OCR may be slower

Install dependencies:

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Environment variables (examples):

- `OLLAMA_URL` — Ollama local API, e.g. http://localhost:11434/api/generate
- `MODEL` — model name used by the Ollama adapter
- `GROQ_API_KEY` — API key for Groq cloud (optional)
- `GROQ_MODEL` — Groq model identifier (optional)
- `OCR_GPU` — true/false (controls EasyOCR GPU usage)

Start the backend (development):

```bash
uvicorn backend.main:app --reload --port 8000
```

The FastAPI app registers services during lifespan and exposes the endpoints below.

**API (core endpoints)**

- POST /upload
  - Upload a PDF file (multipart/form-data). The file is saved to raw/.

- POST /ingest
  - Trigger ingestion for all PDFs in `raw/`. The service processes each file and returns per-file results.

- POST /ingest/single
  - Upload a single PDF and ingest it immediately. The uploaded file is also saved to `raw/`.

- POST /query/simple
  - Submit a simple question (JSON body {"query": "..."}). The service selects relevant pages and streams an LLM answer that is constrained to the wiki content.

- POST /query/pdf
  - Upload a PDF that contains one or more questions. The backend extracts the text and runs the query flow using the extracted questions.

- GET /wiki/pages
  - List available page names from the wiki/ directory.

- GET /wiki/page/{page_name}
  - Retrieve a page's markdown content. Optional download flag returns the file.

- DELETE /wiki/clear
  - Remove the wiki/ directory and recreate it empty (destructive).

Examples (curl):

```bash
# Upload a PDF
curl -F "file=@/path/to/doc.pdf" http://localhost:8000/upload

# Trigger ingestion (default uses local Ollama stream adapter)
curl -X POST http://localhost:8000/ingest

# Query a simple question
curl -H "Content-Type: application/json" -d '{"query":"What is X?"}' http://localhost:8000/query/simple
```

**Key implementation notes**

- The code constrains LLM behavior with strict prompt schemas in backend/schema.py — ingestion expects a JSON array of page/index objects, query selection expects a JSON array of page names, and cleanup/prune flows expect specific outputs. These schemas are central to reliable parsing.
- If the LLM emits extra text or code fences, ingestion parsing may fail; the raw response is written to wiki/_last_response.txt to help debugging.
- `PDFService.extract_pdf_text` returns text separated by the token "---PAGE_BREAK---" between original PDF pages. Chunking operates on those page boundaries.
- `IngestionService.execute` accepts a filename plus PDF bytes (`execute(filename: str, pdf_bytes: bytes`) and returns a per-file result summary. This is used by both `/ingest` (process all files) and `/ingest/single` (single uploaded file).
- Each generated wiki page includes a `## Sources` section listing the original PDF filename.

**File structure (important files & directories)**

- backend/main.py
- backend/schema.py
- backend/services/ingestion_service.py
- backend/services/query_service.py
- backend/services/cleanup_service.py
- backend/services/clear_wiki.py
- backend/services/wiki_service.py
- backend/utils/utils.py
- backend/utils/llm_utils.py
- backend/requirements.txt
- raw/        # place PDFs here or use POST /upload
- wiki/       # generated markdown pages and index.md

**Troubleshooting & tips**

- If parsing fails frequently, inspect wiki/_last_response.txt to see exactly what the model returned.
- On CPU-only machines set OCR_GPU=false to avoid EasyOCR GPU errors.
- The ingestion flow was built to be deterministic where possible (low temperature, explicit schema). If you change model settings, re-check for parsing robustness.

If you want, I can now:

- add a short diagram of the service call flow, or
- implement small tests that validate ingestion with a sample PDF.


