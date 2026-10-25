import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dateutil import parser as date_parser
import cv2
import numpy as np
from PIL import Image

PID_REGEX = re.compile(r"1-\d{10}")
DATE_REGEX = re.compile(r"\b\d{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
AMOUNT_REGEX = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d{2})?)")
ACRES_REGEX = re.compile(r"([\d\.]+)\s*(?:acres|acre)", re.IGNORECASE)

class FieldExtractor:
    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        try:
            cleaned = date_str.strip().replace("/", "-").replace(".", "-")
            dt = date_parser.parse(cleaned, dayfirst=True)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def normalize_amount(amount_str: str) -> Optional[float]:
        try:
            cleaned = re.sub(r"[^\d\.]", "", amount_str)
            return float(cleaned)
        except Exception:
            return None

    @staticmethod
    def find_words_bbox(words: List[Dict[str, Any]], target_tokens: List[str]) -> List[float]:
        """
        Locates the bounding box enclosing the target tokens on the page.
        Returns normalized [ymin, xmin, ymax, xmax].
        """
        if not words or not target_tokens:
            return [0.1, 0.1, 0.2, 0.9]

        matched_boxes = []
        token_lower = [t.lower() for t in target_tokens if len(t) > 1]

        for w in words:
            w_text = w["text"].lower().strip(",.:;\"'()")
            if any(tok in w_text or w_text in tok for tok in token_lower):
                matched_boxes.append(w["bbox"])

        if not matched_boxes:
            return [0.1, 0.1, 0.2, 0.9]

        ymin = min(b[0] for b in matched_boxes)
        xmin = min(b[1] for b in matched_boxes)
        ymax = max(b[2] for b in matched_boxes)
        xmax = max(b[3] for b in matched_boxes)

        # Pad slightly
        return [
            round(max(0.0, ymin - 0.005), 4),
            round(max(0.0, xmin - 0.005), 4),
            round(min(1.0, ymax + 0.005), 4),
            round(min(1.0, xmax + 0.005), 4)
        ]

    @classmethod
    def extract_qr_code(cls, render_path: str, embedded_images: Optional[List[bytes]] = None) -> Optional[Dict[str, Any]]:
        """
        Detects and decodes QR seal from embedded image streams or rendered page image using OpenCV QRCodeDetector.
        """
        detector = cv2.QRCodeDetector()

        # 1. Try embedded image streams first (direct unscaled raster)
        if embedded_images:
            for img_bytes in embedded_images:
                try:
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img_np is not None:
                        data, _, _ = detector.detectAndDecode(img_np)
                        if data:
                            try:
                                return json.loads(data)
                            except json.JSONDecodeError:
                                return {"raw_data": data}
                except Exception:
                    pass

        # 2. Try rendered page image
        try:
            if render_path:
                img = cv2.imread(render_path)
                if img is not None:
                    data, bbox, _ = detector.detectAndDecode(img)
                    if data:
                        try:
                            return json.loads(data)
                        except json.JSONDecodeError:
                            return {"raw_data": data}
            return None
        except Exception as e:
            print(f"[Extract] QR decode error: {e}")
            return None

    @classmethod
    def extract_fields_from_doc(cls, doc_type: str, doc_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extracts relevant regulatory fields based on document type.
        Returns list of extracted claim dicts:
        [{field, value, normalized_value, page, bbox, confidence}]
        """
        extracted: List[Dict[str, Any]] = []
        pages = doc_info.get("pages", [])
        if not pages:
            return extracted

        # First, check for QR code on all pages (usually page 0 or last page)
        for p in pages:
            render_path = p.get("render_path")
            embedded_imgs = p.get("embedded_images", [])
            qr_payload = cls.extract_qr_code(render_path, embedded_imgs)
            if qr_payload:
                extracted.append({
                    "field": "qr_seal",
                    "value": json.dumps(qr_payload),
                    "normalized_value": json.dumps(qr_payload, sort_keys=True),
                    "page": p["page_num"],
                    "bbox": [0.80, 0.70, 0.98, 0.98],
                    "confidence": 1.0
                })
                if "doc_no" in qr_payload:
                    extracted.append({
                        "field": "registered_doc_no",
                        "value": qr_payload["doc_no"],
                        "normalized_value": str(qr_payload["doc_no"]).strip(),
                        "page": p["page_num"],
                        "bbox": [0.80, 0.70, 0.85, 0.98],
                        "confidence": 1.0
                    })
                break

        # Check if scanned raster without text layer
        has_text = any(p.get("text", "").strip() for p in pages)
        if not has_text and doc_type != "lab_photo":
            extracted.append({
                "field": "manual_review_required",
                "value": "SCANNED_IMAGE_MANUAL_REVIEW",
                "normalized_value": "SCANNED_IMAGE_MANUAL_REVIEW",
                "page": 0,
                "bbox": [0.0, 0.0, 0.1, 1.0],
                "confidence": 1.0,
                "plain_language_reason": "Scanned document submitted without machine-readable digital text layer. OCR is disabled or unavailable; manual scrutiny officer review required."
            })

        for page in pages:
            p_num = page["page_num"]
            p_text = page.get("text", "")
            words = page.get("words", [])

            # Extract PID: Permanent Institute ID (1-XXXXXXXXXX)
            pid_match = PID_REGEX.search(p_text)
            if pid_match:
                pid_val = pid_match.group(0)
                extracted.append({
                    "field": "pid",
                    "value": pid_val,
                    "normalized_value": pid_val,
                    "page": p_num,
                    "bbox": cls.find_words_bbox(words, [pid_val]),
                    "confidence": 0.98
                })

            # Extract Institution Name
            name_match = re.search(r"(?:Institution|Institute|College|Trust):\s*([^\n\r,]+(?:Institute|College|Academy|Engineering|Technology)[^\n\r,]*)", p_text, re.IGNORECASE)
            if name_match:
                inst_name = name_match.group(1).strip()
                extracted.append({
                    "field": "institution_name",
                    "value": inst_name,
                    "normalized_value": inst_name.title(),
                    "page": p_num,
                    "bbox": cls.find_words_bbox(words, inst_name.split()[:4]),
                    "confidence": 0.92
                })

            # Specific extractions per doc_type
            if doc_type == "affidavit":
                date_match = re.search(r"(?:solemnly affirm|executed on|sworn on|date:?)\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if date_match:
                    raw_d = date_match.group(1)
                    norm_d = cls.normalize_date(raw_d)
                    if norm_d:
                        extracted.append({
                            "field": "affidavit_date",
                            "value": raw_d,
                            "normalized_value": norm_d,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_d]),
                            "confidence": 0.95
                        })

            elif doc_type == "lease_deed":
                start_match = re.search(r"(?:commencing from|lease start|effective from|from)\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if start_match:
                    raw_sd = start_match.group(1)
                    norm_sd = cls.normalize_date(raw_sd)
                    if norm_sd:
                        extracted.append({
                            "field": "lease_start_date",
                            "value": raw_sd,
                            "normalized_value": norm_sd,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_sd]),
                            "confidence": 0.95
                        })

                exp_match = re.search(r"(?:expiring on|lease expiry|valid up to|until)\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if exp_match:
                    raw_ed = exp_match.group(1)
                    norm_ed = cls.normalize_date(raw_ed)
                    if norm_ed:
                        extracted.append({
                            "field": "lease_expiry_date",
                            "value": raw_ed,
                            "normalized_value": norm_ed,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_ed]),
                            "confidence": 0.95
                        })

                area_match = ACRES_REGEX.search(p_text)
                if area_match:
                    raw_area = area_match.group(1)
                    extracted.append({
                        "field": "land_area_acres",
                        "value": raw_area,
                        "normalized_value": str(float(raw_area)),
                        "page": p_num,
                        "bbox": cls.find_words_bbox(words, [raw_area, "acres"]),
                        "confidence": 0.92
                    })

                # Address extraction on deed
                addr_match = re.search(r"(?:situated at|campus address|premises located at):\s*([^\n\r]+)", p_text, re.IGNORECASE)
                if addr_match:
                    raw_addr = addr_match.group(1).strip()
                    extracted.append({
                        "field": "address",
                        "value": raw_addr,
                        "normalized_value": raw_addr,
                        "page": p_num,
                        "bbox": cls.find_words_bbox(words, raw_addr.split()[:4]),
                        "confidence": 0.88
                    })

            elif doc_type == "state_noc":
                noc_num_match = re.search(r"(?:NOC Ref No|Clearance Letter No|Letter No\.?):\s*([A-Za-z0-9/-]+)", p_text, re.IGNORECASE)
                if noc_num_match:
                    raw_noc = noc_num_match.group(1).strip()
                    extracted.append({
                        "field": "state_noc_number",
                        "value": raw_noc,
                        "normalized_value": raw_noc,
                        "page": p_num,
                        "bbox": cls.find_words_bbox(words, [raw_noc]),
                        "confidence": 0.95
                    })

                noc_date_match = re.search(r"(?:Date of Issue|Dated|Date):\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if noc_date_match:
                    raw_nd = noc_date_match.group(1)
                    norm_nd = cls.normalize_date(raw_nd)
                    if norm_nd:
                        extracted.append({
                            "field": "state_noc_date",
                            "value": raw_nd,
                            "normalized_value": norm_nd,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_nd]),
                            "confidence": 0.94
                        })

            elif doc_type in ["nba_certificate", "accreditation_certificate"]:
                acc_match = re.search(r"(?:File No|Accreditation Ref|Certificate No):\s*([A-Za-z0-9/-]+)", p_text, re.IGNORECASE)
                if acc_match:
                    raw_acc = acc_match.group(1).strip()
                    extracted.append({
                        "field": "nba_accreditation_number",
                        "value": raw_acc,
                        "normalized_value": raw_acc,
                        "page": p_num,
                        "bbox": cls.find_words_bbox(words, [raw_acc]),
                        "confidence": 0.95
                    })

                valid_match = re.search(r"(?:valid up to|valid through|expiry):\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if valid_match:
                    raw_vd = valid_match.group(1)
                    norm_vd = cls.normalize_date(raw_vd)
                    if norm_vd:
                        extracted.append({
                            "field": "nba_valid_upto",
                            "value": raw_vd,
                            "normalized_value": norm_vd,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_vd]),
                            "confidence": 0.95
                        })

            elif doc_type == "ter_receipt":
                txn_match = re.search(r"(?:Transaction ID|Txn Ref|Reference No):\s*([A-Za-z0-9-]+)", p_text, re.IGNORECASE)
                if txn_match:
                    raw_tx = txn_match.group(1).strip()
                    extracted.append({
                        "field": "ter_transaction_id",
                        "value": raw_tx,
                        "normalized_value": raw_tx,
                        "page": p_num,
                        "bbox": cls.find_words_bbox(words, [raw_tx]),
                        "confidence": 0.98
                    })

                amt_match = AMOUNT_REGEX.search(p_text)
                if amt_match:
                    raw_amt = amt_match.group(1)
                    norm_amt = cls.normalize_amount(raw_amt)
                    if norm_amt:
                        extracted.append({
                            "field": "ter_amount",
                            "value": raw_amt,
                            "normalized_value": str(norm_amt),
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_amt]),
                            "confidence": 0.96
                        })

                tx_date_match = re.search(r"(?:Date of Transaction|Txn Date|Paid On):\s*([0-9]{1,2}[-/\.][0-9A-Za-z]{2,3}[-/\.][0-9]{2,4}|\d{4}-\d{2}-\d{2})", p_text, re.IGNORECASE)
                if tx_date_match:
                    raw_td = tx_date_match.group(1)
                    norm_td = cls.normalize_date(raw_td)
                    if norm_td:
                        extracted.append({
                            "field": "ter_payment_date",
                            "value": raw_td,
                            "normalized_value": norm_td,
                            "page": p_num,
                            "bbox": cls.find_words_bbox(words, [raw_td]),
                            "confidence": 0.95
                        })

        # Deduplicate extracted fields by field name, keeping highest confidence
        unique_extracted = {}
        for item in extracted:
            fn = item["field"]
            if fn not in unique_extracted or item["confidence"] > unique_extracted[fn]["confidence"]:
                unique_extracted[fn] = item

        return list(unique_extracted.values())
