import uuid
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
from backend.app.models import (
    Application, Document, Claim, MockAICTERecord,
    LaneVoteEnum, StatusEnum
)
from backend.app.lanes.content import ContentLane
from backend.app.lanes.provenance import ProvenanceLane
from backend.app.lanes.forensic import ForensicLane

def bbox_intersects(b1: List[float], b2: List[float]) -> bool:
    """Checks if two normalized [ymin, xmin, ymax, xmax] boxes intersect."""
    if not b1 or not b2 or len(b1) != 4 or len(b2) != 4:
        return False
    # If one box is degenerate 0,0,0,0
    if b1 == [0.0, 0.0, 0.0, 0.0] or b2 == [0.0, 0.0, 0.0, 0.0]:
        return False
    return not (b1[3] < b2[1] or b1[1] > b2[3] or b1[2] < b2[0] or b1[0] > b2[2])


class ClaimLedger:
    @classmethod
    def record_and_evaluate_claims(
        cls,
        session: Session,
        application_id: str,
        doc_id: str,
        doc_type: str,
        extracted_fields: List[Dict[str, Any]],
        page_renders: List[str],
        inspect_data: Optional[Dict[str, Any]] = None,
        doc_bytes: Optional[bytes] = None
    ) -> List[Claim]:
        """
        Takes raw extracted fields from a document, registers them into the Claim Ledger,
        and evaluates them across all Three Independent Evidence Lanes:
        1. Content Lane (Checklists, formats, master record consistency)
        2. Forensic Lane (ELA, noise residual, copy-move, metadata, mixed typography)
        3. Provenance Lane (Ed25519 QR signatures, mock issuer ledgers)
        """
        # Fetch application and AICTE master record
        app = session.get(Application, application_id)
        aicte_record = None
        if app:
            aicte_record = session.get(MockAICTERecord, app.institution_id)

        # 1. Evaluate Provenance Lane for the overall document
        prov_result = ProvenanceLane.evaluate_provenance(
            doc_id=doc_id,
            doc_type=doc_type,
            extracted_fields=extracted_fields,
            page_renders=page_renders
        )

        # 2. Evaluate Forensic Lane for the overall document
        forensic_result = {"vote": LaneVoteEnum.NA, "suspicion_score": 0.0, "flags": []}
        if inspect_data and doc_bytes:
            forensic_result = ForensicLane.evaluate_document(
                doc_id=doc_id,
                inspect_data=inspect_data,
                doc_bytes=doc_bytes,
                extracted_claims=extracted_fields
            )

        created_claims: List[Claim] = []

        # 3. Iterate through extracted fields, evaluate Content Lane & map Forensic/Provenance
        for f in extracted_fields:
            field_name = f.get("field", "")
            raw_val = str(f.get("value", ""))
            norm_val = str(f.get("normalized_value", raw_val))
            page = int(f.get("page", 0))
            bbox = f.get("bbox", [0.0, 0.0, 0.0, 0.0])
            confidence = float(f.get("confidence", 1.0))

            claim_dict = {
                "field": field_name,
                "value": raw_val,
                "normalized_value": norm_val,
                "page": page,
                "bbox": bbox,
                "doc_id": doc_id
            }

            content_eval = ContentLane.evaluate_claim(
                claim_dict=claim_dict,
                doc_type=doc_type,
                aicte_record=aicte_record
            )

            # Map Forensic flags overlapping this claim's region
            claim_forensic_flags = []
            claim_forensic_vote = LaneVoteEnum.SUPPORT if forensic_result["vote"] != LaneVoteEnum.NA else LaneVoteEnum.NA
            for f_flag in forensic_result["flags"]:
                f_box = f_flag.get("evidence", {}).get("bbox", [0.0, 0.0, 0.0, 0.0])
                f_page = f_flag.get("evidence", {}).get("page", 0)
                # Overlaps this claim or document-level metadata
                if f_flag.get("reason_code") == "SUSPICIOUS_PDF_PRODUCER" or (f_page == page and bbox_intersects(bbox, f_box)):
                    claim_forensic_flags.append(f_flag)
                    claim_forensic_vote = LaneVoteEnum.CONTRADICT

            # Assign lane votes
            content_vote = content_eval["vote"]
            forensic_vote = claim_forensic_vote
            provenance_vote = prov_result["vote"]

            # Merge flags
            flags = list(content_eval["flags"])
            flags.extend(claim_forensic_flags)
            
            # Attach provenance seal flags to qr_seal claim only (or registered_doc_no if no qr_seal field exists)
            has_qr_field = any(fld.get("field") == "qr_seal" for fld in extracted_fields)
            if field_name == "qr_seal" or (not has_qr_field and field_name == "registered_doc_no"):
                flags.extend(prov_result["flags"])

            # Deduplicate flags for this claim by (rule_id, reason_code)
            deduped_flags = []
            seen_flag_keys = set()
            for fl in flags:
                f_key = (fl.get("rule_id", ""), fl.get("reason_code", ""))
                if f_key not in seen_flag_keys:
                    seen_flag_keys.add(f_key)
                    deduped_flags.append(fl)
            flags = deduped_flags

            # Determine claim status
            claim_status = StatusEnum.VERIFIED
            if any(fl.get("reason_code") == "ISSUER_UNREACHABLE" for fl in flags):
                claim_status = StatusEnum.SOURCE_UNAVAILABLE
            elif any(fl.get("reason_code") == "EXPIRED_DOCUMENT" for fl in flags):
                claim_status = StatusEnum.EXPIRED
            elif flags:
                claim_status = StatusEnum.MISMATCH_DETECTED

            claim_obj = Claim(
                id=str(uuid.uuid4()),
                application_id=application_id,
                doc_id=doc_id,
                field=field_name,
                value=raw_val,
                normalized_value=norm_val,
                page=page,
                bbox=bbox,
                extraction_confidence=confidence,
                content_vote=content_vote,
                forensic_vote=forensic_vote,
                provenance_vote=provenance_vote,
                status=claim_status,
                flags=flags
            )
            session.add(claim_obj)
            created_claims.append(claim_obj)

        session.commit()
        return created_claims
