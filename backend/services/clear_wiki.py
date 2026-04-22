from pathlib import Path
import shutil

class ClearWikiService:

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path):
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR  = RAW_DIR

    def execute(self) -> dict:
        if self.WIKI_DIR.exists():
            shutil.rmtree(self.WIKI_DIR)
        self.WIKI_DIR.mkdir()

        if self.RAW_DIR.exists():
            shutil.rmtree(self.RAW_DIR)
        self.RAW_DIR.mkdir()

        return {"status": "cleared"}