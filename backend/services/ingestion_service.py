from pathlib import Path
import json
import logging

from schema import SCHEMA, INGESTION_PROMPT, SELECT_PAGES_SCHEMA_INGESTION, EXAMPLES
from utils.utils import PDFService


class IngestionService(PDFService):

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR = RAW_DIR
        self.stream_fn = stream_fn
        self.logger = logging.getLogger("wiki.ingestion")


    def _setup_logger(self) -> None:
        if not self.logger.handlers:
            handler = logging.FileHandler(self.WIKI_DIR / "log.md", encoding="utf-8")
            handler.setFormatter(logging.Formatter("- %(asctime)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _assign_pages(self, chunk: str, index: str, valid: set[str]) -> list[str]:
        if not index:
            return []
        prompt = f"CONTENT:\n{chunk}\n\nEXISTING PAGES:\n{index}\n\n"
        response = "".join(self.stream_fn(prompt, system=SELECT_PAGES_SCHEMA_INGESTION))
        try:
            selected = json.loads(response)
        except Exception:
            return []
        return [p for p in selected if p in valid]


    def _merge_page(self, path: Path, name: str, new_body: str, source: str) -> None:
        if path.exists():
            existing_text = path.read_text(encoding="utf-8").rstrip()
            body, sources_part = existing_text.rsplit("## Sources", 1) if "## Sources" in existing_text else (existing_text, "")
            all_sources = {l[2:].strip() for l in sources_part.splitlines() if l.startswith("- ")}
            final = body.rstrip() + "\n\n" + new_body
        else:
            all_sources = set()
            final = new_body
        all_sources.add(source)
        final += "\n\n## Sources\n" + "\n".join(f"- {s}" for s in sorted(all_sources))
        path.write_text(final, encoding="utf-8")


    def _update_index(self, updates: dict[str, str]) -> None:
        index_path = self.WIKI_DIR / "index.md"
        existing = {}
        if index_path.exists():
            for line in index_path.read_text(encoding="utf-8").splitlines():
                if parsed := self.parse_index_line(line):
                    existing[parsed[0]] = parsed[1]
        existing.update(updates)
        index_path.write_text(
            "\n".join(f"[[{k}]] — {v}" for k, v in sorted(existing.items())),
            encoding="utf-8",
        )


    def _write_pages(self, pages: list[dict], page_map: dict[str, Path]) -> None:
        self.WIKI_DIR.mkdir(parents=True, exist_ok=True)
        index_updates = {}
        for page in pages:
            if page["path"] == "index":
                for line in page["content"]:
                    if parsed := self.parse_index_line(line):
                        index_updates[parsed[0]] = parsed[1]
                continue
            name = page["path"]
            path = page_map.get(name) or self.WIKI_DIR / Path(page["source"]).stem / f"{name}.md"
            path.parent.mkdir(exist_ok=True)
            page_map[name] = path
            new_body = f"# {name}\n\n" + "\n\n".join(s.strip() for s in page["content"] if s.strip())
            self._merge_page(path, name, new_body, page["source"])
            self.logger.info("%s/%s", path.parent.name, name)
        if index_updates:
            self._update_index(index_updates)


    def _build_prompt(self, chunk, chunk_index, total_chunks, index, selected, filename):
        examples = "FEW SHOT BEHAVIOR EXAMPLES:\n" + EXAMPLES
        selected_block = "\n".join(f"[[{p}]]" for p in selected)
        return (
            f"EXISTING WIKI PAGES (GLOBAL):\n{index}\n\n"
            f"TARGET PAGES (PRIORITY):\n{selected_block}\n\n---\n\n"
            f"SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})\n\n"
            f"CONTENT:\n{chunk}\n\n{examples}\n\n---\n\n{INGESTION_PROMPT}"
        )


    def _parse_response(self, response: str, filename: str) -> list[dict]:
        response = response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            items = json.loads(response)
            return [
                {"source": filename, "path": "index" if item["type"] == "index" else item["name"], "content": item["content"]}
                for item in items if item.get("type") in ("page", "index")
            ]
        except Exception:
            return []


    def _process_chunk(self, chunk: str, i: int, total: int, filename: str, page_map: dict) -> dict:
        if len([c for c in chunk if c.isalpha()]) / max(len(chunk), 1) < 0.4:
            self.logger.warning("low_text_quality: %s chunk %d", filename, i + 1)
            return {"chunk": i + 1, "status": "skipped_low_quality"}
        index = self._get_index(self.WIKI_DIR)
        valid = {parsed[0] for line in index.splitlines() if (parsed := self.parse_index_line(line))}
        prompt = self._build_prompt(chunk, i, total, index, self._assign_pages(chunk, index, valid), filename)
        self.logger.info("chunk %d/%d prompt_len=%d", i + 1, total, len(prompt))
        response = "".join(self.stream_fn(prompt, system=SCHEMA))
        pages = self._parse_response(response, filename)
        if pages:
            self._write_pages(pages, page_map)
            return {"chunk": i + 1, "status": "ok", "pages": len(pages)}
        self.logger.warning("parse_failed: %s chunk %d", filename, i + 1)
        with (self.WIKI_DIR / "_last_response.txt").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {filename} chunk {i+1} ---\n{response}\n")
        return {"chunk": i + 1, "status": "parse_failed"}


    def execute(self, filename: str, pdf_bytes: bytes) -> dict:
        self._setup_logger()
        text = self.extract_pdf_text(pdf_bytes)
        if not text.strip():
            return {"file": filename, "status": "failed"}
        page_map = self._get_page_map(self.WIKI_DIR)
        chunks = self.chunk_text(text)
        results = [self._process_chunk(chunk, i, len(chunks), filename, page_map) for i, chunk in enumerate(chunks)]
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        return {"file": filename, "results": results}


    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)