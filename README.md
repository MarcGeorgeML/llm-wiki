# LLM Wiki (Streamlit)

A small Streamlit app that ingests PDFs into a markdown wiki and answers
questions using either a local Ollama model or the Groq cloud API.

## Overview
- Entrypoint: `app.py` — Streamlit UI with three tabs: Ingest PDFs, Ask Questions, Browse Wiki.
- Core logic: `utils/utils.py` — PDF extraction (pymupdf + EasyOCR), model streaming adapters (`ask_ollama_stream`, `ask_groq_stream`), parsing/writing wiki files, and prompt builders.
- LLM instructions: `schema.py` — strict schema used when ingesting and answering (`SCHEMA`, `INGESTION_PROMPT`, `QUERY_PROMPT`, `QUESTION_PROMPT`).
- Wiki folder: `wiki/` (contains `index.md`, `log.md`, `_last_response.txt`, and content pages). Raw PDFs are stored in `raw/`.

## Requirements
- Python 3.8+
- See `requirements.txt` for dependencies (e.g. `pymupdf`, `streamlit`, `easyocr`, `numpy`, `python-dotenv`, `groq`).

## Environment variables (defaults coming from `utils/utils.py`)
- `GROQ_API_KEY` — Groq API key (for cloud streaming).
- `GROQ_MODEL` — optional Groq model id (defaults to `llama-3.3-70b-versatile`).
- `OLLAMA_URL` — Ollama server URL (default: `http://localhost:11434/api/generate`).
- `MODEL` — Ollama model name (default: `gemma3:12b`).

## Install
```bash
pip install -r requirements.txt
```

If using Ollama locally:
```bash
ollama pull <model-name>
ollama serve
```

## Run
Start the Streamlit app:
```bash
streamlit run app.py
```

On Windows (PowerShell) set env vars and run:
```powershell
$env:GROQ_API_KEY = "your_key_here"
$env:OLLAMA_URL = "http://localhost:11434/api/generate"
streamlit run app.py
```

On Windows (cmd):
```cmd
set GROQ_API_KEY=your_key_here
set OLLAMA_URL=http://localhost:11434/api/generate
streamlit run app.py
```

UI flow:
- Ingest PDFs — upload PDF(s); the app extracts text (pymupdf, falls back to EasyOCR), splits source content into 20k-character chunks, and sends each chunk to the LLM using `build_ingest_prompt`.
	- The LLM is expected to emit files wrapped in `===FILE: wiki/PageName.md=== ... ===END===` blocks. `parse_pages` parses those blocks and `write_wiki_pages` writes page files and updates `wiki/log.md` and `wiki/index.md`.
	- Raw PDFs are saved into `raw/`.
- Ask Questions — the app builds a prompt with `build_query_prompt` or `build_question_prompt` that includes `load_wiki_context()` output (index + pages), then streams the model response to the UI.
- Browse Wiki — view rendered markdown pages or expand to view raw markdown.

## Behavior notes & caveats
- OCR GPU: `easyocr.Reader(['en'], gpu=True)` may be slow or fail without a proper GPU/CUDA setup — set `gpu=False` in `utils/utils.py` if needed.
- Chunking: ingestion currently splits source text into fixed 20,000-character chunks before prompting the LLM; the first chunk includes the full `SCHEMA` block, later chunks receive a shorter reminder.
- Parsing: `parse_pages` expects model output in `===FILE: ... ===` / `===END===` blocks. If parsing fails, the full model response is saved to `wiki/_last_response.txt` and a fallback single page is written.
- Context size: `load_wiki_context` concatenates `index.md` and page files and truncates to ~80k characters; very large wikis will be trimmed before being sent to models.
- Path safety: `write_wiki_pages` validates output paths to avoid directory traversal or suspicious writes.
- Clear wiki: the UI "Clear Wiki" button removes the `wiki/` directory and recreates it (no confirmation dialog currently).

## Troubleshooting
- Ingest failures: inspect `wiki/_last_response.txt` for raw model output.
- OCR install errors: try CPU mode or install appropriate CUDA drivers for your GPU.
- Ollama: ensure `ollama serve` is running and `MODEL` matches a pulled model. `OLLAMA_URL` default points at the app's expected endpoint for streaming generation.

## Contributing / Next steps
- Improve `parse_pages` robustness, add unit tests for parsing/writing, and consider sentence-aware chunking or embedding-based retrieval for better query context.

## Checklist / TODO
- [ ] Add verification back after ingestion stabilizes
- [ ] Sentence-aware chunking
- [ ] Semantic search with embeddings for better query context retrieval
- [ ] Confirmation dialog on clear wiki button
