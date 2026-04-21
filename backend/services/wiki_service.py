from pathlib import Path


class WikiService:

    def __init__(self, WIKI_DIR: Path):
        self.WIKI_DIR = WIKI_DIR


    def _resolve_page_path(self, page_name: str) -> Path | None:
        if not self.WIKI_DIR.exists():
            return None
        for p in self.WIKI_DIR.rglob("*.md"):
            if p.name == "index.md":
                continue
            if p.stem == page_name:
                return p
        return None


    def list_pages(self) -> dict:
        if not self.WIKI_DIR.exists():
            return {"status": "ok", "pages": []}
        pages = sorted({
            p.stem
            for p in self.WIKI_DIR.rglob("*.md")
            if p.name != "index.md"
        })
        return {"status": "ok", "pages": pages}


    def get_page_path(self, page_name: str):
        path = self._resolve_page_path(page_name)
        if not path:
            return None
        return path


    def get_page_content(self, page_name: str) -> dict:
        path = self._resolve_page_path(page_name)
        if not path:
            return {"status": "error", "message": f"Page '{page_name}' not found"}
        return {
            "status": "ok",
            "page": page_name,
            "content": path.read_text(encoding="utf-8")
        }