from datetime import date
from pathlib import Path
import json


from schema import SCHEMA, INGESTION_PROMPT, REUSE_SCHEMA
from utils.pdf_utils import PDFService


class IngestionService(PDFService):
    
    def __init__(
        self, 
        WIKI_DIR: Path, 
        RAW_DIR: Path, 
        stream_fn
    ):
        
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR = RAW_DIR
        self.stream_fn  = stream_fn


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
        
    def _parse_pages(self, response: str, filename: str = "source") -> list[dict]:
        items = json.loads(response)

        return [
            {
                "source": filename,
                "path": "index" if item["type"] == "index" else item["name"],
                "content": item["content"]
            }
            for item in items
        ]


    def _write_wiki_pages(self, pages: list[dict]) -> None:
        self.WIKI_DIR.mkdir(parents=True, exist_ok=True)

        for page in pages:
            content = "\n\n".join(page["content"]).strip()

            if page["path"] == "index":
                path = self.WIKI_DIR / "index.md"
                if path.exists():
                    content = path.read_text(encoding="utf-8").rstrip() + "\n\n" + content
            else:
                folder = self.WIKI_DIR / Path(page["source"]).stem
                folder.mkdir(exist_ok=True)
                path = folder / f"{page['path']}.md"
                if path.exists():
                    content = path.read_text(encoding="utf-8").rstrip() + "\n\n" + content

            path.write_text(content, encoding="utf-8")

    def build_ingest_prompt(
        self, 
        chunk: str, 
        chunk_index: int, 
        total_chunks: int,
        filename: str = "source"
    ) -> str:
        
        hints = self._get_page_hints()
        existing_context = "\n".join(hints) if hints else "(none)"
        
        return f"""
EXISTING WIKI PAGES (name — description):
Use BOTH the name and description to determine relevance.
Reuse page names EXACTLY when the meaning matches.
Do NOT create variations of existing page names.
{existing_context}
---
SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})
CONTENT:
{chunk}
---
{INGESTION_PROMPT}
"""


    def execute(self, pdfs) -> dict:
        if not pdfs:
            return {"status": "error", "message": "No PDFs provided for ingestion"}

        all_results = []
        seen_files = set()
        all_chunks = 0

        for pdf in pdfs:
            pdf_bytes = pdf.read_bytes()
            filename = pdf.name if hasattr(pdf, "name") else "source.pdf"

            text = self.extract_pdf_text(pdf_bytes)
            if not text.strip():
                all_results.append({"file": filename, "status": "failed"})
                continue

            chunks = self.chunk_text(text)
            total = len(chunks)

            for i, chunk in enumerate(chunks):
                prompt = self.build_ingest_prompt(
                    chunk=chunk,
                    chunk_index=i,
                    total_chunks=total,
                    filename=filename
                )

                system_prompt = SCHEMA if i == 0 else REUSE_SCHEMA

                response = "".join(self.stream_fn(prompt, system=system_prompt))
                response = response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                print(response)
                pages = self._parse_pages(response, filename=filename)

                if pages:
                    self._write_wiki_pages(pages)
                    all_results.append({"chunk": i+1, "status": "ok", "pages_written": len(pages)})
                    seen_files.add(filename)
                    all_chunks += 1
                else:
                    self.WIKI_DIR.mkdir(parents=True, exist_ok=True)
                    (self.WIKI_DIR / "_last_response.txt").write_text(response, encoding="utf-8")
                    all_results.append({"chunk": i+1, "status": "parse_failed"})

        return {
            "status": "complete",
            "filenames": list(seen_files),
            "total_chunks": all_chunks,
            "chunks": all_results
        }

