import hashlib
import io
from pathlib import Path
from typing import Dict, Any, List, Tuple
import fitz  # PyMuPDF
from PIL import Image
import imagehash
from backend.app.config import RENDER_CACHE_DIR, settings
from backend.app.security import load_decrypted_file

class DocumentLoader:
    @staticmethod
    def load_document_bytes(encrypted_path: Path) -> bytes:
        return load_decrypted_file(encrypted_path)

    @staticmethod
    def inspect_and_render_pdf(
        pdf_bytes: bytes,
        doc_id: str,
        dpi: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Inspects PDF structure, extracts text-layer words with normalized bounding boxes,
        identifies font spans, renders pages to PNG, and computes perceptual hash.
        """
        if dpi is None:
            dpi = 110 if settings.LOW_MEMORY else 150

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        pages_data: List[Dict[str, Any]] = []
        overall_phash = None

        for page_num in range(page_count):
            page = doc[page_num]
            rect = page.rect
            width, height = rect.width, rect.height

            # Render to image for frontend and OCR/visual forensics
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img_bytes = pix.tobytes("png")

            # Cache rendered image
            render_path = RENDER_CACHE_DIR / f"{doc_id}_page_{page_num}.png"
            render_path.write_bytes(img_bytes)

            pil_img = Image.open(io.BytesIO(img_bytes))
            p_hash = str(imagehash.phash(pil_img))
            if page_num == 0:
                overall_phash = p_hash

            # Extract words with bboxes: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            raw_words = page.get_text("words")
            words: List[Dict[str, Any]] = []
            for w in raw_words:
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
                # Normalize bounding box to [ymin, xmin, ymax, xmax] in [0, 1]
                bbox = [
                    round(max(0.0, min(1.0, y0 / height)), 4),
                    round(max(0.0, min(1.0, x0 / width)), 4),
                    round(max(0.0, min(1.0, y1 / height)), 4),
                    round(max(0.0, min(1.0, x1 / width)), 4)
                ]
                words.append({
                    "text": text,
                    "bbox": bbox,
                    "raw_rect": [x0, y0, x1, y1]
                })

            # Extract detailed text blocks and font spans for forensic typography analysis
            text_dict = page.get_text("dict")
            font_spans: List[Dict[str, Any]] = []
            for block in text_dict.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            bx0, by0, bx1, by1 = span["bbox"]
                            font_spans.append({
                                "text": span.get("text", ""),
                                "font": span.get("font", ""),
                                "size": round(span.get("size", 0.0), 2),
                                "flags": span.get("flags", 0),
                                "color": span.get("color", 0),
                                "bbox": [
                                    round(max(0.0, min(1.0, by0 / height)), 4),
                                    round(max(0.0, min(1.0, bx0 / width)), 4),
                                    round(max(0.0, min(1.0, by1 / height)), 4),
                                    round(max(0.0, min(1.0, bx1 / width)), 4)
                                ]
                            })

            full_page_text = page.get_text("text")

            embedded_images: List[bytes] = []
            for img_info in page.get_images():
                try:
                    xref = img_info[0]
                    base_img = doc.extract_image(xref)
                    if "image" in base_img:
                        embedded_images.append(base_img["image"])
                except Exception:
                    pass

            pages_data.append({
                "page_num": page_num,
                "width": width,
                "height": height,
                "text": full_page_text,
                "words": words,
                "font_spans": font_spans,
                "phash": p_hash,
                "render_path": str(render_path),
                "embedded_images": embedded_images
            })

        metadata = doc.metadata or {}
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        return {
            "doc_id": doc_id,
            "page_count": page_count,
            "sha256": sha256,
            "phash": overall_phash,
            "metadata": metadata,
            "pages": pages_data
        }

    @staticmethod
    def inspect_and_render_image(
        img_bytes: bytes,
        doc_id: str
    ) -> Dict[str, Any]:
        """
        Processes single-image documents (e.g. lab photos, scanned certificates).
        """
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        width, height = pil_img.size
        if settings.LOW_MEMORY and max(width, height) > 1600:
            scale = 1600.0 / max(width, height)
            new_w, new_h = int(width * scale), int(height * scale)
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            width, height = new_w, new_h

        render_path = RENDER_CACHE_DIR / f"{doc_id}_page_0.png"
        pil_img.save(render_path, format="PNG")

        sha256 = hashlib.sha256(img_bytes).hexdigest()
        p_hash = str(imagehash.phash(pil_img))

        return {
            "doc_id": doc_id,
            "page_count": 1,
            "sha256": sha256,
            "phash": p_hash,
            "metadata": {},
            "pages": [{
                "page_num": 0,
                "width": width,
                "height": height,
                "text": "",
                "words": [],
                "font_spans": [],
                "phash": p_hash,
                "render_path": str(render_path)
            }]
        }
