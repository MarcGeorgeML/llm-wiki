from sentence_transformers import SentenceTransformer
from pathlib import Path
from chromadb.api import ClientAPI
from transformers import Any


from schema import SCHEMA


class QueryService:


    def __init__(
        self, 
        embedder: SentenceTransformer, 
        collection: ClientAPI, 
        WIKI_DIR: Path,
    ):
        
        self.embedder = embedder
        self.collection = collection
        self.WIKI_DIR = WIKI_DIR    


    def load_relevant_wiki_context(self,  question: str, max_pages: int = 5) -> str:
        index_path = self.WIKI_DIR / "index.md"
        index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

        if self.collection.count() == 0:
            return f"=== INDEX ===\n{index}\n\n=== PAGES ===\n\n(no pages indexed yet)"

        question_embedding = self.embedder.encode(question).tolist()
        results = self.collection.query(
            query_embeddings=[question_embedding],
            n_results=min(max_pages, self.collection.count())
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


    def build_query_prompt(self, query: str, QUERY_PROMPT: str) -> str:
        context = self.load_relevant_wiki_context(question=query)
        return f"""
    {SCHEMA}

    ---
    WIKI CONTENT (this is ALL you know — do not use outside knowledge):
    {context}
    ---
    QUESTION: {query}

    ---
    {QUERY_PROMPT}
    """


    def build_question_prompt(self, q_pdf: Any, QUESTION_PROMPT: str, q_text: str) -> str:
        context = self.load_relevant_wiki_context(question=q_text)
        return f"""
    {SCHEMA}

    ---
    WIKI CONTENT (this is ALL you know — do not use outside knowledge):
    {context}

    ===
    {QUESTION_PROMPT}

    ---
    QUESTION DOCUMENT ({q_pdf.name}):
    {q_text[:40000]}
    """