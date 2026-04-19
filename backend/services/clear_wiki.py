from pathlib import Path
import shutil
from chromadb.api import ClientAPI
from services.ingestion import IngestionService

class ClearWikiService:

    def __init__(self, WIKI_DIR: Path, RAW_DIR: Path):
        self.WIKI_DIR = WIKI_DIR
        self.RAW_DIR  = RAW_DIR

    def execute(self, chroma_client: ClientAPI, ingestion_service: IngestionService) -> dict:
        if self.WIKI_DIR.exists():
            shutil.rmtree(self.WIKI_DIR)
        self.WIKI_DIR.mkdir()

        # if self.RAW_DIR.exists():
        #     shutil.rmtree(self.RAW_DIR)
        # self.RAW_DIR.mkdir()

        chroma_client.delete_collection("wiki")
        new_collection = chroma_client.get_or_create_collection("wiki")
        ingestion_service.collection = new_collection

        return {"status": "cleared"}