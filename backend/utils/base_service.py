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
        if not logger.handlers:
            handler = logging.FileHandler(self.LOG_PATH, mode="a", encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "- %(asctime)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        logger.info(
            "=== %s %s ===", label, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

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

    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
