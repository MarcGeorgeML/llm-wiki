import json
import re
import urllib.request
import os
from pathlib import Path
import pymupdf as fitz
from google import genai
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "gemma3"
WIKI_DIR   = Path("wiki")
RAW_DIR    = Path("raw")
WIKI_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)

def ask_gemini_stream(prompt: str):
    client = genai.Client(api_key=GEMINI_API_KEY)
    for chunk in client.models.generate_content_stream(
        model=GEMINI_MODEL,
        contents=prompt
    ):
        if chunk.text:
            yield chunk.text


def ask_ollama_stream(prompt: str):
    payload = json.dumps({"model": MODEL, "prompt": prompt, "stream": True}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            chunk = json.loads(line)
            yield chunk["response"]
            if chunk.get("done"):
                break


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(str(page.get_text()) for page in doc)


def parse_pages(response: str) -> list[dict]:
    # Strip anything before the first ===FILE: block
    first = response.find("===FILE:")
    if first != -1:
        response = response[first:]
    pattern = re.compile(r"===FILE:\s*(.+?)===\n(.*?)===END===", re.DOTALL)
    return [{"path": m.group(1).strip(), "content": m.group(2).strip()}
            for m in pattern.finditer(response)]


def write_wiki_pages(pages: list[dict]):
    for page in pages:
        path = (Path.cwd() / page["path"]).resolve()
        # Reject anything trying to escape the wiki directory
        if not str(path).startswith(str(WIKI_DIR.resolve())):
            st.warning(f"Skipped suspicious path: {page['path']}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "log.md" and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + "\n\n" + page["content"], encoding="utf-8")
        else:
            path.write_text(page["content"], encoding="utf-8")


def load_wiki_context() -> str:
    index_path = WIKI_DIR / "index.md"
    if not index_path.exists():
        return "(wiki is empty)"
    index = index_path.read_text(encoding="utf-8")
    pages = [f"--- {md.name} ---\n{md.read_text(encoding='utf-8')}"
            for md in sorted(WIKI_DIR.glob("*.md"))
            if md.name not in ("index.md", "log.md", "_last_response.txt")]
    context = f"=== INDEX ===\n{index}\n\n=== PAGES ===\n\n" + "\n\n".join(pages)
    if len(context) > 80000:
        st.warning(f"Wiki is large ({len(context)} chars) — truncating to 80k. Consider clearing and starting fresh for a new subject.")
        context = context[:80000]
    return context


def get_wiki_pages() -> list[Path]:
    return [p for p in sorted(WIKI_DIR.glob("*.md")) if p.name != "_last_response.txt"]