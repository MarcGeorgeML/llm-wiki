import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from pathlib import Path
import streamlit as st


from sentence_transformers import SentenceTransformer
import chromadb

def load_models():
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    chroma_client = chromadb.PersistentClient(path="wiki/chroma_db")
    collection = chroma_client.get_or_create_collection("wiki")
    return embedder, chroma_client, collection

embedder, chroma_client, collection = load_models()


def write_wiki_pages(pages: list[dict], WIKI_DIR: Path):
    for page in pages:
        path = (Path.cwd() / page["path"]).resolve()
        if not str(path).startswith(str(WIKI_DIR.resolve())):
            st.warning(f"Skipped suspicious path: {page['path']}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "log.md" and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + "\n\n" + page["content"], encoding="utf-8")
        else:
            path.write_text(page["content"], encoding="utf-8")
        if path.name not in ("index.md", "log.md", "_last_response.txt"):
            index_wiki_page(path)


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


def index_wiki_page(path: Path):
    content = path.read_text(encoding="utf-8")
    embedding = embedder.encode(content).tolist()
    collection.upsert(
        ids=[path.stem],
        embeddings=[embedding],
        documents=[content],
        metadatas=[{"filename": path.name}]
    )


def load_relevant_wiki_context(WIKI_DIR: Path, question: str, max_pages: int = 5) -> str:
    index_path = WIKI_DIR / "index.md"
    index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    if collection.count() == 0:
        return f"=== INDEX ===\n{index}\n\n=== PAGES ===\n\n(no pages indexed yet)"

    question_embedding = embedder.encode(question).tolist()
    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=min(max_pages, collection.count())
    )

    docs = results.get("documents") if isinstance(results, dict) else None
    metas = results.get("metadatas") if isinstance(results, dict) else None
    if not docs or not metas or not docs[0]:
        return f"=== INDEX ===\n{index}\n\n=== RELEVANT PAGES ===\n\n(no results)"

    pages = [
        f"--- {meta.get('filename','unknown.md')} ---\n{doc}"
        for doc, meta in zip(docs[0], metas[0])
    ]

    return f"=== INDEX ===\n{index}\n\n=== RELEVANT PAGES ===\n\n" + "\n\n".join(pages)


def clear_chroma():
    global collection
    chroma_client.delete_collection("wiki")
    collection = chroma_client.get_or_create_collection("wiki")

