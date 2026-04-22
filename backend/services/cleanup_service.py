from pathlib import Path
import json


from schema import CLEANUP_PROMPT, PRUNE_PROMPT
from utils.utils import PDFService

class CleanupService(PDFService):
    def __init__(self, WIKI_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.stream_fn = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _find_orphans(self, page_map: dict) -> set[str]:
        all_links = set()
        for path in self.WIKI_DIR.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                for link in line.split("[[")[1:]:
                    if "]]" in link:
                        all_links.add(link.split("]]")[0])
        return set(page_map.keys()) - all_links


    def execute(self):
        index = self._get_index(self.WIKI_DIR)
        page_map = self._get_page_map(self.WIKI_DIR)
        results = []

        # Phase 1 — clean each page
        for path in self.WIKI_DIR.rglob("*.md"):
            if path.name == "index.md":
                continue
            original = path.read_text(encoding="utf-8").strip()
            if not original:
                continue

            prompt = f"WIKI INDEX:\n{index}\n\nPAGE TO CLEAN:\n{original}"
            cleaned = "".join(self.stream_fn(prompt, system=CLEANUP_PROMPT))

            if cleaned.strip():
                path.write_text(cleaned, encoding="utf-8")
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "cleaned"})
            else:
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "skipped"})

        # Phase 2 — prune irrelevant or redundant pages
        response = "".join(self.stream_fn(f"WIKI INDEX:\n{index}", system=PRUNE_PROMPT))
        try:
            to_delete = json.loads(response)
        except Exception:
            to_delete = []

        for name in to_delete:
            for path in self.WIKI_DIR.rglob(f"{name}.md"):
                path.unlink()
                results.append({"file": name, "status": "deleted"})

        # Phase 3 — flag orphans (no LLM, purely programmatic)
        page_map = self._get_page_map(self.WIKI_DIR)
        orphans = self._find_orphans(page_map)
        for name in orphans:
            results.append({"file": name, "status": "orphan"})

        return {"status": "complete", "files": results}