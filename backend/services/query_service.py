from pathlib import Path
from typing import Any

from schema import (
    QUERY_PROMPT,
    QUESTION_PROMPT,
    QUESTION_SCHEMA,
    SELECT_PAGES_SCHEMA_QUESTION,
)
from utils.base_service import BaseService


class QueryService(BaseService):

    def __init__(self, WIKI_DIR: Path, stream_fn):
        super().__init__(WIKI_DIR, stream_fn)

    def _select_wiki_pages(self, query: str, index: str, max_pages: int = 5) -> list[str]:
        valid = [parsed[0] for line in index.splitlines() if (parsed := self.parse_index_line(line))]
        if not valid:
            return []
        top = self._top_k_pages(query, valid, k=20)  # pre-filter to top 20
        filtered_index = "\n".join(f"[[{p}]] — {self.index_map.get(p, p)}" for p in top)
        prompt = f"QUESTION:\n{query}\n\nAVAILABLE PAGES:\n{filtered_index}"
        return super()._select_pages(prompt, SELECT_PAGES_SCHEMA_QUESTION.format(max_pages=max_pages), set(top), max_pages)

    def _build_prompt(
        self, query: str, selected_pages: list[str], source_name: str | None = None
    ) -> str:
        file_map = self._build_file_map()
        index = (
            self.INDEX_PATH.read_text(encoding="utf-8")
            if self.INDEX_PATH.exists()
            else ""
        )
        pages_content = "\n\n".join(
            f"[PAGE: {name}]\n---\n{file_map[name].read_text(encoding='utf-8')}"
            for name in selected_pages
            if name in file_map
        )
        context = f"[Index]\n{index}\n\n[Pages]\n{pages_content or '(no pages found)'}"
        task_prompt = QUESTION_PROMPT if source_name else QUERY_PROMPT
        source_block = (
            f"QUESTION DOCUMENT ({source_name}):\n{query}\n---\n"
            if source_name
            else f"QUESTION:\n{query}\n---\n"
        )
        return f"WIKI CONTENT (this is ALL you know — do not use outside knowledge):\n{context}\n---\n{source_block}{task_prompt}"

    def execute_query(self, query: str | None = None):
        if not query:
            return {"status": "error", "message": "No question provided"}
        self.index_map = self._get_index_map()
        index = self.INDEX_PATH.read_text(encoding="utf-8") if self.INDEX_PATH.exists() else ""
        selected_pages = self._select_wiki_pages(query, index)
        print("Selected pages:", selected_pages)
        return {
            "result": self.stream_fn(
                self._build_prompt(query, selected_pages),
                system=QUESTION_SCHEMA
            ),
            "selected_pages": selected_pages,
        }

    async def execute_pdf(self, q_pdf: Any | None = None):
        if not q_pdf:
            return {"status": "error", "message": "Missing PDF"}
        self.index_map = self._get_index_map()
        q_text, failed_pages = self.extract_pdf_text(await q_pdf.read())
        index = self.INDEX_PATH.read_text(encoding="utf-8") if self.INDEX_PATH.exists() else ""
        selected_pages = self._select_wiki_pages(q_text, index)
        print("Selected pages:", selected_pages)
        print("Number of failed pages:", failed_pages)
        return {
            "result": self.stream_fn(
                self._build_prompt(q_text, selected_pages, source_name=q_pdf.name),
                system=QUESTION_SCHEMA
            ),
            "selected_pages": selected_pages,
            "number_of_pages_not_read_from_question_paper": failed_pages,
        }
