import json
import re
import urllib.request
import os
from pathlib import Path
import pymupdf as fitz
import streamlit as st
import easyocr
from groq import Groq
import numpy as np
from dotenv import load_dotenv

reader = easyocr.Reader(['en'], gpu=True)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("MODEL", "gemma3:12b")

def ask_groq_stream(prompt: str):
    
    client = Groq(api_key=GROQ_API_KEY)
    stream = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )
    for chunk in stream:
        text = chunk.choices[0].delta.content
        if text:
            yield text


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
    pages_text = []
    for page in doc:
        normal = str(page.get_text()).strip()
        if normal:
            pages_text.append(normal)
        else:
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            result = reader.readtext(np.frombuffer(img_bytes, dtype=np.uint8), detail=0)
            lines: list[str] = []
            for item in result:
                if isinstance(item, str):
                    lines.append(item)
                elif isinstance(item, (list, tuple)):
                    lines.extend(str(v) for v in item if isinstance(v, str))
            ocr = "\n".join(lines).strip()
            if ocr:
                pages_text.append(ocr)
    return "\n".join(pages_text)

def write_wiki_pages(pages: list[dict], WIKI_DIR: Path):
    for page in pages:
        path = (Path.cwd() / page["path"]).resolve()
        if not str(path).startswith(str(WIKI_DIR.resolve())):
            st.warning(f"Skipped suspicious path: {page['path']}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "log.md" and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + "\n\n" + page["content"], encoding="utf-8")
        else:
            path.write_text(page["content"], encoding="utf-8")


def load_wiki_context(WIKI_DIR: Path) -> str:
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


def get_wiki_pages(WIKI_DIR: Path) -> list[Path]:
    return [p for p in sorted(WIKI_DIR.glob("*.md")) if p.name != "_last_response.txt"]

def parse_pages(response: str, filename: str = "source") -> list[dict]:
    first = response.find("===FILE:")
    if first != -1:
        response = response[first:]
    pattern = re.compile(r"===FILE:\s*(.+?)===\n(.*?)===END===", re.DOTALL)
    pages = [{"path": m.group(1).strip(), "content": m.group(2).strip()}
            for m in pattern.finditer(response)]
    if pages:
        return pages
    # Fallback: split on ===FILE: blocks without ===END===
    pattern = re.compile(r"===FILE:\s*(.+?)===\n(.*?)(?====FILE:|\Z)", re.DOTALL)
    pages = [{"path": m.group(1).strip(), "content": m.group(2).strip()}
            for m in pattern.finditer(response)]
    if pages:
        return pages
    # Last resort: model ignored format entirely, save whatever it wrote as a single page
    stem = Path(filename).stem
    return [
        {"path": f"wiki/{stem}.md", "content": response.strip()},
        {"path": "wiki/index.md",   "content": f"- [[{stem}]] — ingested from {filename}\n"},
    ]