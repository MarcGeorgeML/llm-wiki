# llm-wiki

This repository converts PDF documents into a small, local markdown wiki and provides an API to query that wiki using a local LLM (Ollama) or Groq. The goal is to make document knowledge extractable, inspectable as Markdown, and answerable by a grounded LLM prompt that is restricted to the wiki's content.

---

## Summary

- Converts PDFs -> text (PyMuPDF) with OCR fallback (EasyOCR) for image pages.
- Splits documents into chunks and asks an LLM to produce structured wiki pages (Markdown) and an index.
- Stores pages under the `wiki/` folder and maintains `index.md` and `log.md`.
- Provides HTTP endpoints (FastAPI) to upload PDFs, run ingestion, run a linter, query, and manage the wiki.

This README explains how the pieces fit together so another developer can run, extend, or debug the system.

---

## Quick start (developer)

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

3. Provide environment variables (example `.env`):

- `OLLAMA_URL` — Ollama streaming endpoint (default used by adapters).
- `MODEL` — model name for Ollama adapter (example `gemma3:12b`).
- `GROQ_API_KEY` and `GROQ_MODEL` — if using Groq.
- `OCR_GPU` — `true` or `false` (EasyOCR GPU usage).

You can put them in a `.env` file (the app loads it) or export in your shell.

4. Run the API:

```bash
uvicorn backend.main:app --reload --port 8000
```

The service will be available at `http://localhost:8000`.

---

## Main responsibilities & architecture

- Entrypoint: [backend/main.py](backend/main.py) — FastAPI app, lifecycle, and endpoints.
- Prompt & schema definitions: [backend/schema.py](backend/schema.py) — ingestion, selection, cleanup, and query prompts and rules.
- LLM adapters: [backend/utils/llm_utils.py](backend/utils/llm_utils.py) — streaming helpers for Ollama and Groq.
- File + wiki helpers: [backend/utils/file_utils.py](backend/utils/file_utils.py) — index parsing, file map, index updates, log path.
- OCR + chunking: [backend/utils/ocr_utils.py](backend/utils/ocr_utils.py) — extract text from PDFs, fallback OCR for image pages, chunking by page.
- Core services (in backend/services/):
	- [backend/services/ingestion_service.py](backend/services/ingestion_service.py): orchestrates extraction, chunking, LLM ingestion prompts, parses JSON output, writes Markdown pages to `wiki/session_001/`, and updates `index.md`.
	- [backend/services/linter_service.py](backend/services/linter_service.py): merges related pages, calls the LLM cleanup prompt, removes merged files, updates index, and flags orphan pages.
	- [backend/services/query_service.py](backend/services/query_service.py): selects best-matching pages (via an LLM selection prompt) and builds a final prompt combining `index.md` + selected pages; returns streamed answers.
	- [backend/services/wiki_service.py](backend/services/wiki_service.py): helper to list pages and return page content.
	- [backend/services/clear_wiki.py](backend/services/clear_wiki.py): removes and recreates the `wiki/` folder (destructive).

These components share `BaseService` ([backend/utils/base_service.py](backend/utils/base_service.py)) which combines file and OCR helpers and provides common logging and selection helpers.

---

## Data flow (high level)

1. Upload: client uploads PDF via `POST /upload` or places files in `raw/`.
2. Ingest: `POST /ingest` reads all PDFs in `raw/` and for each:
	 - `OCRService.extract_pdf_text()` uses PyMuPDF; if a page has no text, EasyOCR extracts text from an image of the page.
	 - `OCRService.chunk_text()` splits by `---PAGE_BREAK---` and groups pages into chunks (~3500 chars).
	 - For each chunk the service builds a prompt (using `INGESTION_PROMPT` / `SCHEMA`) and calls the streaming LLM adapter expecting a JSON array describing pages/index.
	 - Responses are parsed (uses `json5` for lenient JSON) and written to `wiki/session_001/` as Markdown files and `index.md` is updated.
3. Lint: `POST /lint` runs `LinterService` to merge similar pages, run the cleanup prompt on each page, and flag orphans.
4. Query: `POST /query/simple` or `POST /query/pdf` — `QueryService` uses a selection prompt to pick relevant pages, then streams a final answer restricted to wiki content.

---

## HTTP API (quick reference)

- `POST /upload` — multipart file upload; saves file to `raw/`.
- `POST /ingest` — ingests all PDFs in `raw/`. Accepts optional `model` parameter (`ollama` | `groq`).
- `POST /ingest/single` — upload and ingest a single PDF in one call.
- `POST /lint` — runs the linter that may merge, clean, or delete files.
- `POST /query/simple` — JSON body `{ "query": "..." }`. Streams LLM output.
- `POST /query/pdf` — multipart PDF upload containing questions; runs the PDF-based query flow.
- `GET /wiki/pages` — returns list of page names.
- `GET /wiki/page/{page_name}` — returns markdown text or download if `?download=true`.
- `DELETE /wiki/clear` — deletes the `wiki/` directory and recreates it.

Refer to [backend/main.py](backend/main.py) for exact request signatures and route details.

---

## Model behavior & expectations

- The ingestion flow expects the LLM to return a strict JSON array describing pages and an index (see `INGESTION_PROMPT` in [backend/schema.py](backend/schema.py)). The code extracts JSON blocks and uses `json5` for leniency.
- The linter and query flows also rely on carefully written system prompts (`CLEANUP_PROMPT`, `QUESTION_SCHEMA`, etc.) to keep the LLM outputs structured.
- If the LLM returns stray text or fails to produce parseable JSON, raw output is appended to `wiki/_last_response.txt` for debugging.

---

## Important implementation notes and caveats

- The LLM adapters (`ask_ollama_stream`, `ask_groq_stream`) yield text chunks and the services join them. If the remote service changes its streaming format the parsers may break.
- Ingestion appends to files in `wiki/session_001/`. Re-running ingestion may append duplicate content unless sessions are rotated or cleared first.
- `DELETE /wiki/clear` permanently removes `wiki/` — backups are your responsibility.
- OCR failures in `OCRService.extract_pdf_text` may raise exceptions for a page; ingestion will record errors in its returned result.
- Logging: service logs are written to `wiki/log.md` using per-service loggers.

---

## Troubleshooting

- No pages created during ingestion: check `wiki/_last_response.txt` and `wiki/log.md` for parse errors and raw model outputs.
- OCR slow or failing: try `OCR_GPU=false` or install GPU drivers and set `OCR_GPU=true`.
- Server failing to start: confirm Python version and that `pip install -r backend/requirements.txt` completed successfully.

---

## Tests, development ideas, and next steps

- Add unit tests for `OCRService.chunk_text()` and `FileService.parse_index_line()`.
- Add an integration test that runs ingestion on a small sample PDF and verifies `wiki/` output.
- Add a minimal web UI to view & edit wiki pages and send queries.
- Rotate ingestion sessions (e.g., `session_002`) instead of always appending to `session_001` to avoid accidental duplication.

---

If you want, I can now:

1. Add a short integration test that runs a tiny sample through ingestion and verifies output.
2. Add a simple CLI to run ingestion on a single PDF and inspect session output.
3. Start the server locally and run a smoke test (requires your env variables).

Tell me which and I'll proceed.


