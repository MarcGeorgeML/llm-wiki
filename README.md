# llm-wiki

A small project that converts PDF documents into a local, browsable wiki using OCR and a streaming LLM. It provides an API to upload PDFs, ingest them into the wiki, run a lint/cleanup pass, and ask questions grounded in the wiki content.

This README explains what the code does, how the pieces fit together, and how to run and use the project on your own computer.

## Quick summary
- Upload a PDF to `/raw/` (or use the `/upload` endpoint).
- Run ingestion: OCR → chunk → ask LLM to convert chunks into wiki pages (written to `wiki/session_001/`).
- Run the linter to merge and clean pages.
- Query the wiki using the built-in query endpoints.

## Requirements
- Python 3.10+ (tested on 3.10/3.11)
- System packages required by `easyocr` and `opencv` (see notes below)
- A running LLM endpoint or API credentials (Ollama or Groq supported)

Prerequisite Python packages are declared in `backend/requirements.txt`.

## File structure

Top-level layout:

```
README.md
backend/
  main.py                # FastAPI app entrypoint
  requirements.txt       # Python dependencies
  schema.py              # Prompt templates and schemas
  services/
    clear_wiki.py
    ingestion_service.py
    linter_service.py
    query_service.py
    wiki_service.py
  utils/
    base_service.py
    file_utils.py
    llm_utils.py         # adapters for Ollama / Groq
    ocr_utils.py         # PDF -> text and chunking
raw/                    # uploaded PDFs (runtime)
wiki/                   # generated wiki pages and index
```

Read the code in `backend/` to see how services interact. The FastAPI app wires service singletons at startup.

## How it works (high level)
- Upload a PDF (or place it in `raw/`).
- `IngestionService` extracts text from the PDF (`ocr_utils`), splits it into chunks, and asks the LLM to output JSON representing wiki pages and an index. It writes `.md` files into `wiki/session_001/` and appends `index.md`.
- `LinterService` optionally merges similar pages and asks the LLM to clean pages so each page is a single coherent markdown document.
- `QueryService` selects the most relevant wiki pages for a question (LLM-assisted selection) and asks the LLM to answer using only the wiki content.
- `WikiService` provides read/list operations for the generated markdown pages.

## Configuration / Environment variables
Create a `.env` file or export environment variables before running.

- `OLLAMA_URL` (optional) — URL for a local Ollama API (default: `http://localhost:11434/api/generate`).
- `MODEL` (optional) — model name used by the Ollama adapter.
# llm-wiki

Simple tool to turn PDFs into a local markdown wiki and ask questions about the content.

This README is written in simple English and explains how to run and use the project.

## What this does
- Turn PDF files into markdown pages using OCR and an LLM.
- Store pages in `wiki/` and keep an `index.md` and `log.md`.
- Provide HTTP endpoints to upload PDFs, run ingestion, clean pages, and ask questions grounded in the wiki.

## Quick steps
1. Put PDFs in the `raw/` folder or use `POST /upload` to upload.
2. Run `POST /ingest` to convert PDFs into wiki pages.
3. Run `POST /lint` to clean and merge pages.
4. Use `POST /query/simple` or `POST /query/pdf` to ask questions.

## Requirements
- Python 3.10 or newer
- See `backend/requirements.txt` for Python packages
- If you use OCR with GPU, install `torch` with CUDA and set `OCR_GPU=true` in `.env`

## Environment variables
- `OLLAMA_URL` — URL for Ollama (default: `http://localhost:11434/api/generate`)
- `MODEL` — default model name used when calling Ollama
- `GROQ_API_KEY` and `GROQ_MODEL` — if you use Groq
- `OCR_GPU` — `True` or `False` (default False if not set)

Put these in a `.env` file or export them in your shell.

## File structure

Top-level layout (important files):

```
backend/
  main.py                # FastAPI app and routes
  requirements.txt       # Python deps
  schema.py              # prompts and rules the app sends to the LLM
  services/              # main logic
    ingestion_service.py
    linter_service.py
    query_service.py
    wiki_service.py
    clear_wiki.py
  utils/                 # helpers
    base_service.py
    file_utils.py
    llm_utils.py
    ocr_utils.py
raw/                    # put PDFs here or upload via API
wiki/                   # generated markdown pages, index.md, log.md
```

## How to run (local)

1. Create and activate a virtualenv:

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # macOS / Linux
```

2. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Start the server:

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for API docs.

## Key API endpoints (simple examples)

- `POST /upload` — upload a PDF (multipart). Saves to `raw/`.

curl example:
```bash
curl -F "file=@/path/to/file.pdf" http://localhost:8000/upload
```

- `POST /ingest` — ingest all PDFs in `raw/`.
- `POST /ingest/single` — upload + ingest one PDF in one call.
- `POST /lint` — run linter to merge and clean pages.
- `POST /query/simple` — JSON body `{ "query": "..." }` to ask a question.
- `POST /query/pdf` — upload a PDF with questions.
- `GET /wiki/pages` — list page names.
- `GET /wiki/page/{page_name}` — get page content or download with `?download=true`.
- `DELETE /wiki/clear` — delete and recreate the `wiki/` folder.

## How it works (short)

- OCR and text extraction: `backend/utils/ocr_utils.py` reads PDF text with PyMuPDF and uses EasyOCR for image-only pages.
- Ingestion: `backend/services/ingestion_service.py` chunks text, builds prompts, asks the LLM to return JSON describing pages, then writes markdown files and updates `index.md`.
- Linting: `backend/services/linter_service.py` can merge related pages and ask the LLM to clean page content.
- Querying: `backend/services/query_service.py` asks the LLM to select relevant pages and then answer using only the wiki content.

## Recent code updates (simple list)

- JSON repair: ingestion now tries to close missing brackets when the LLM output is cut off. This helps parsing partial streams.
- Local index in prompts: ingestion scores existing pages by word overlap with each text chunk and includes top matches in the prompt.
- Index update: after writing pages the ingestion service refreshes its local index map.
- No retry loop: ingestion no longer retries multiple times on parse failure; instead it logs raw model output to `wiki/_last_response.txt`.
- Ollama adapter: default `MODEL` value and extra request options are set in `backend/utils/llm_utils.py`.

I kept descriptions simple and did not change program behavior.

## Why this "LLM Wiki" approach (short)

- Easier to trace where answers come from because pages are normal markdown files.
- You can edit or fix wiki pages by hand.
- The linter and prompts force the LLM to use only wiki content, which reduces hallucinations.
- It is easier to debug wrong answers by inspecting `wiki/` and logs.

## Troubleshooting (quick)

- If ingestion fails to parse JSON, check `wiki/_last_response.txt` and `wiki/log.md`.
- If OCR is slow or failing, set `OCR_GPU=false` or install the correct `torch` build.
- If nothing appears in `wiki/`, make sure PDFs are in `raw/` and the server is using the expected LLM endpoint.

---
Last updated: April 2026
