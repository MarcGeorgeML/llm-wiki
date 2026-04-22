from pathlib import Path
import json

from schema import SCHEMA, INGESTION_PROMPT, SELECT_PAGES_SCHEMA_INGESTION, EXAMPLES
from utils.utils import PDFService


class IngestionService(PDFService):

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR = RAW_DIR
        self.stream_fn = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _assign_pages(self, chunk: str, index: str) -> list[str]:
        if not index:
            return []
        prompt = f"CONTENT:\n{chunk}\n\nEXISTING PAGES:\n{index}\n\n"
        response = "".join(self.stream_fn(prompt, system=SELECT_PAGES_SCHEMA_INGESTION))
        try:
            selected = json.loads(response)
        except Exception:
            return []
        valid = {
            line.split("[[")[1].split("]]")[0]
            for line in index.splitlines()
            if "[[" in line
        }
        return [p for p in selected if p in valid]


    def _build_prompt(
        self,
        chunk: str,
        chunk_index: int,
        total_chunks: int,
        index: str,
        selected: list[str],
        filename: str,
    ) -> str:
        examples = "FEW SHOT BEHAVIOR EXAMPLES:\n" + EXAMPLES
        selected_block = "\n".join(f"[[{p}]]" for p in selected)
        return f"EXISTING WIKI PAGES (GLOBAL):\n{index}\n\nTARGET PAGES (PRIORITY):\n{selected_block}\n\n---\n\nSOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})\n\nCONTENT:\n{chunk}\n\n{examples}\n\n---\n\n{INGESTION_PROMPT}"


    def _write_pages(self, pages: list[dict], page_map: dict[str, Path]) -> None:
        self.WIKI_DIR.mkdir(parents=True, exist_ok=True)
        index_updates = {}

        for page in pages:
            if page["path"] == "index":
                for line in page["content"]:
                    if "]] — " in line:
                        name, desc = line.split("]] — ", 1)
                        index_updates[name.replace("[[", "").strip()] = desc.strip()
                continue

            name = page["path"]
            path = (
                page_map.get(name)
                or self.WIKI_DIR / Path(page["source"]).stem / f"{name}.md"
            )
            path.parent.mkdir(exist_ok=True)
            page_map[name] = path

            new_content = f"# {name}\n\n" + "\n\n".join(s.strip() for s in page["content"] if s.strip())
            new_content += f"\n\n## Sources\n- {page['source']}"
            existing = (
                path.read_text(encoding="utf-8").rstrip() + "\n\n"
                if path.exists()
                else ""
            )
            path.write_text(existing + new_content, encoding="utf-8")

        if not index_updates:
            return

        index_path = self.WIKI_DIR / "index.md"
        existing = {}
        if index_path.exists():
            for line in index_path.read_text(encoding="utf-8").splitlines():
                if "]] — " in line:
                    name, desc = line.split("]] — ", 1)
                    existing[name.replace("[[", "").strip()] = desc.strip()
        existing.update(index_updates)
        index_path.write_text(
            "\n".join(f"[[{k}]] — {v}" for k, v in sorted(existing.items())),
            encoding="utf-8",
        )


    def execute(self, filename: str, pdf_bytes: bytes) -> dict:
        text = self.extract_pdf_text(pdf_bytes)
        if not text.strip():
            return {"file": filename, "status": "failed"}

        page_map = self._get_page_map(self.WIKI_DIR)
        chunks = self.chunk_text(text)
        results = []

        for i, chunk in enumerate(chunks):
            index = self._get_index(self.WIKI_DIR)
            prompt = self._build_prompt(chunk, i, len(chunks), index, self._assign_pages(chunk, index), filename)
            response = "".join(self.stream_fn(prompt, system=SCHEMA))
            response = response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            try:
                items = json.loads(response)
                pages = [
                    {"source": filename, "path": "index" if item["type"] == "index" else item["name"], "content": item["content"]}
                    for item in items if item.get("type") in ("page", "index")
                ]
            except Exception:
                pages = []

            if pages:
                self._write_pages(pages, page_map)
                results.append({"chunk": i + 1, "status": "ok", "pages": len(pages)})
            else:
                (self.WIKI_DIR / "_last_response.txt").write_text(response, encoding="utf-8")
                results.append({"chunk": i + 1, "status": "parse_failed"})

        return {"file": filename, "results": results}