import json
import logging
from datetime import datetime
from pathlib import Path


from utils.file_utils import FileService
from utils.ocr_utils import OCRService


class BaseService(FileService, OCRService):
    def __init__(self, WIKI_DIR: Path, stream_fn):
        FileService.__init__(self, WIKI_DIR)
        self.stream_fn = stream_fn
        self.logger = logging.getLogger("wiki.base")

    def set_stream(self, stream_fn) -> None:
        self.stream_fn = stream_fn

    def _setup_logger(self, logger: logging.Logger, label: str) -> None:
        self.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        if not logger.handlers:
            handler = logging.FileHandler(self.LOG_PATH, mode="a", encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "- %(asctime)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

        # write header without formatter
        with open(self.LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"=== {label} ===\n")

    def _select_pages(
        self, prompt: str, system: str, valid: set[str], max_pages: int | None = None
    ) -> list[str]:
        if not valid:
            return []
        response = "".join(self.stream_fn(prompt, system=system))
        try:
            selected = json.loads(response)
        except Exception:
            return []
        result = [p for p in selected if p in valid]
        return result[:max_pages] if max_pages else result

    def _top_k_pages(self, text: str, pages: list[str], k: int = 10) -> list[str]:
        text_words = set(text.lower().split())
        scored = sorted(
            [(len(text_words & set((self.index_map.get(p) or p).lower().split())), p) for p in pages],
            reverse=True
        )
        return [p for score, p in scored[:k] if score > 0]

    def close(self) -> None:
        self.logger.info("=== SESSION END ===\n\n\n")
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
