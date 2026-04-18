# LLM Wiki (Streamlit)

A small Streamlit app that ingests PDFs into a markdown wiki and answers
questions using either a local Ollama model or the Groq cloud API.

## Overview
- Entrypoint: `app.py` — Streamlit UI with three tabs: Ingest PDFs, Ask Questions, Browse Wiki.
- Core logic: `utils/utils.py` — PDF extraction (pymupdf + EasyOCR), model streaming adapters, parsing/writing wiki files.
- LLM instructions: `schema.py` — strict schema used when ingesting and answering.
- Wiki folder: `wiki/` (contains `index.md`, `log.md`, and content pages). Raw PDFs are stored in `raw/`.

## Requirements
- Python 3.8+
- See `requirements.txt` (includes `pymupdf`, `streamlit`, `easyocr`, `numpy`, `python-dotenv`, `groq`).

## Environment variables
- `GROQ_API_KEY` — Groq API key (for cloud streaming).
- `GROQ_MODEL` — optional Groq model id (defaults to `llama-3.3-70b-versatile`).
- `OLLAMA_URL` — Ollama server URL (default: `http://localhost:11434/api/chat`).
- `MODEL` — Ollama model name (default set in `utils/utils.py`).

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
$env:OLLAMA_URL = "http://localhost:11434/api/chat"
streamlit run app.py
```

On Windows (cmd):
```cmd
set GROQ_API_KEY=your_key_here
set OLLAMA_URL=http://localhost:11434/api/chat
streamlit run app.py
```

UI flow:
- Ingest PDFs — upload PDF(s); LLM writes `wiki/*.md` and appends `wiki/log.md`; raw PDFs saved in `raw/`.
- Ask Questions — queries use only wiki content and enforce citations.
- Browse Wiki — view rendered markdown pages.

## Behavior notes & caveats
- OCR GPU: `easyocr.Reader(['en'], gpu=True)` may fail or be slow without a GPU — set `gpu=False` in `utils/utils.py` if needed.
- Parsing: `parse_pages` expects model output in `===FILE: ... ===` / `===END===` blocks. Malformed output falls back to a single saved page; check `wiki/_last_response.txt`.
- Context size: `load_wiki_context` truncates to ~80k chars for large wikis; long wikis will be cut.
- Path safety: `write_wiki_pages` checks output paths and will skip suspicious paths.
- Note: older README references `ingest.py`/`query.py` which are not present; current entrypoint is `app.py`.

## Troubleshooting
- Ingest failures: inspect `wiki/_last_response.txt` for raw model output.
- EasyOCR install errors: try CPU mode or install appropriate CUDA drivers for your GPU.
- Ollama: ensure `ollama serve` is running and `MODEL` matches a pulled model.

## Contributing / Next steps
- Consider toggling EasyOCR GPU option, improving `parse_pages` robustness, or adding unit tests for parsing/writing.
