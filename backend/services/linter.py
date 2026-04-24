from pathlib import Path
import json
import logging
from datetime import datetime
from collections import defaultdict


from schema import CLEANUP_PROMPT, MERGE_PROMPT, PRUNE_CANDIDATES_PROMPT
from utils.utils import PDFService

class Linter(PDFService):
    def __init__(self, WIKI_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.INDEX_PATH = self.WIKI_DIR / "index.md"
        self.LOG_PATH = self.WIKI_DIR / "log.md"
        self.folder_map = defaultdict(dict)
        self.stream_fn = stream_fn
        self.logger = logging.getLogger("wiki.linter")


    def _setup_logger(self) -> None:
        with self.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n\n=== LINTER ({datetime.now():%Y-%m-%d %H:%M:%S}) ===\n\n")
        if not self.logger.handlers:
            handler = logging.FileHandler(self.LOG_PATH, encoding="utf-8")
            handler.setFormatter(logging.Formatter("- %(asctime)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _find_orphans(self, page_map: dict) -> set[str]:
        valid = set()

        for path in page_map.values():
            for line in path.read_text(encoding="utf-8").splitlines():
                for link in line.split("[[")[1:]:
                    if "]]" in link:
                        valid.add(link.split("]]")[0])

        return set(page_map.keys()) - valid


    def _get_index_map(self) -> dict[str, str]:
        index = {}
        for line in self.INDEX_PATH.read_text(encoding="utf-8").splitlines():
            if parsed := self.parse_index_line(line):
                index[parsed[0]] = parsed[1]
        return index


    def _clean_pages(self) -> list[dict]:
        results = []
        index = self.INDEX_PATH.read_text(encoding="utf-8")
        for path in self.WIKI_DIR.rglob("*.md"):
            if path.name == "index.md":
                continue
            original = path.read_text(encoding="utf-8").strip()
            if not original:
                continue
            cleaned = "".join(self.stream_fn(f"WIKI INDEX:\n{index}\n\nPAGE TO CLEAN:\n{original}", system=CLEANUP_PROMPT))
            if cleaned.strip():
                path.write_text(cleaned, encoding="utf-8")
                self.logger.info("cleaned: %s/%s", path.parent.name, path.stem)
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "cleaned"})
            else:
                results.append({"file": str(path.relative_to(self.WIKI_DIR)), "status": "skipped"})
        return results


    def _merge_pages(self, all_files: dict) -> list[dict]:
        results = []

        folder_index = "\n".join(
            f"[[{name}]] — {desc}"
            for name, desc in self.index_map.items()
            if name in all_files
        )
        try:
            candidate_pairs = json.loads("".join(self.stream_fn(f"WIKI INDEX:\n{folder_index}", system=PRUNE_CANDIDATES_PROMPT)))
        except Exception:
            candidate_pairs = []

        for pair in candidate_pairs:
            if len(pair) != 2:
                continue
            
            name_a, name_b = pair
            if name_a not in all_files or name_b not in all_files:
                continue
            
            prompt = (
                f"[PAGE: {name_a}]\n{all_files[name_a].read_text(encoding='utf-8')}\n\n"
                f"[PAGE: {name_b}]\n{all_files[name_b].read_text(encoding='utf-8')}"
            )
            response = None
            try:
                response = json.loads("".join(self.stream_fn(prompt, system=MERGE_PROMPT)))
            except Exception:
                continue
            
            if not response:
                continue
            
            parent = response.get("parent")
            child = response.get("child")
            content = response.get("content", "").strip()
            
            if parent not in all_files or child not in all_files or not content:
                continue
            
            parent_path = all_files[parent]
            child_path = all_files[child]
            
            if content:
                parent_text = parent_path.read_text(encoding="utf-8").rstrip()
                merged_text = parent_text + "\n\n" + content + "\n"
                parent_path.write_text(merged_text, encoding="utf-8")
                
                self.logger.info("merged: %s -> %s", child, parent)
                results.append({
                    "file": child,
                    "status": f"merged into {parent}"
                })
                
                child_path.unlink()
                self.logger.info("deleted: %s/%s", child_path.parent.name, child)
                self._update_index({child: None})
                results.append({"file": child, "status": "deleted"})
        return results


    def _update_index(self, updates: dict[str, str | None]) -> None:
        index_path = self.WIKI_DIR / "index.md"

        for key, value in updates.items():
            if value is None:
                self.index_map.pop(key, None)  # delete entry
            else:
                self.index_map[key] = value

        index_path.write_text(
            "\n".join(f"[[{k}]] — {v}" for k, v in sorted(self.index_map.items())),
            encoding="utf-8",
        )


    def _flag_orphans(self, all_files: dict) -> list[dict]:
        return [{"file": name, "status": "orphan"} for name in self._find_orphans(all_files)]


    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


    def execute(self):
        self._setup_logger()
        results = []
        self.folder_map = defaultdict(dict)

        for p in self.WIKI_DIR.rglob("*.md"):
            if p.name == "index.md":
                continue
            folder = p.parent.name
            self.folder_map[folder][p.stem] = p
        self.index_map = self._get_index_map()
        
        for _, files in self.folder_map.items():
            results += self._merge_pages(files)

        self.folder_map = defaultdict(dict)
        for p in self.WIKI_DIR.rglob("*.md"):
            if p.name == "index.md":
                continue
            folder = p.parent.name
            self.folder_map[folder][p.stem] = p
        
        results  += self._clean_pages()
        
        for _, files in self.folder_map.items():
            results += self._flag_orphans(files)
        
        self.close()
        return {"status": "complete", "files": results}


