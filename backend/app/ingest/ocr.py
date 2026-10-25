import io
from typing import List, Dict, Any, Optional
from PIL import Image
import numpy as np

from backend.app.config import settings

# Global cached EasyOCR reader (lazy-loaded on first call)
_EASYOCR_READER = None

def get_ocr_reader():
    global _EASYOCR_READER
    if settings.DISABLE_OCR or settings.LOW_MEMORY:
        return None
    if _EASYOCR_READER is None:
        try:
            import easyocr
            # Lazy initialize English reader on CPU
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception as e:
            print(f"[OCR] EasyOCR initialization warning: {e}")
            _EASYOCR_READER = None
    return _EASYOCR_READER


def run_ocr_on_image(img_input: Any) -> List[Dict[str, Any]]:
    """
    Run OCR on image bytes, PIL Image, or file path.
    Returns list of words/lines with normalized bounding box [ymin, xmin, ymax, xmax].
    """
    reader = get_ocr_reader()
    if reader is None:
        return []

    try:
        if isinstance(img_input, bytes):
            pil_img = Image.open(io.BytesIO(img_input)).convert("RGB")
        elif isinstance(img_input, str):
            pil_img = Image.open(img_input).convert("RGB")
        elif isinstance(img_input, Image.Image):
            pil_img = img_input.convert("RGB")
        else:
            return []

        width, height = pil_img.size
        img_np = np.array(pil_img)
        results = reader.readtext(img_np)

        ocr_words: List[Dict[str, Any]] = []
        for bbox_pts, text, confidence in results:
            # bbox_pts is [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            xs = [pt[0] for pt in bbox_pts]
            ys = [pt[1] for pt in bbox_pts]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)

            norm_bbox = [
                round(max(0.0, min(1.0, y_min / height)), 4),
                round(max(0.0, min(1.0, x_min / width)), 4),
                round(max(0.0, min(1.0, y_max / height)), 4),
                round(max(0.0, min(1.0, x_max / width)), 4)
            ]

            ocr_words.append({
                "text": text,
                "confidence": round(float(confidence), 3),
                "bbox": norm_bbox
            })
        return ocr_words
    except Exception as e:
        print(f"[OCR] Error during optical recognition: {e}")
        return []
