import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from pathlib import Path
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import shutil







# def load_wiki_context(WIKI_DIR: Path) -> str:
#     index_path = WIKI_DIR / "index.md"
#     if not index_path.exists():
#         return "(wiki is empty)"
#     index = index_path.read_text(encoding="utf-8")
#     pages = [f"--- {md.name} ---\n{md.read_text(encoding='utf-8')}"
#             for md in sorted(WIKI_DIR.glob("*.md"))
#             if md.name not in ("index.md", "log.md", "_last_response.txt")]
#     context = f"=== INDEX ===\n{index}\n\n=== PAGES ===\n\n" + "\n\n".join(pages)
#     return context


def get_wiki_pages(WIKI_DIR: Path) -> list[Path]:
    return [p for p in sorted(WIKI_DIR.glob("*.md")) if p.name != "_last_response.txt"]







def clear_chroma(WIKI_DIR: Path):
    global chroma_client, collection
    chroma_dir = WIKI_DIR / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        
    shutil.rmtree(str(WIKI_DIR))

    # recreate client and collection for continued operation
    WIKI_DIR.mkdir(exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir), settings=Settings(allow_reset=True))
    collection = chroma_client.get_or_create_collection("wiki")
    

