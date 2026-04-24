from pathlib import Path
import json
import logging
from datetime import datetime


from schema import SCHEMA, INGESTION_PROMPT, SELECT_PAGES_SCHEMA_INGESTION, EXAMPLES
from utils.utils import PDFService


class IngestionService(PDFService):

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR = RAW_DIR
        self.INDEX_PATH = self.WIKI_DIR / "index.md"
        self.LOG_PATH = self.WIKI_DIR / "log.md"
        self.stream_fn = stream_fn
        self.logger = logging.getLogger("wiki.ingestion")


    def _setup_logger(self) -> None:
        with self.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n\n=== INGESTION ({datetime.now():%Y-%m-%d %H:%M:%S}) ===\n\n")
            
        if not self.logger.handlers:
            handler = logging.FileHandler(self.LOG_PATH, encoding="utf-8")
            handler.setFormatter(logging.Formatter("- %(asctime)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn
    
    
    def _get_index_map(self) -> dict[str, str]:
        index = {}

        if not self.INDEX_PATH.exists():
            return index

        for line in self.INDEX_PATH.read_text(encoding="utf-8").splitlines():
            if parsed := self.parse_index_line(line):
                name, desc = parsed
                index[name] = desc

        return index


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


    def add_to_page(self, path: Path, new_body: str, page) -> str:
        existing_text = path.read_text(encoding="utf-8").rstrip()
        body, sources_part = (existing_text.rsplit("## Sources", 1)
                                if "## Sources" in existing_text
                                else (existing_text, ""))
        all_sources = {l[2:].strip() for l in sources_part.splitlines() if l.startswith("- ")}
        all_sources.add(page["source"])
        final = body.rstrip() + "\n\n" + new_body
        return final


    def _update_index(self, updates: dict[str, str]) -> None:
        
        for k, v in updates.items():
            self.index_map[k] = v

        self.INDEX_PATH.write_text(
            "\n".join(f"[[{k}]] — {v}" for k, v in sorted(self.index_map.items())),
            encoding="utf-8",
        )

    def _write_pages(self, pages: list[dict], pdf_dir: Path) -> None:
        index_updates = {}
        
        for page in pages:
            if page["path"] == "index":
                for line in page["content"]:
                    if parsed := self.parse_index_line(line):
                        index_updates[parsed[0]] = parsed[1]
                continue
            
            name = page["path"]
            path = pdf_dir / f"{name}.md"
            path.parent.mkdir(exist_ok=True)
            
            new_body = f"# {name}\n\n" + "\n\n".join(s.strip() for s in page["content"] if s.strip())
            
            if path.exists():
                final = self.add_to_page(path, new_body, page)
            else:
                all_sources = {page["source"]}
                final = new_body

            final += "\n\n## Sources\n" + "\n".join(f"- {s}" for s in sorted(all_sources))
            path.write_text(final, encoding="utf-8")
            self.logger.info("%s/%s", path.parent.name, name)

        if index_updates:
            self._update_index(index_updates)


    def _build_prompt(self, chunk, chunk_index, total_chunks, index, selected, filename):
        examples = "FEW SHOT BEHAVIOR EXAMPLES:\n" + EXAMPLES
        selected_block = "\n".join(f"[[{p}]]" for p in selected)
        return (
            f"EXISTING WIKI PAGES (THIS PDF):\n{index}\n\n"
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


    def _process_chunk(self, chunk: str, i: int, total: int, filename: str, pdf_dir: Path, local_pages: set) -> dict:
        alpha_count = sum(c.isalpha() for c in chunk)
        if alpha_count / len(chunk) < 0.4:
            self.logger.warning("low_text_quality: %s chunk %d", filename, i + 1)
            return {"chunk": i + 1, "status": "skipped_low_quality"}
        
        valid_pages = [p for p in local_pages if p in self.index_map]

        if len(valid_pages) >= 3:
            local_index = "\n".join(f"[[{p}]] — {self.index_map[p]}" for p in valid_pages)
            valid_set = set(valid_pages)
            selected = self._assign_pages(chunk, local_index, valid_set)
        else:
            local_index = ""
            selected = list(local_pages)
            
        prompt = self._build_prompt(
            chunk,
            i,
            total,
            local_index,
            selected,
            filename
        )
        
        self.logger.info("chunk %d/%d prompt_len=%d", i + 1, total, len(prompt))
        response = "".join(self.stream_fn(prompt, system=SCHEMA))
        pages = self._parse_response(response, filename)
        
        if pages:
            self._write_pages(pages, pdf_dir)
            for page in pages:
                if page["path"] != "index":
                    local_pages.add(page["path"])
            return {"chunk": i + 1, "status": "ok", "pages": len(pages)}
        
        self.logger.warning("parse_failed: %s chunk %d", filename, i + 1)
        with (self.WIKI_DIR / "_last_response.txt").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {filename} chunk {i+1} ---\n{response}\n")
        return {"chunk": i + 1, "status": "parse_failed"}


    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


    def execute(self, filename: str, pdf_bytes: bytes) -> dict:
        self._setup_logger()
        text = self.extract_pdf_text(pdf_bytes)
        self.index_map = self._get_index_map()
        
        if not text.strip():
            return {"file": filename, "status": "failed"}
        
        pdf_dir = self.WIKI_DIR / Path(filename).stem
        pdf_dir.mkdir(parents=True, exist_ok=True)
        chunks = self.chunk_text(text)
        local_pages = {p.stem for p in pdf_dir.glob("*.md")}
        results = [
            self._process_chunk(chunk, i, len(chunks), filename, pdf_dir, local_pages)
            for i, chunk in enumerate(chunks)
        ]
        
        low_quality_chunks = [r["chunk"] for r in results if r["status"] == "skipped_low_quality"]
        
        self.close()
        
        return {
            "file": filename, 
            "results": results,
            "has_low_quality": len(low_quality_chunks) > 0
        }


