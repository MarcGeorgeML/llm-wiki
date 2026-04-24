from pathlib import Path
import json
import logging


from schema import CLEANUP_PROMPT, PRUNE_PROMPT, PRUNE_CANDIDATES_PROMPT
from utils.utils import PDFService

class Linter(PDFService):
    def __init__(self, WIKI_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
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


    def _find_orphans(self, page_map: dict) -> set[str]:
        valid = set()
        for path in self.WIKI_DIR.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                for link in line.split("[[")[1:]:
                    if "]]" in link:
                        valid.add(link.split("]]")[0])
        return set(page_map.keys()) - valid


    def _clean_pages(self, index: str) -> list[dict]:
        results = []
        for path in self.WIKI_DIR.rglob("*.md"):
            if path.name == "index.md":
                continue
            original = path.read_text(encoding="utf-8").strip()
            if not original:
                continue
            cleaned = "".join(self.stream_fn(f"WIKI INDEX:\n{index}\n\nPAGE TO CLEAN:\n{original}", system=CLEANUP_PROMPT))
            if cleaned.strip():
                path.write_text(cleaned, encoding="utf-8")
                self.logger.info("edited: %s/%s", path.parent.name, path.stem)
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "cleaned"})
            else:
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "skipped"})
        return results


    def _prune_pages(self, index: str) -> list[dict]:
        results = []
        try:
            candidate_pairs = json.loads("".join(self.stream_fn(f"WIKI INDEX:\n{index}", system=PRUNE_CANDIDATES_PROMPT)))
        except Exception:
            candidate_pairs = []

        page_map = self._get_page_map(self.WIKI_DIR)
        to_delete = []
        for pair in candidate_pairs:
            if len(pair) != 2:
                continue
            name_a, name_b = pair
            if name_a not in page_map or name_b not in page_map:
                continue
            prompt = f"[PAGE: {name_a}]\n{page_map[name_a].read_text(encoding='utf-8')}\n\n[PAGE: {name_b}]\n{page_map[name_b].read_text(encoding='utf-8')}"
            try:
                to_delete.extend(json.loads("".join(self.stream_fn(prompt, system=PRUNE_PROMPT))))
            except Exception:
                pass

        for name in to_delete:
            for path in self.WIKI_DIR.rglob(f"{name}.md"):
                self.logger.info("deleted: %s/%s", path.parent.name, name)
                path.unlink()
                results.append({"file": name, "status": "deleted"})
        return results


    def _flag_orphans(self) -> list[dict]:
        page_map = self._get_page_map(self.WIKI_DIR)
        return [{"file": name, "status": "orphan"} for name in self._find_orphans(page_map)]


    def execute(self):
        self._setup_logger()
        results  = self._clean_pages(self._get_index(self.WIKI_DIR))
        results += self._prune_pages(self._get_index(self.WIKI_DIR))
        results += self._flag_orphans()
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        return {"status": "complete", "files": results}


    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)