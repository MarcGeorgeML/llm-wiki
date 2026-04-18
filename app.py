from datetime import date
from pathlib import Path
import streamlit as st
import shutil
from dotenv import load_dotenv
load_dotenv()

from schema import SCHEMA, QUESTION_PROMPT, INGESTION_PROMPT, QUERY_PROMPT
from utils.utils import (
    ask_ollama_stream, 
    extract_pdf_text, 
    parse_pages, 
    write_wiki_pages, 
    get_wiki_pages, 
    ask_groq_stream,
    build_ingest_prompt,
    build_query_prompt,
    build_question_prompt)



# ── config ────────────────────────────────────────────────────────────────────
WIKI_DIR   = Path("wiki")
RAW_DIR    = Path("raw")
WIKI_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)
# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="LLM Wiki", page_icon="📖", layout="wide")
st.title("📖 LLM Wiki")

model_choice = st.radio("Model", ["Local (Ollama)", "Cloud (llama-3.3-70b-versatile)"], horizontal=True)

def stream(prompt: str):
    if model_choice == "Cloud (llama-3.3-70b-versatile)":
        yield from ask_groq_stream(prompt)
    else:
        yield from ask_ollama_stream(prompt)

tab_ingest, tab_query, tab_wiki = st.tabs(["Ingest PDFs", "Ask Questions", "Browse Wiki"])

# ── TAB 1: INGEST ─────────────────────────────────────────────────────────────
with tab_ingest:
    st.header("Add PDFs to the Wiki")

    uploaded = st.file_uploader("Upload one or more PDFs", type="pdf", accept_multiple_files=True)

    if st.button("🔄 Clear Wiki (switch subject)", type="secondary"):
        shutil.rmtree(WIKI_DIR)
        WIKI_DIR.mkdir()
        st.success("Wiki cleared. Ready for a new subject.")

    if uploaded and st.button("📥 Ingest Selected PDFs", type="primary"):
        for up_file in uploaded:
            with st.status(f"Processing {up_file.name}...", expanded=True) as status:
                st.write("Extracting text...")
                pdf_bytes = up_file.read()
                text = extract_pdf_text(pdf_bytes)

                if not text.strip():
                    status.update(label=f"⚠️ {up_file.name} — no text found (scanned PDF?)", state="error")
                    continue

                chunks = [text[i:i+20000] for i in range(0, len(text), 20000)]
                st.write(f"Split into {len(chunks)} chunk(s)...")

                for i, chunk in enumerate(chunks):
                    st.write(f"Processing chunk {i+1}/{len(chunks)}...")
                    index_md = (WIKI_DIR / "index.md").read_text(encoding="utf-8") \
                        if (WIKI_DIR / "index.md").exists() else "(empty)"

                    prompt = build_ingest_prompt(
                        chunk=chunk,
                        filename=up_file.name,
                        chunk_index=i,
                        total_chunks=len(chunks),
                        index_md=index_md,
                        schema=SCHEMA,
                        ingestion_prompt=INGESTION_PROMPT
                    )

                    response = "".join(stream(prompt))
                    pages = parse_pages(response, filename=up_file.name)

                    if not pages:
                        (WIKI_DIR / "_last_response.txt").write_text(response, encoding="utf-8")
                        st.warning(f"Chunk {i+1} parse failed — check _last_response.txt")
                    else:
                        write_wiki_pages(pages, WIKI_DIR)
                        st.write(f"✅ Chunk {i+1}/{len(chunks)} — {len(pages)} pages written")

                (RAW_DIR / up_file.name).write_bytes(pdf_bytes)
                status.update(label=f"✅ {up_file.name} — all chunks processed", state="complete")

    st.divider()
    st.subheader("Current Wiki Pages")
    pages = get_wiki_pages(WIKI_DIR=WIKI_DIR)
    if pages:
        for p in pages:
            st.write(f"- `{p.name}`")
    else:
        st.info("No wiki pages yet. Ingest a PDF to get started.")


# ── TAB 2: QUERY ──────────────────────────────────────────────────────────────
with tab_query:
    st.header("Ask Questions")

    mode = st.radio("Mode", ["Type a question", "Upload a PDF with questions"], horizontal=True)

    if mode == "Type a question":
        question = st.text_area("Your question", height=100)
        if st.button("Ask", type="primary") and question.strip():
            
            prompt = build_query_prompt(
                SCHEMA=SCHEMA,
                WIKI_DIR=WIKI_DIR,
                question=question,
                QUERY_PROMPT=QUERY_PROMPT
            )
            st.write_stream(stream(prompt))
            
    else:
        q_pdf = st.file_uploader("Upload PDF containing questions", type="pdf", key="qpdf")
        if st.button("Answer Questions", type="primary") and q_pdf:
            
            prompt = build_question_prompt(
                SCHEMA=SCHEMA,
                WIKI_DIR=WIKI_DIR,
                q_pdf=q_pdf,
                QUESTION_PROMPT=QUESTION_PROMPT
            )
            st.write_stream(stream(prompt))


# ── TAB 3: BROWSE WIKI ────────────────────────────────────────────────────────
with tab_wiki:
    st.header("Browse Wiki")

    pages = get_wiki_pages(WIKI_DIR=WIKI_DIR)
    if not pages:
        st.info("Wiki is empty. Go to Ingest to add PDFs.")
    else:
        selected = st.selectbox("Select a page", [p.name for p in pages])
        if selected:
            content = (WIKI_DIR / selected).read_text(encoding="utf-8")
            st.markdown(content)
            with st.expander("View raw markdown"):
                st.code(content, language="markdown")
