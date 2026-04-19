import re
from pathlib import Path
import pymupdf as fitz
import easyocr
import numpy as np
from PIL import Image
import io
import cv2
from dotenv import load_dotenv
load_dotenv()


reader = easyocr.Reader(['en'], gpu=True)


def extract_pdf_text(pdf_bytes: bytes) -> str:
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
    return "\n".join(pages_text)


def parse_pages(response: str, filename: str = "source") -> list[dict]:
    first = response.find("===FILE:")
    if first != -1:
        response = response[first:]
    pattern = re.compile(r"===FILE:\s*(.+?)===\n(.*?)===END===", re.DOTALL)
    pages = [{"path": m.group(1).strip(), "content": m.group(2).strip()}
            for m in pattern.finditer(response)]
    if pages:
        return pages
    pattern = re.compile(r"===FILE:\s*(.+?)===\n(.*?)(?====FILE:|\Z)", re.DOTALL)
    pages = [{"path": m.group(1).strip(), "content": m.group(2).strip()}
            for m in pattern.finditer(response)]
    if pages:
        return pages
    stem = Path(filename).stem
    return [
        {"path": f"wiki/{stem}.md", "content": response.strip()},
        {"path": "wiki/index.md",   "content": f"- [[{stem}]] — ingested from {filename}\n"},
    ]