from datetime import date
from pathlib import Path
from typing import Any

from .wiki_utils import load_relevant_wiki_context

def build_ingest_prompt(chunk: str, filename: str, chunk_index: int, total_chunks: int, 
                        index_md: str, schema: str, ingestion_prompt: str) -> str:
    schema_block = schema if chunk_index == 0 else "You are a strict wiki maintainer. Same rules and format as before."
    return f"""{schema_block}
---
CURRENT index.md:
{index_md}

---

SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})
CONTENT:
{chunk}

---
{ingestion_prompt}

Today's date: {date.today().isoformat()}"""


def build_query_prompt(SCHEMA: str, WIKI_DIR: Path, question: str, QUERY_PROMPT: str) -> str:
    context = load_relevant_wiki_context(WIKI_DIR=WIKI_DIR, question=question)
    return f"""
{SCHEMA}

---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{context}
---
QUESTION: {question}

---
{QUERY_PROMPT}
"""


def build_question_prompt(SCHEMA: str, WIKI_DIR: Path, q_pdf: Any, QUESTION_PROMPT: str, q_text: str) -> str:
    context = load_relevant_wiki_context(WIKI_DIR=WIKI_DIR, question=q_text)
    return f"""
{SCHEMA}

---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{context}

===
{QUESTION_PROMPT}

---
QUESTION DOCUMENT ({q_pdf.name}):
{q_text[:40000]}
"""
