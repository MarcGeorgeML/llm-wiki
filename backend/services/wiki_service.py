from pathlib import Path
from utils.file_utils import FileService


class WikiService(FileService):
    def __init__(self, WIKI_DIR: Path):
        FileService.__init__(self, WIKI_DIR)

    def resolve_page_path(self, page_name: str) -> Path | None:
        if not self.WIKI_DIR.exists():
            return None
        return self._build_file_map().get(page_name)

    def list_pages(self) -> dict:
        if not self.WIKI_DIR.exists():
            return {"status": "ok", "pages": []}
        return {"status": "ok", "pages": sorted(self._build_file_map().keys())}

    def get_page_content(self, page_name: str) -> dict:
        path = self.resolve_page_path(page_name)
        if not path:
            return {"status": "error", "message": f"Page '{page_name}' not found"}
        return {
            "status": "ok",
            "page": page_name,
            "content": path.read_text(encoding="utf-8"),
        }
