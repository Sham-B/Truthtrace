import re
from typing import Dict, Any, List, Optional
import yaml
from rapidfuzz import fuzz
from backend.app.config import RULES_DIR
from backend.app.models import LaneVoteEnum, StatusEnum, MockAICTERecord

# Load benign hypotheses YAML
BENIGN_YAML_PATH = RULES_DIR / "benign_hypotheses.yaml"
_BENIGN_HYPOTHESES: Dict[str, Any] = {}
if BENIGN_YAML_PATH.exists():
    try:
        with open(BENIGN_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            _BENIGN_HYPOTHESES = data.get("hypotheses", {})
    except Exception as e:
        print(f"[ContentLane] Warning loading benign hypotheses: {e}")

def get_benign_explanations(reason_code: str) -> List[Dict[str, str]]:
    if reason_code in _BENIGN_HYPOTHESES:
        return _BENIGN_HYPOTHESES[reason_code].get("benign_explanations", [])
    if "DEFAULT" in _BENIGN_HYPOTHESES:
        return _BENIGN_HYPOTHESES["DEFAULT"].get("benign_explanations", [])
    return [{
        "title": "Administrative or Scanning Inconsistency",
        "description": "Clerical deviation or scanning artifact during document upload.",
        "settling_evidence": "Verification of original wet-ink signed documents during hearing."
    }]

class ContentLane:
    @classmethod
    def evaluate_claim(
        cls,
        claim_dict: Dict[str, Any],
        doc_type: str,
        aicte_record: Optional[MockAICTERecord] = None,
        checklist_rules: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a single claim in the Content lane:
        - Validates format (regex)
        - Compares against AICTE master record (PID, institution name, address, TER payment)
        - Checks numeric thresholds and expiry
        Returns: {"vote": LaneVoteEnum, "status": str, "flags": List[Dict[str, Any]]}
        """
        field = claim_dict.get("field", "")
        raw_val = claim_dict.get("value", "")
        norm_val = claim_dict.get("normalized_value", "")
        bbox = claim_dict.get("bbox", [0.0, 0.0, 0.0, 0.0])
        page = claim_dict.get("page", 0)
        doc_id = claim_dict.get("doc_id", "")

        flags: List[Dict[str, Any]] = []

        # 0. Scanned Image Manual Review Check
        if field == "manual_review_required":
            reason_code = "MANUAL_REVIEW_REQUIRED"
            flags.append({
                "reason_code": reason_code,
                "plain_language_reason": claim_dict.get("plain_language_reason") or "Scanned document submitted without machine-readable digital text layer. OCR is disabled or unavailable; manual scrutiny officer review required.",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "REQ_MANUAL_REVIEW",
                "source_lane": "content",
                "benign_explanations": [{
                    "title": "Legacy Physical Document Scan",
                    "description": "Applicant uploaded a physical paper scan without digital text layer.",
                    "settling_evidence": "Officer inspection of physical paper or high-resolution text resubmission."
                }]
            })
            return {"vote": LaneVoteEnum.CONTRADICT, "status": "manual_review_required", "flags": flags}

        # 1. PID Consistency & Format Check
        if field == "pid":
            if not re.match(r"^1-\d{10}$", norm_val):
                reason_code = "PID_FORMAT_INVALID"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Permanent Institute ID '{norm_val}' does not conform to AICTE standard format (1-XXXXXXXXXX).",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "REQ_PID_FORMAT",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations(reason_code)
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}

            if aicte_record and norm_val != aicte_record.pid:
                reason_code = "PID_MASTER_MISMATCH"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Claimed PID '{norm_val}' does not match official AICTE Master Record PID '{aicte_record.pid}'.",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "IR_PID_CROSS_DOC",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations(reason_code)
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}

            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}

        # 2. Institution Name Fuzzy Concordance
        if field == "institution_name" and aicte_record:
            similarity = fuzz.token_sort_ratio(norm_val.lower(), aicte_record.name.lower())
            if similarity < 75:
                reason_code = "NAME_MISMATCH"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Document institution name '{norm_val}' diverges significantly from AICTE master record '{aicte_record.name}' (similarity: {similarity}%).",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "IR_INST_NAME_MATCH",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations(reason_code)
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}
            elif similarity < 90:
                # Slight variation
                return {"vote": LaneVoteEnum.WEAK, "status": StatusEnum.VERIFIED, "flags": []}
            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}

        # 3. Address Concordance Check
        if field == "address" and aicte_record:
            addr_sim = fuzz.token_set_ratio(norm_val.lower(), aicte_record.address.lower())
            if addr_sim < 65:
                reason_code = "ADDRESS_MISMATCH"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Campus address in deed '{norm_val[:60]}...' diverges from AICTE registered address '{aicte_record.address[:60]}...' (similarity: {addr_sim}%).",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "IR_ADDRESS_MATCH",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations("NAME_MISMATCH")
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}
            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}

        # 4. TER Payment Amount and Transaction Verification
        if field == "ter_amount" and aicte_record:
            try:
                amt = float(norm_val)
                if amt < aicte_record.ter_fee_required:
                    reason_code = "TER_AMOUNT_INSUFFICIENT"
                    flags.append({
                        "reason_code": reason_code,
                        "plain_language_reason": f"Regulatory fee paid (INR {amt:,.2f}) is below standard prescribed fee (INR {aicte_record.ter_fee_required:,.2f}).",
                        "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                        "rule_id": "REQ_TER_AMT",
                        "source_lane": "content",
                        "benign_explanations": get_benign_explanations("TER_PAYMENT_PENDING")
                    })
                    return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}
                return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}
            except ValueError:
                pass

        if field == "ter_transaction_id" and aicte_record:
            if norm_val != aicte_record.ter_transaction_id:
                reason_code = "TER_TXN_MISMATCH"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Payment transaction ID '{norm_val}' was not matched against bank clearing record '{aicte_record.ter_transaction_id}'.",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "REQ_TER_TXN",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations("TER_PAYMENT_PENDING")
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}
            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}

        # 5. Land Area Acreage Check
        if field == "land_area_acres":
            try:
                acres = float(norm_val)
                if acres < 2.5:
                    reason_code = "INSUFFICIENT_LAND_AREA"
                    flags.append({
                        "reason_code": reason_code,
                        "plain_language_reason": f"Contiguous land area ({acres} acres) is below minimum handbook norm of 2.5 acres for technical campus.",
                        "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                        "rule_id": "REQ_LAND_AREA",
                        "source_lane": "content",
                        "benign_explanations": get_benign_explanations("DEFAULT")
                    })
                    return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.MISMATCH_DETECTED, "flags": flags}
                return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}
            except ValueError:
                pass

        # 6. Expiry Date Check
        if "expiry" in field or "valid_upto" in field:
            # Check if expired relative to 2026-2027 academic year baseline (2026-06-30)
            if norm_val < "2026-06-30":
                reason_code = "EXPIRED_DOCUMENT"
                flags.append({
                    "reason_code": reason_code,
                    "plain_language_reason": f"Document validity expired on {norm_val}, prior to the 2026-2027 academic approval commencement.",
                    "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                    "rule_id": "TR_LEASE_MIN_VALIDITY" if "lease" in field else "REQ_NBA_VALIDITY",
                    "source_lane": "content",
                    "benign_explanations": get_benign_explanations(reason_code)
                })
                return {"vote": LaneVoteEnum.CONTRADICT, "status": StatusEnum.EXPIRED, "flags": flags}
            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}

        # Default fallback
        if norm_val:
            return {"vote": LaneVoteEnum.SUPPORT, "status": StatusEnum.VERIFIED, "flags": []}
        return {"vote": LaneVoteEnum.NA, "status": StatusEnum.VERIFICATION_PENDING, "flags": []}
