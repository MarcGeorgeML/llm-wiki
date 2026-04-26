from pathlib import Path
import re
import json5
import logging


from schema import INGESTION_PROMPT, EXAMPLES
from utils.base_service import BaseService


class IngestionService(BaseService):

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path, stream_fn):
        super().__init__(WIKI_DIR, stream_fn)
        self.RAW_DIR = RAW_DIR
        self._failed_chunks = {}
        self.logger = logging.getLogger("wiki.ingestion")

    def _build_local_index(self, local_pages: set, chunk: str, k: int = 10) -> str:
        valid = [p for p in local_pages if p in self.index_map]
        if not valid:
            return ""
        top = self._top_k_pages(chunk, valid, k)
        return "\n".join(f"[[{p}]] — {self.index_map[p]}" for p in top)

    def _write_pages(self, pages: list[dict], session_dir: Path) -> None:
        index_updates = {}
        written = 0
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
            written += 1
            source_line = f"\n\n## Sources\n- {page['source']}"
            separator = "\n\n---\n\n" if path.exists() else ""
            with path.open("a", encoding="utf-8") as f:
                f.write(separator + new_body + source_line)
        self.logger.info("written %d pages", written)
        if index_updates:
            self._update_index(index_updates)

    def _build_prompt(self, chunk, chunk_index, total_chunks, index, filename):
        examples = "FEW SHOT BEHAVIOR EXAMPLES:\n" + EXAMPLES
        return (
            f"RELEVANT WIKI PAGES (THIS PDF):\n{index}\n\n---\n\n"
            f"SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})\n\n"
            f"CONTENT:\n{chunk}\n\n{examples}\n\n---\n\n{INGESTION_PROMPT}"
        )

    def _repair_json(self, response: str) -> str:
        stack = []
        in_string = False
        escape = False
        for char in response:
            if escape:
                escape = False
                continue
            if char == '\\' and in_string:
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char in '{[':
                stack.append(char)
            elif char == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif char == ']' and stack and stack[-1] == '[':
                stack.pop()
        closing = {'[': ']', '{': '}'}
        return response.rstrip() + ''.join(closing[c] for c in reversed(stack))

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
        
        local_index = self._build_local_index(local_pages, chunk)
        prompt = self._build_prompt(chunk, i, total, local_index, filename)
        self.logger.info("chunk %d/%d prompt_len=%d", i + 1, total, len(prompt))
        response = "".join(self.stream_fn(prompt, system="Output only valid JSON arrays. No explanations."))
        pages = self._parse_response(response, filename)
        if pages:
            self._write_pages(pages, session_dir)
            local_pages.update(p["path"] for p in pages if p["path"] != "index")
            self.index_map = self._get_index_map()
            return {"chunk": i + 1, "status": "ok", "pages": len(pages)}
        self.logger.warning("parse_failed: %s chunk %d", filename, i + 1)

        self._failed_chunks[i + 1] = response
        with (self.SESSION_DIR / "_last_response.txt").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {filename} chunk {i+1} ---\n{response}\n")
        return {"chunk": i + 1, "status": "parse_failed"}

    def _recover_failed(self, session_dir: Path, filename: str) -> list[dict]:
        results = []
        for chunk_num, response in self._failed_chunks.items():
            repaired = self._repair_json(response)
            pages = self._parse_response(repaired, filename)
            if pages:
                self._write_pages(pages, session_dir)
                self.logger.info("recovered: %s chunk %d", filename, chunk_num)
                results.append({"chunk": chunk_num, "status": "recovered"})
            else:
                self.logger.warning("unrecoverable: %s chunk %d", filename, chunk_num)
                results.append({"chunk": chunk_num, "status": "unrecoverable"})
        self._failed_chunks.clear()
        return results

    def execute(self, filename: str, pdf_bytes: bytes) -> dict:
        super()._setup_logger(self.logger, f"INGESTION {filename}")
        self._failed_chunks = {}

        try:
            text, failed_pages  = self.extract_pdf_text(pdf_bytes)
            if failed_pages:
                self.logger.warning("ocr_failed_pages: %s count=%d", filename, failed_pages)
            if not text.strip():
                self.logger.warning("empty_pdf: %s", filename)
                return {
                    "status": "failed",
                    "file": filename,
                    "results": [],
                    "failed_ocr_pages": failed_pages,
                    "error": "empty_pdf",
                }

            self.index_map = self._get_index_map() 
            chunks = self.chunk_text(text)
            local_pages = {p.stem for p in self.SESSION_DIR.glob("*.md") if p.name not in {"index.md", "log.md"} and not p.name.startswith("_")}
            results = [
                self._process_chunk(
                    chunk, i, len(chunks), filename, self.SESSION_DIR, local_pages
                )
                for i, chunk in enumerate(chunks)
            ]
            results += self._recover_failed(self.SESSION_DIR, filename)

            has_low_quality = any(
                r.get("status") == "skipped_low_quality" for r in results
            )

            return {
                "status": "complete",
                "file": filename,
                "results": results,
                "has_low_quality": has_low_quality,
                "failed_ocr_pages": failed_pages,
                "error": None,
            }

        except Exception as e:
            return {
                "status": "failed",
                "file": filename,
                "results": [],
                "has_low_quality": False,
                "failed_ocr_pages": 0,
                "error": str(e),
            }

        finally:
            self.close()
