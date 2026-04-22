
import json
from pathlib import Path
from typing import Any


from schema import QUERY_PROMPT, QUESTION_PROMPT, QUESTION_SCHEMA, SELECT_PAGES_SCHEMA
from utils.pdf_utils import PDFService


class QueryService(PDFService):


    def __init__(
        self, 
        WIKI_DIR: Path,
        stream_fn
    ):


        self.WIKI_DIR = WIKI_DIR
        self.stream_fn = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _get_page_hints(self) -> list[str]:
        index_path = self.WIKI_DIR / "index.md"
        if not index_path.exists():
            return []
        return [
            line.strip()
            for line in index_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


    def _select_pages(self, query: str, max_pages: int = 5) -> list[str]:
        hints = self._get_page_hints()
        if not hints:
            return []
        prompt = f"""QUESTION:
{query}

AVAILABLE PAGES (name — description):
{chr(10).join(hints)}

Select up to {max_pages} most relevant pages.
Return ONLY a JSON array of page names (strings).
Do NOT include descriptions or formatting.
"""
        system_prompt = SELECT_PAGES_SCHEMA.format(max_pages=max_pages)
        response = "".join(self.stream_fn(prompt, system=system_prompt))
        try:
            selected = json.loads(response)
        except Exception:
            selected = []
        valid = {
            line.split("[[")[1].split("]]")[0]
            for line in hints if "[[" in line and "]]" in line
        }
        selected = [p for p in selected if p in valid][:max_pages]
        if not selected:
            
            selected = [
                line.split("[[")[1].split("]]")[0]
                for line in hints[:max_pages]
            ]
            print("Page selection fallback triggered")
        return list(dict.fromkeys(selected))


    def _resolve_page(self, name: str) -> Path | None:
        for p in self.WIKI_DIR.rglob(f"{name}.md"):
            return p
        return None


    def _build_wiki_context(self, selected_pages: list[str]) -> str:
        index_path = self.WIKI_DIR / "index.md"
        index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        contents = []
        for name in selected_pages:
            path = self._resolve_page(name)
            if not path:
                continue
            contents.append(
                f"[PAGE: {name}]\n---\n{path.read_text(encoding='utf-8')}"
            )
        return f"""WIKI CONTEXT

[Index]
{index}

[Pages]
{chr(10).join(contents) if contents else "(no pages found)"}"""


    def _build_query_prompt(self, query: str, selected_pages: list[str]) -> str:
        context = self._build_wiki_context(selected_pages)
        return f"""{QUESTION_SCHEMA}
---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{context}
---
QUESTION:
{query}
---
{QUERY_PROMPT}
"""


    def _build_question_prompt(self, q_pdf_name: str, q_text: str, selected_pages: list[str]) -> str:
        context = self._build_wiki_context(selected_pages)
        return f"""{QUESTION_SCHEMA}
---
WIKI CONTENT (this is ALL you know — do not use outside knowledge):
{context}
---
QUESTION DOCUMENT ({q_pdf_name}):
{q_text[:40000]}
---
{QUESTION_PROMPT}
"""


    def execute_query(self, query: str | None = None):
        if not query:
            return {"status": "error", "message": "No question provided"}
        selected_pages = self._select_pages(query)
        print("Selected pages:", selected_pages)
        prompt = self._build_query_prompt(
            query=query,
            selected_pages=selected_pages
        )
        return self.stream_fn(prompt, system=QUESTION_SCHEMA)


    def execute_pdf(self, q_pdf: Any | None = None):
            if not q_pdf:
                return {"status": "error", "message": "Missing PDF"}
            q_text = self.extract_pdf_text(q_pdf.read())
            selected_pages = self._select_pages(q_text)
            print("Selected pages:", selected_pages)
            prompt = self._build_question_prompt(
                q_pdf_name=q_pdf.name,
                q_text=q_text,
                selected_pages=selected_pages
            )
            return self.stream_fn(prompt, system=QUESTION_SCHEMA)