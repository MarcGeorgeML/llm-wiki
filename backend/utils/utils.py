
import os
from pathlib import Path
import pymupdf as fitz
import easyocr
import numpy as np
from PIL import Image
import io
import cv2
from dotenv import load_dotenv
load_dotenv()

OCR_GPU = os.getenv("OCR_GPU", "True").lower()
OCR_GPU = True if OCR_GPU == "true" else False


reader = easyocr.Reader(['en'], gpu=OCR_GPU)

class PDFService:

    def extract_pdf_text(self, pdf_bytes: bytes) -> str:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            normal = str(page.get_text()).strip()
            if normal:
                pages_text.append(normal)
            else:
                pix = page.get_pixmap(dpi=250)
                img_bytes = pix.tobytes("png")
                try:
                    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    img_arr = np.array(img)
                except Exception:
                    try:
                        img_arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
                    except Exception:
                        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
                try:
                    result = reader.readtext(img_arr, detail=0)
                except Exception as e:
                    # log and skip OCR on this page if reader fails
                    result = []
                    raise ValueError(f"OCR failed on page: {e}")
                lines: list[str] = []
                for item in result:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, (list, tuple)):
                        lines.extend(str(v) for v in item if isinstance(v, str))
                ocr = "\n".join(lines).strip()
                if ocr:
                    pages_text.append(ocr)
        return "\n\n---PAGE_BREAK---\n\n".join(pages_text)


    def chunk_text(self, text: str, max_chars: int = 3500) -> list[str]:
        pages = text.split("\n\n---PAGE_BREAK---\n\n")
        if len(text) <= max_chars:
            return [text]
        chunks = []
        current = []
        current_len = 0
        for page in pages:
            page_len = len(page)
            # Case 1: single page too large → keep as its own chunk
            if page_len >= max_chars:
                if current:
                    chunks.append("\n\n".join(current))
                    current, current_len = [], 0
                chunks.append(page)
                continue
            # Case 2: accumulate pages until threshold
            if current_len + page_len > max_chars:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            current.append(page)
            current_len += page_len
        if current:
            chunks.append("\n\n".join(current))
        return chunks


    def _get_page_map(self, WIKI_DIR) -> dict[str, Path]:
        return {p.stem: p for p in WIKI_DIR.rglob("*.md") if p.name != "index.md"}


    def _get_index(self, WIKI_DIR) -> str:
        path = WIKI_DIR / "index.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""


    def set_stream(self, stream_fn):
        self.stream_fn = stream_fn

    def parse_index_line(self, line: str) -> tuple[str, str] | None:
        if "[[" in line and "]] — " in line:
            name = line.split("[[")[1].split("]]")[0]
            desc = line.split("]] — ", 1)[1].strip()
            return name, desc
        return None
    
    
