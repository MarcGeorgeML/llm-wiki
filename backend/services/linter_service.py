from pathlib import Path
import json
import logging


from schema import CLEANUP_PROMPT
from utils.base_service import BaseService


class LinterService(BaseService):
    def __init__(self, WIKI_DIR: Path, stream_fn):
        super().__init__(WIKI_DIR, stream_fn)
        self.logger = logging.getLogger("wiki.linter")
        self.MAX_MERGE_ITERATIONS = 5

    def _setup_logger(self) -> None:
        super()._setup_logger(self.logger, "LINTER")

    def _top_k_candidates(self, anchor_name, remaining, k=10):
        anchor_desc = (self.index_map.get(anchor_name) or anchor_name).lower()
        anchor_words = set(anchor_desc.split())

        scored = []
        for name, path in remaining.items():
            if name == anchor_name:
                continue

            desc = (self.index_map.get(name) or name).lower()
            words = set(desc.split())

            score = len(anchor_words & words)

            if score > 0:
                scored.append((score, name, path))

        scored.sort(reverse=True)
        return dict((name, path) for score, name, path in scored[:k])

    def _clean_pages(self) -> list[dict]:
        results = []
        index = self.INDEX_PATH.read_text(encoding="utf-8")
        for path in self.WIKI_DIR.rglob("*.md"):
            if path.name in {"index.md", "log.md"} or path.name.startswith("_"):
                continue
            original = path.read_text(encoding="utf-8").strip()
            if not original:
                continue
            try:
                cleaned = "".join(
                    self.stream_fn(
                        f"WIKI INDEX:\n{index}\n\nPAGE TO CLEAN:\n{original}",
                        system=CLEANUP_PROMPT,
                    )
                )
            except Exception as e:
                self.logger.error("clean_failed: %s - %s", path.stem, str(e))
                results.append({"file": path.stem, "status": "clean_failed"})
                continue
            if cleaned.strip():
                path.write_text(cleaned, encoding="utf-8")
                self.logger.info("cleaned: %s", path.stem)
                results.append({"file": path.stem, "status": "cleaned"})
            else:
                results.append({"file": path.stem, "status": "skipped"})
        return results

    def _merge_pages(self, all_files: dict) -> list[dict]:
        results = []
        remaining = dict(all_files)

        while remaining:
            anchor_name, anchor_path = next(iter(remaining.items()))
            candidates = self._top_k_candidates(anchor_name, remaining, k=10)
            remaining.pop(anchor_name)

            if not candidates:
                continue

            anchor_text = anchor_path.read_text(encoding="utf-8")
            for name, path in candidates.items():
                if name not in remaining:
                    continue
                child_text = path.read_text(encoding="utf-8")
                anchor_text = anchor_text.rstrip() + "\n\n---\n\n" + child_text
                path.unlink()
                self._update_index({name: None})
                del remaining[name]
                self.logger.info("merged: %s -> %s", name, anchor_name)
                results.append({"file": name, "status": f"merged into {anchor_name}"})

            anchor_path.write_text(anchor_text, encoding="utf-8")

        return results

    def _flag_orphans(self, files: dict) -> list[dict]:
        linked = set()
        for name, path in files.items():
            for line in path.read_text(encoding="utf-8").splitlines():
                for part in line.split("[[")[1:]:
                    if "]]" in part:
                        raw = part.split("]]")[0]
                        target = raw.split("|")[0].strip()  # handle aliased links
                        if target.lower() != name.lower():  # exclude self-links
                            linked.add(target.lower())

        return [
            {"file": name, "status": "orphan"}
            for name in files
            if name.lower() not in linked
        ]

    def execute(self):
        self._setup_logger()
        results = []
        self.index_map = self._get_index_map()

        try:
            files = self._build_file_map()
            iteration = 0
            while iteration < self.MAX_MERGE_ITERATIONS:
                merge_results = self._merge_pages(files)
                results += merge_results

                if not any("merged into" in r.get("status", "") for r in merge_results):
                    break
                files = self._build_file_map()
                iteration += 1

            results += self._clean_pages()

            files = self._build_file_map()
            results += self._flag_orphans(files)

            return {
                "status": "complete",
                "results": results,
                "skipped": [r["file"] for r in results if r.get("status") == "skipped"],
                "error": None,
            }

        except Exception as e:
            self.logger.exception("linter_failed")
            return {"status": "failed", "results": [], "skipped": [], "error": str(e)}

        finally:
            self.close()
