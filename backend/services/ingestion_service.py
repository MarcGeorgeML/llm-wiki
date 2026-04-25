from pathlib import Path
import re
import json5
import logging


from schema import SCHEMA, INGESTION_PROMPT, SELECT_PAGES_SCHEMA_INGESTION, EXAMPLES
from utils.base_service import BaseService


class IngestionService(BaseService):

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path, stream_fn):
        super().__init__(WIKI_DIR, stream_fn)
        self.RAW_DIR = RAW_DIR
        self.logger = logging.getLogger("wiki.ingestion")

    def _assign_pages(self, chunk: str, index: str, valid: set[str]) -> list[str]:
        if not index:
            return []
        prompt = f"CONTENT:\n{chunk}\n\nEXISTING PAGES:\n{index}\n\n"
        return self._select_pages(prompt, SELECT_PAGES_SCHEMA_INGESTION, valid)

    def _build_local_index(self, local_pages: set) -> tuple[str, list[str]]:
        valid = [p for p in local_pages if p in self.index_map]
        if len(valid) >= 3:
            index = "\n".join(f"[[{p}]] — {self.index_map[p]}" for p in valid)
            return index, self._assign_pages("", index, set(valid))
        return "", list(local_pages)

    def _write_pages(self, pages: list[dict], session_dir: Path) -> None:
        index_updates = {}
        for page in pages:
            if page["path"] == "index":
                for line in page["content"]:
                    if parsed := self.parse_index_line(line):
                        index_updates[parsed[0]] = parsed[1]
                continue
            name = page["path"]
            path = session_dir / f"{name}.md"
            new_body = f"# {name}\n\n" + "\n\n".join(
                s.strip() for s in page["content"] if s.strip()
            )
            source_line = f"\n\n## Sources\n- {page['source']}"
            separator = "\n\n---\n\n" if path.exists() else ""
            with path.open("a", encoding="utf-8") as f:
                f.write(separator + new_body + source_line)
            self.logger.info("%s", name)
        if index_updates:
            self._update_index(index_updates)

    def _build_prompt(
        self, chunk, chunk_index, total_chunks, index, selected, filename
    ):
        examples = "FEW SHOT BEHAVIOR EXAMPLES:\n" + EXAMPLES
        selected_block = "\n".join(f"[[{p}]]" for p in selected)
        return (
            f"EXISTING WIKI PAGES (THIS PDF):\n{index}\n\n"
            f"TARGET PAGES (PRIORITY):\n{selected_block}\n\n---\n\n"
            f"SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})\n\n"
            f"CONTENT:\n{chunk}\n\n{examples}\n\n---\n\n{INGESTION_PROMPT}"
        )

    def _parse_response(self, response: str, filename: str) -> list[dict]:
        response = response.strip()
        match = re.search(
            r"```(?:json)?\s*(.*?)\s*```|(\[.*\]|\{.*\})", response, re.DOTALL
        )
        if match:
            response = match.group(1) or match.group(2)
        try:
            items = json5.loads(response)
            if not isinstance(items, list):
                return []
            return [
                {
                    "source": filename,
                    "path": (
                        "index" if item.get("type") == "index" else item.get("name")
                    ),
                    "content": item.get("content", []),
                }
                for item in items
                if isinstance(item, dict)
                and item.get("type") in ("page", "index")
                and (item.get("name") or item.get("type") == "index")
            ]
        except Exception:
            return []

    def _process_chunk(
        self,
        chunk: str,
        i: int,
        total: int,
        filename: str,
        session_dir: Path,
        local_pages: set,
    ) -> dict:
        if sum(c.isalpha() for c in chunk) / max(len(chunk), 1) < 0.4:
            self.logger.warning("low_text_quality: %s chunk %d", filename, i + 1)
            return {"chunk": i + 1, "status": "skipped_low_quality"}

        local_index, selected = self._build_local_index(local_pages)
        prompt = self._build_prompt(chunk, i, total, local_index, selected, filename)
        self.logger.info("chunk %d/%d prompt_len=%d", i + 1, total, len(prompt))
        response = "".join(self.stream_fn(prompt, system=SCHEMA))
        pages = self._parse_response(response, filename)

        if pages:
            self._write_pages(pages, session_dir)
            local_pages.update(p["path"] for p in pages if p["path"] != "index")
            return {"chunk": i + 1, "status": "ok", "pages": len(pages)}

        self.logger.warning("parse_failed: %s chunk %d", filename, i + 1)
        with (self.WIKI_DIR / "_last_response.txt").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {filename} chunk {i+1} ---\n{response}\n")
        return {"chunk": i + 1, "status": "parse_failed"}

    def execute(self, filename: str, pdf_bytes: bytes) -> dict:
        super()._setup_logger(self.logger, f"INGESTION {filename}")

        try:
            text = self.extract_pdf_text(pdf_bytes)
            self.index_map = self._get_index_map()
            if not text.strip():
                return {
                    "status": "failed",
                    "file": filename,
                    "results": [],
                    "has_low_quality": False,
                    "error": "empty_pdf",
                }

            session_dir = self.WIKI_DIR / "session_001"
            session_dir.mkdir(parents=True, exist_ok=True)
            chunks = self.chunk_text(text)
            local_pages = {p.stem for p in session_dir.glob("*.md")}
            results = [
                self._process_chunk(
                    chunk, i, len(chunks), filename, session_dir, local_pages
                )
                for i, chunk in enumerate(chunks)
            ]

            has_low_quality = any(
                r.get("status") == "skipped_low_quality" for r in results
            )

            return {
                "status": "complete",
                "file": filename,
                "results": results,
                "has_low_quality": has_low_quality,
                "error": None,
            }

        except Exception as e:
            return {
                "status": "failed",
                "file": filename,
                "results": [],
                "has_low_quality": False,
                "error": str(e),
            }

        finally:
            self.close()
