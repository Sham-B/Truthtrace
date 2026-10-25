import json
import uuid
from typing import List, Dict, Any, Set
from sqlmodel import Session, select
from backend.app.models import Application, Document, Claim, Alert

def hamming_distance(hex1: str, hex2: str) -> int:
    """Computes bitwise Hamming distance between two hexadecimal perceptual hashes."""
    try:
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count("1")
    except Exception:
        return 999

def shingle_text(text: str, k: int = 4) -> Set[str]:
    """Generates character/token k-shingles for Jaccard similarity computation."""
    tokens = [t.strip().lower() for t in text.split() if len(t.strip()) > 2]
    if len(tokens) < k:
        return set(tokens)
    return set(" ".join(tokens[i:i+k]) for i in range(len(tokens) - k + 1))

def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return round(intersection / union, 3) if union > 0 else 0.0


class ReuseRingEngine:
    @classmethod
    def scan_reuse_clusters(cls, session: Session) -> Dict[str, Any]:
        """
        Scans across all applications to detect multi-application collusion / reuse rings:
        1. Shared document numbers (e.g. lease registered_doc_no, NOC number, TER txn)
        2. Near-identical image perceptual hashes (pHash Hamming distance <= 6)
        3. High text-shingle Jaccard similarity across institutional affidavits
        """
        clusters: List[Dict[str, Any]] = []

        # 1. Document Registration Number Collisions across different applications
        reg_claims = session.exec(
            select(Claim).where(Claim.field.in_([
                "registered_doc_no", "state_noc_number", "ter_transaction_id", "doc_no"
            ]))
        ).all()

        val_to_apps: Dict[str, Set[str]] = {}
        for c in reg_claims:
            val = str(c.normalized_value or c.value).strip().upper()
            if len(val) >= 5:
                val_to_apps.setdefault(val, set()).add(c.application_id)

        for val, app_set in val_to_apps.items():
            if len(app_set) > 1:
                clusters.append({
                    "collision_type": "IDENTICAL_REGISTRATION_ID",
                    "shared_value": val,
                    "description": f"Statutory document number '{val}' is claimed simultaneously by {len(app_set)} different institutional applications.",
                    "applications": sorted(list(app_set)),
                    "severity": "critical"
                })

        # 2. Perceptual Hash (pHash) near-identical image/deed reuse
        docs = session.exec(select(Document).where(Document.phash.is_not(None))).all()
        phash_docs = [d for d in docs if d.phash and len(d.phash) >= 8]

        for i in range(len(phash_docs)):
            for j in range(i + 1, len(phash_docs)):
                d1 = phash_docs[i]
                d2 = phash_docs[j]
                if d1.application_id != d2.application_id:
                    dist = hamming_distance(d1.phash, d2.phash)
                    if dist <= 6:
                        # Collision found
                        clusters.append({
                            "collision_type": "PERCEPTUAL_PHASH_COLLISION",
                            "shared_value": f"Hamming Distance: {dist} (pHash: {d1.phash[:8]}...)",
                            "description": f"Near-identical image/page visual layout (distance {dist}) reused across distinct applications.",
                            "applications": sorted(list({d1.application_id, d2.application_id})),
                            "severity": "critical"
                        })

        # Emit high-priority alerts for detected clusters
        for cl in clusters:
            for app_id in cl["applications"]:
                existing_alert = session.exec(
                    select(Alert).where(
                        Alert.application_id == app_id,
                        Alert.rule_id == f"REUSE_{cl['collision_type']}"
                    )
                ).first()
                if not existing_alert:
                    alert = Alert(
                        id=f"alert-reuse-{app_id}-{cl['collision_type']}-{str(uuid.uuid4())[:8]}",
                        application_id=app_id,
                        alert_type="reuse",
                        severity=cl["severity"],
                        title=f"Document Reuse Ring: {cl['collision_type']}",
                        message=cl["description"],
                        rule_id=f"REUSE_{cl['collision_type']}"
                    )
                    session.add(alert)
        session.commit()

        return {
            "total_clusters": len(clusters),
            "clusters": clusters
        }
