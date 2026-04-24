import json
from pathlib import Path
from typing import Any

from schema import QUERY_PROMPT, QUESTION_PROMPT, QUESTION_SCHEMA, SELECT_PAGES_SCHEMA_QUESTION
from utils.utils import PDFService


class QueryService(PDFService):

    def __init__(self, WIKI_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.stream_fn = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _select_pages(self, query: str, index: str, max_pages: int = 5) -> list[str]:
        if not index:
            return []
        prompt = f"QUESTION:\n{query}\n\nAVAILABLE PAGES:\n{index}"
        response = "".join(self.stream_fn(prompt, system=SELECT_PAGES_SCHEMA_QUESTION.format(max_pages=max_pages)))
        try:
            selected = json.loads(response)
        except Exception:
            return []
        valid = set()
        for line in index.splitlines():
            parsed = self.parse_index_line(line)
            if parsed:
                valid.add(parsed[0])
        return [p for p in selected if p in valid][:max_pages]


    def _build_prompt(self, query: str, selected_pages: list[str], source_name: str | None = None) -> str:
        index = self._get_index(self.WIKI_DIR)
        page_map = self._get_page_map(self.WIKI_DIR)
        pages_content = "\n\n".join(
            f"[PAGE: {name}]\n---\n{page_map[name].read_text(encoding='utf-8')}"
            for name in selected_pages if name in page_map
        )
        context = f"[Index]\n{index}\n\n[Pages]\n{pages_content or '(no pages found)'}"
        task_prompt = QUESTION_PROMPT if source_name else QUERY_PROMPT
        source_block = f"QUESTION DOCUMENT ({source_name}):\n{query}\n---\n" if source_name else f"QUESTION:\n{query}\n---\n"
        return f"WIKI CONTENT (this is ALL you know — do not use outside knowledge):\n{context}\n---\n{source_block}{task_prompt}"


    def execute_query(self, query: str | None = None):
        if not query:
            return {"status": "error", "message": "No question provided"}
        index = self._get_index(self.WIKI_DIR)
        selected_pages = self._select_pages(query, index)
        print("Selected pages:", selected_pages)
        return self.stream_fn(self._build_prompt(query, selected_pages), system=QUESTION_SCHEMA)


    def execute_pdf(self, q_pdf: Any | None = None):
        if not q_pdf:
            return {"status": "error", "message": "Missing PDF"}
        q_text = self.extract_pdf_text(q_pdf.read())
        index = self._get_index(self.WIKI_DIR)
        selected_pages = self._select_pages(q_text, index)
        print("Selected pages:", selected_pages)
        return self.stream_fn(self._build_prompt(q_text, selected_pages, source_name=q_pdf.name), system=QUESTION_SCHEMA)