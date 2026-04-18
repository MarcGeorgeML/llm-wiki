from datetime import date
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
from PIL import Image
import io
import cv2
from typing import Any
from dotenv import load_dotenv

reader = easyocr.Reader(['en'], gpu=True)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "gemma3:12b")

def ask_groq_stream(prompt: str):
    
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user", 
                "content": prompt
            }
        ],
        temperature=1, # 0.2
        max_completion_tokens=8192,
        top_p=1,
        stream=True,
        stop=None
    )
    for chunk in completion:
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
            pix = page.get_pixmap(dpi=250)
            img_bytes = pix.tobytes("png")
            try:
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                img_arr = np.array(img)
            except Exception:
                try:
                    img_arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
                except Exception:
                    img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            try:
                result = reader.readtext(img_arr, detail=0)
            except Exception as e:
                # log and skip OCR on this page if reader fails
                st.warning(f"OCR failed on page: {e}")
                result = []
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


# def load_wiki_context(WIKI_DIR: Path) -> str:
#     index_path = WIKI_DIR / "index.md"
#     if not index_path.exists():
#         return "(wiki is empty)"
#     index = index_path.read_text(encoding="utf-8")
#     pages = [f"--- {md.name} ---\n{md.read_text(encoding='utf-8')}"
#             for md in sorted(WIKI_DIR.glob("*.md"))
#             if md.name not in ("index.md", "log.md", "_last_response.txt")]
#     context = f"=== INDEX ===\n{index}\n\n=== PAGES ===\n\n" + "\n\n".join(pages)
#     if len(context) > 80000:
#         st.warning(f"Wiki is large ({len(context)} chars) — truncating to 80k. Consider clearing and starting fresh for a new subject.")
#         context = context[:80000]
#     return context

def load_relevant_wiki_context(WIKI_DIR: Path, question: str, max_pages: int = 5) -> str:
    index_path = WIKI_DIR / "index.md"
    if not index_path.exists():
        return "(wiki is empty)"

    index = index_path.read_text(encoding="utf-8")
    question_words = set(question.lower().split())

    scored = []
    for md in sorted(WIKI_DIR.glob("*.md")):
        if md.name in ("index.md", "log.md", "_last_response.txt"):
            continue
        content = md.read_text(encoding="utf-8").lower()
        name_words = set(md.stem.lower().replace("-", " ").replace("_", " ").split())
        # score on both page name and page content
        name_score = len(question_words & name_words) * 2  # name match weighted higher
        content_score = sum(1 for w in question_words if w in content)
        scored.append((name_score + content_score, md))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_pages = [md for _, md in scored[:max_pages]]

    pages = [f"--- {md.name} ---\n{md.read_text(encoding='utf-8')}"
            for md in top_pages]

    return f"=== INDEX ===\n{index}\n\n=== RELEVANT PAGES ===\n\n" + "\n\n".join(pages)


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


def build_ingest_prompt(chunk: str, filename: str, chunk_index: int, total_chunks: int, 
                        index_md: str, schema: str, ingestion_prompt: str) -> str:
    schema_block = schema if chunk_index == 0 else "You are a strict wiki maintainer. Same rules and format as before."
    return f"""{schema_block}
---
CURRENT index.md:
{index_md[:3000]}

---

SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})
CONTENT:
{chunk}

---
{ingestion_prompt}

Today's date: {date.today().isoformat()}"""


def build_query_prompt(SCHEMA: str, WIKI_DIR: Path, question: str, QUERY_PROMPT: str) -> str:
    prompt = f"""
{SCHEMA}

---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{load_relevant_wiki_context(WIKI_DIR=WIKI_DIR, question=question)}

---
QUESTION: {question}

---
{QUERY_PROMPT}
"""
    return prompt


def build_question_prompt(SCHEMA: str, WIKI_DIR: Path, q_pdf: Any, QUESTION_PROMPT: str, q_text: str) -> str:
    prompt = f"""
{SCHEMA}

---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{load_relevant_wiki_context(WIKI_DIR=WIKI_DIR, question=q_text)}

===
{QUESTION_PROMPT}

---
QUESTION DOCUMENT ({q_pdf.name}):
{q_text[:40000]}"""
    return prompt