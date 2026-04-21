from pathlib import Path

from schema import CLEANUP_PROMPT

class CleanupService:
    def __init__(self, WIKI_DIR: Path, stream_fn):
        self.WIKI_DIR = WIKI_DIR
        self.stream_fn = stream_fn


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn


    def _clean_page(self, content: str) -> str:
        prompt = f"""
{CLEANUP_PROMPT}
INPUT PAGE:
{content}
"""
        return prompt


    def execute(self):
        result = []
        for path in self.WIKI_DIR.rglob("*.md"):
            print(f"Cleaning: {path.name}")
            if path.name == "index.md":
                continue

            original = path.read_text(encoding="utf-8").strip()
            if not original:
                continue
            
            prompt = self._clean_page(original)
            cleaned = "".join(self.stream_fn(prompt))

            # safety: only overwrite if result is non-empty and not drastically smaller
            ratio = len(cleaned) / len(original) if original else 1
            if cleaned and 0.6 <= ratio <= 1.05:
                path.write_text(cleaned, encoding="utf-8")
                status = "ok"
            else:
                status = "skipped"
            
            result.append(
                {
                    "file": str(path.relative_to(self.WIKI_DIR)),
                    "status": status,
                    "original_length": len(original),
                    "cleaned_length": len(cleaned)
                }
            )
            
            return {
                "status": "complete",
                "number of files cleaned": len(result),
                "files": result
            }
