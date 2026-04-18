# LLM Wiki (local, Ollama + Gemma 3)

Personal knowledge base that compounds. Based on Karpathy's llm-wiki pattern.

## Setup

```bash
pip install pymupdf
```

Ollama must be running with your model pulled:
```bash
ollama pull gemma3
ollama serve
```

If your model has a different name, edit the `MODEL` variable at the top of both scripts.

## Usage

### 1. Ingest a PDF
```bash
python ingest.py raw/mynotes.pdf
```
The LLM reads it and writes/updates markdown pages in `wiki/`.

### 2. Ask a question
```bash
python query.py "what is the difference between X and Y?"
```

### 3. Answer questions inside a PDF
```bash
python query.py --pdf raw/exam_questions.pdf
```

### Switching subjects
Delete everything in `wiki/` and `raw/`. That's it.
Optionally back up first: `cp -r wiki/ wiki_backup_subject1/`

## Structure

```
llm-wiki/
├── schema.md        ← tells the LLM how to behave (edit this to tune it)
├── ingest.py        ← reads PDF, updates wiki
├── query.py         ← asks questions against wiki
├── raw/             ← put your PDFs here
└── wiki/
    ├── index.md     ← master list of all pages (auto-maintained)
    ├── log.md       ← history of ingests
    └── *.md         ← one page per concept (LLM writes these)
```

## Notes
- First ingest will be slow — Gemma 3 is doing real work
- If a response looks broken, check `wiki/_last_response.txt`
- The wiki folder is just markdown files — open in Obsidian for graph view
