# llm-wiki

**What this project does**

llm-wiki converts PDF documents into a small, local markdown wiki and lets you ask questions about that wiki using a large language model (LLM). It provides a simple HTTP API to upload PDFs, run ingestion, query the wiki, and manage pages.

**Why it exists (short)**

If you have documents (research papers, manuals, reports) you want searchable and queryable by an LLM, this project extracts the text, creates structured wiki pages, and keeps everything in plain markdown files under `wiki/`.

**High-level flow (simple)**

- Upload a PDF (API or put it in `raw/`).
- The ingestion service extracts text from the PDF (text extraction + OCR fallback), splits it into chunks, then asks an LLM to turn each chunk into one or more wiki pages.
- The service writes Markdown files into `wiki/` and maintains an `index.md`.
- Ask questions via the API; the query service chooses relevant pages and asks the LLM to answer using only the wiki content.

**Quick Start — run locally**

1. Create and activate a Python virtual environment:

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Set environment variables (examples):

- `OLLAMA_URL` — URL for local Ollama (e.g. `http://localhost:11434/api/generate`).
- `MODEL` — model name used by Ollama adapter (example: `gemma3:12b`).
- `GROQ_API_KEY` / `GROQ_MODEL` — if you use Groq.
- `OCR_GPU` — `true` or `false` (controls EasyOCR GPU usage).

You can set these in a `.env` file or your shell environment.

4. Start the server:

```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000/`.

**Core API endpoints (simple descriptions)**

- `POST /upload` — upload a PDF file (multipart). The file is saved to `raw/`.
- `POST /ingest` — process all PDFs found in `raw/` and create/update wiki pages.
- `POST /ingest/single` — upload and ingest a single PDF in one request (also saves to `raw/`).
- `POST /query/simple` — send a JSON body `{"query": "..."}` to ask a question; returns a streamed text answer.
- `POST /query/pdf` — upload a PDF that contains questions; the service extracts the text and runs the query flow.
- `GET /wiki/pages` — returns the list of page names in `wiki/`.
- `GET /wiki/page/{page_name}` — returns the markdown content of a page; `download` flag returns as a file.
- `DELETE /wiki/clear` — delete and recreate the `wiki/` folder (destructive).

**Key files to read (if you want to dig in)**

- `backend/main.py` — FastAPI app and service wiring.
- `backend/services/ingestion_service.py` — PDF ingestion logic and page writing.
- `backend/services/query_service.py` — selecting pages and asking the LLM to answer questions.
- `backend/services/linter.py` — page cleanup, prune suggestions, and orphan detection.
- `backend/utils/utils.py` — `PDFService`: text extraction, OCR fallback, and chunking.
- `backend/utils/llm_utils.py` — simple streaming adapters for Ollama and Groq.
- `backend/schema.py` — the prompt templates and strict JSON schemas the system expects from the model.

**Project structure**

```
llm-wiki/
├─ backend/
│  ├─ main.py                # FastAPI app and endpoints
│  ├─ requirements.txt       # Python dependencies for backend
│  ├─ schema.py              # Prompt templates and strict schemas
│  └─ services/
│     ├─ ingestion_service.py# Ingest PDFs -> write wiki pages
│     ├─ query_service.py    # Select pages and answer questions
│     ├─ linter.py           # Cleanup and prune wiki pages
│     ├─ wiki_service.py     # List/resolve pages
│     └─ clear_wiki.py       # Remove and recreate wiki/ directory
├─ raw/                      # Drop PDFs here or upload via API
├─ wiki/                     # Generated markdown pages and index.md
├─ README.md                 # This file
```


**Important behavior and tips (plain language)**

- The system expects the LLM to return strict JSON for ingestion. If the model outputs extra text or code fences the ingestion parser may fail. When parsing fails the raw model text is saved to `wiki/_last_response.txt` for debugging.
- Text extraction: PyMuPDF is used first. If a page has no selectable text, EasyOCR runs as a fallback. OCR is slower and may need a GPU for speed (`OCR_GPU=true`).
- Chunking: document text is split by original PDF pages using the marker `---PAGE_BREAK---` and combined into chunks under ~3500 characters to keep prompts manageable.
- Indexing: `index.md` holds a simple listing of pages in the wiki. The ingestion flow updates it automatically.
- Safety: `DELETE /wiki/clear` removes the whole `wiki/` folder — use carefully.

**Troubleshooting (quick)**

- If ingestion creates no pages, check `wiki/_last_response.txt` to see what the model returned.
- If OCR crashes or is very slow, try `OCR_GPU=false` or install GPU drivers if you want GPU acceleration.
- If the app won’t start, verify Python version (3.10+) and that `backend/requirements.txt` was installed into your active environment.

**Ideas for next steps**

- Add a small test that runs `IngestionService` on a short sample PDF and verifies it creates pages.
- Add unit tests for `PDFService.chunk_text` and `parse_index_line`.
- Add a lightweight web UI to browse `wiki/` and send queries.

If you want, I can implement tests or a short diagram next. Tell me which one and I will proceed.


