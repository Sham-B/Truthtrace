import re
from typing import Dict, Any, List

DOCUMENT_KEYWORDS = {
    "affidavit": [
        "affidavit", "solemnly affirm", "deponent", "notary public", "oath commissioner",
        "sworn before me", "omnibus affidavit", "stamp paper"
    ],
    "lease_deed": [
        "lease deed", "indenture of lease", "lessor", "lessee", "demised premises",
        "sub-registrar", "schedule of property", "land area", "acres", "survey number"
    ],
    "state_noc": [
        "no objection certificate", "directorate of technical education", "higher education department",
        "state noc", "government of", "state clearance", "clearance letter"
    ],
    "nba_certificate": [
        "national board of accreditation", "accreditation status", "nba",
        "tier-i", "tier-ii", "provisional accreditation", "accreditation certificate"
    ],
    "ter_receipt": [
        "technical education regulatory", "ter fee", "payment receipt",
        "payment confirmation", "transaction id", "payment gateway", "aicte regulatory fee"
    ],
    "lab_photo": [
        "laboratory", "computer center", "workstations", "geo-tagged", "exif"
    ]
}


def classify_document(doc_info: Dict[str, Any], filename: str = "") -> Dict[str, Any]:
    """
    Classifies a document based on text content, filename cues, and metadata.
    Returns: {"doc_type": str, "confidence": float, "method": str}
    """
    # 1. Check if document is an image without text layer
    if doc_info.get("page_count", 1) == 1 and not doc_info.get("pages", [{}])[0].get("text", "").strip():
        # Likely a lab photo or scanned graphic
        fn_lower = filename.lower()
        if any(k in fn_lower for k in ["lab", "photo", "computer", "infra", "facility", "workshop"]):
            return {"doc_type": "lab_photo", "confidence": 0.95, "method": "heuristic_image"}
        return {"doc_type": "lab_photo", "confidence": 0.75, "method": "heuristic_image_default"}

    # 2. Analyze combined text from all pages
    all_text = " ".join([p.get("text", "") for p in doc_info.get("pages", [])]).lower()
    fn_lower = filename.lower()

    scores: Dict[str, float] = {k: 0.0 for k in DOCUMENT_KEYWORDS}

    for doc_type, keywords in DOCUMENT_KEYWORDS.items():
        for kw in keywords:
            if kw in all_text:
                scores[doc_type] += 2.0
            if kw in fn_lower:
                scores[doc_type] += 1.5

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score > 0:
        confidence = min(0.99, round(0.5 + (best_score / 10.0), 2))
        return {
            "doc_type": best_type,
            "confidence": confidence,
            "method": "keyword_heuristic"
        }

    # Fallback to filename or affidavit default
    if "lease" in fn_lower:
        return {"doc_type": "lease_deed", "confidence": 0.6, "method": "filename_fallback"}
    if "noc" in fn_lower:
        return {"doc_type": "state_noc", "confidence": 0.6, "method": "filename_fallback"}
    if "nba" in fn_lower:
        return {"doc_type": "nba_certificate", "confidence": 0.6, "method": "filename_fallback"}
    if "ter" in fn_lower or "receipt" in fn_lower or "fee" in fn_lower:
        return {"doc_type": "ter_receipt", "confidence": 0.6, "method": "filename_fallback"}

    return {
        "doc_type": "affidavit",
        "confidence": 0.5,
        "method": "default_fallback"
    }
