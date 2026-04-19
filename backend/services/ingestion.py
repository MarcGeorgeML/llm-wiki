from datetime import date
from pathlib import Path
import re
from sentence_transformers import SentenceTransformer
from chromadb.api import ClientAPI


from schema import SCHEMA, INGESTION_PROMPT
from utils.pdf_utils import PDFService


class IngestionService(PDFService):
    
    def __init__(
        self, 
        embedder: SentenceTransformer, 
        collection: ClientAPI, 
        WIKI_DIR: Path, 
        RAW_DIR: Path, 
        stream_fn
    ):
        
        self.embedder = embedder
        self.collection = collection
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR = RAW_DIR
        self.stream_fn  = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _index_wiki_page(self, path: Path) -> None:
        
        content = path.read_text(encoding="utf-8")
        embedding = self.embedder.encode(content).tolist()
        self.collection.upsert(
            ids=[path.stem],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{"filename": path.name}]
        )


    def _parse_pages(self, response: str, filename: str = "source") -> list[dict]:
        pattern = re.compile(r"===\s*File:\s*\[(.+?)\](.+?)\s*===\n(.*?)===END===", re.DOTALL | re.IGNORECASE)
        pages = [{"source": m.group(1).strip(), "path": m.group(2).strip(), "content": m.group(3).strip()} for m in pattern.finditer(response)]
        if pages:
            return pages
            
        return [{"source": filename, "path": Path(filename).stem, "content": response.strip()}]


    def _write_wiki_pages(self, pages: list[dict]) -> None:
        self.WIKI_DIR.mkdir(parents=True, exist_ok=True)
        for page in pages:
            name    = re.sub(r"[^A-Za-z0-9._-]", "_", page.get("path", "page"))
            source  = re.sub(r"[^A-Za-z0-9._-]", "_", Path(page.get("source", "unknown")).stem)
            
            # index and log keep their plain names
            if name in ("index", "log"):
                fname = f"{name}.md"
                
            else:
                fname = f"[{source}]{name}.md"
                
            target  = (self.WIKI_DIR / fname).resolve()
            content = page.get("content", "")
                
                
            if target.name in ("index.md", "log.md") and target.exists():
                target.write_text(target.read_text(encoding="utf-8").rstrip() + "\n\n" + content, encoding="utf-8")
                
            else:
                target.write_text(content, encoding="utf-8")
                
            if target.name not in ("index.md", "log.md", "_last_response.txt"):
                self._index_wiki_page(target)


    def _get_relevant_context(self, chunk: str, max_results: int = 5) -> str:
        if self.collection.count() == 0:
            return "(no existing wiki pages)"
            
        embedding = self.embedder.encode(chunk).tolist()
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(max_results, self.collection.count())
        )
        
        if not results["documents"][0]:
            return "(no relevant pages found)"
            
        pages = [f"--- {meta['filename']} ---\n{doc}"
                for doc, meta in zip(results["documents"][0], results["metadatas"][0])]
                
        return "\n\n".join(pages)


    def build_ingest_prompt(
        self, 
        chunk: str, 
        chunk_index: int, 
        total_chunks: int,
        filename: str = "source"
    ) -> str:
        existing_context = self._get_relevant_context(chunk)
        schema_block = SCHEMA if chunk_index == 0 else "You are a strict wiki maintainer. Same rules and format as before."
        return f"""

{schema_block}
---
EXISTING RELEVANT WIKI PAGES:
{existing_context}

---

SOURCE FILE: {filename} (part {chunk_index+1} of {total_chunks})
CONTENT:
{chunk}

---
{INGESTION_PROMPT}

Today's date: {date.today().isoformat()}
"""

    def execute(self, filename, pdf_bytes: bytes) -> dict:
        text = self.extract_pdf_text(pdf_bytes)
        if not text.strip():
            return {"status": "error", "message": f"{filename} — no text found (scanned PDF?)"}
            
        chunks = [text[i:i+20000] for i in range(0, len(text), 20000)]
        results = []
            
            
        for i, chunk in enumerate(chunks):
            
            prompt = self.build_ingest_prompt(
                chunk=chunk,
                chunk_index=i,
                total_chunks=len(chunks),
                filename=filename
            )
            
            response = "".join(self.stream_fn(prompt))
            pages = self._parse_pages(response, filename=filename)
            
            if not pages:
                (self.WIKI_DIR / "_last_response.txt").write_text(response, encoding="utf-8")
                results.append({"chunk": i+1, "status": "parse_failed"})
            else:
                self._write_wiki_pages(pages)
                results.append({"chunk": i+1, "status": "ok", "pages_written": len(pages)})
        
        self.RAW_DIR.mkdir(exist_ok=True)
        (self.RAW_DIR / filename).write_bytes(pdf_bytes)
        
        return {
            "status": "complete",
            "filename": filename,
            "total_chunks": len(chunks),
            "chunks": results
        }
        

