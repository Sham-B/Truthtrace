import json
import time
from typing import Dict, Any, List, Optional
from backend.app.models import LaneVoteEnum, StatusEnum
from backend.app.mock_issuers.router import (
    get_mock_issuer_record,
    _CHAOS_STATE,
    ISSUER_METADATA
)
from backend.app.security import verify_issuer_signature
from backend.app.lanes.content import get_benign_explanations

class ProvenanceLane:
    @classmethod
    def evaluate_provenance(
        cls,
        doc_id: str,
        doc_type: str,
        extracted_fields: List[Dict[str, Any]],
        page_renders: List[str]
    ) -> Dict[str, Any]:
        """
        Evaluates cryptographic provenance for a document:
        1. Checks for QR seal payload extracted from the page.
        2. Validates Ed25519 digital signature against Mock Issuer Public Key.
        3. Queries Mock Issuer authority ledger to confirm field consistency.
        4. Respects Chaos Switch (outage / timeout) and gracefully routes to SOURCE_UNAVAILABLE.
        Returns: {
            "vote": LaneVoteEnum,
            "status": StatusEnum,
            "flags": List[Dict[str, Any]],
            "provenance_data": Dict[str, Any]
        }
        """
        qr_claim = next((c for c in extracted_fields if c.get("field") == "qr_seal"), None)
        if not qr_claim:
            # Document has no digital seal/QR code
            return {
                "vote": LaneVoteEnum.NA,
                "status": StatusEnum.VERIFICATION_PENDING,
                "flags": [],
                "provenance_data": {
                    "has_seal": False,
                    "message": "Document carries no verifiable digital QR seal."
                }
            }

        try:
            seal = json.loads(qr_claim.get("value", "{}"))
        except Exception:
            seal = {}

        issuer_id = seal.get("issuer")
        doc_no = seal.get("doc_no")
        signature = seal.get("signature")
        field_hash = seal.get("field_hash")
        bbox = qr_claim.get("bbox", [0.80, 0.70, 0.98, 0.98])
        page = qr_claim.get("page", 0)

        if not issuer_id or not doc_no or not signature:
            reason_code = "SEAL_MALFORMED"
            flag = {
                "reason_code": reason_code,
                "plain_language_reason": "Embedded QR seal is incomplete or missing required cryptographic payload fields.",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "PROV_SEAL_SYNTAX",
                "source_lane": "provenance",
                "benign_explanations": get_benign_explanations("DEFAULT")
            }
            return {
                "vote": LaneVoteEnum.CONTRADICT,
                "status": StatusEnum.MISMATCH_DETECTED,
                "flags": [flag],
                "provenance_data": {"has_seal": True, "error": "Malformed seal"}
            }

        # Check Chaos Switch (simulated issuer downtime)
        chaos = _CHAOS_STATE.get(issuer_id, {"down": False, "timeout_seconds": 0.0})
        if chaos.get("down", False):
            # Issuer is simulated offline
            reason_code = "ISSUER_UNREACHABLE"
            flag = {
                "reason_code": reason_code,
                "plain_language_reason": f"Statutory authority issuer gateway '{issuer_id}' is temporarily unreachable (simulated network chaos).",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "PROV_GATEWAY_TIMEOUT",
                "source_lane": "provenance",
                "benign_explanations": [{
                    "title": "Scheduled Portal Maintenance",
                    "description": "Government issuing authority database undergoing scheduled downtime or maintenance.",
                    "settling_evidence": "Re-poll during working hours or manual confirmation with state registrar."
                }]
            }
            return {
                "vote": LaneVoteEnum.WEAK,
                "status": StatusEnum.SOURCE_UNAVAILABLE,
                "flags": [flag],
                "provenance_data": {
                    "has_seal": True,
                    "issuer": issuer_id,
                    "status": "source_unavailable",
                    "message": f"Authority {issuer_id} is unreachable"
                }
            }

        # 1. Verify Ed25519 signature
        verify_payload = {
            "issuer": issuer_id,
            "doc_no": doc_no,
            "field_hash": field_hash
        }
        sig_ok = verify_issuer_signature(issuer_id, verify_payload, signature)

        if not sig_ok:
            reason_code = "SEAL_SIGNATURE_MISMATCH"
            flag = {
                "reason_code": reason_code,
                "plain_language_reason": f"Digital signature on document failed Ed25519 cryptographic verification against {issuer_id} public registry key.",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "PROV_SIG_VERIFY",
                "source_lane": "provenance",
                "benign_explanations": get_benign_explanations(reason_code)
            }
            return {
                "vote": LaneVoteEnum.CONTRADICT,
                "status": StatusEnum.MISMATCH_DETECTED,
                "flags": [flag],
                "provenance_data": {
                    "has_seal": True,
                    "issuer": issuer_id,
                    "doc_no": doc_no,
                    "signature_valid": False,
                    "status": "signature_failed"
                }
            }

        # 2. Query Mock Issuer Ledger
        official_rec = get_mock_issuer_record(issuer_id, doc_no)
        if not official_rec:
            reason_code = "DOC_NOT_IN_REGISTRY"
            flag = {
                "reason_code": reason_code,
                "plain_language_reason": f"Document reference '{doc_no}' signed by {issuer_id} does not exist in the authority's issuance database.",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "PROV_REGISTRY_LOOKUP",
                "source_lane": "provenance",
                "benign_explanations": [{
                    "title": "Batch Registration Latency",
                    "description": "Deed or certificate was signed recently and registrar ledger synchronization batch runs at midnight.",
                    "settling_evidence": "Inspection of registrar daily physical counter receipt."
                }]
            }
            return {
                "vote": LaneVoteEnum.CONTRADICT,
                "status": StatusEnum.MISMATCH_DETECTED,
                "flags": [flag],
                "provenance_data": {
                    "has_seal": True,
                    "issuer": issuer_id,
                    "doc_no": doc_no,
                    "signature_valid": True,
                    "record_found": False
                }
            }

        # 3. Check field hash concordance
        reg_fields = official_rec["fields"]
        reg_hash = official_rec["seal_payload"]["field_hash"]

        if reg_hash != field_hash:
            reason_code = "SEAL_HASH_MISMATCH"
            flag = {
                "reason_code": reason_code,
                "plain_language_reason": "Payload hash in digital seal does not match the official recorded attributes for this registration number.",
                "evidence": {"doc_id": doc_id, "page": page, "bbox": bbox},
                "rule_id": "PROV_FIELD_INTEGRITY",
                "source_lane": "provenance",
                "benign_explanations": get_benign_explanations("DEFAULT")
            }
            return {
                "vote": LaneVoteEnum.CONTRADICT,
                "status": StatusEnum.MISMATCH_DETECTED,
                "flags": [flag],
                "provenance_data": {
                    "has_seal": True,
                    "issuer": issuer_id,
                    "doc_no": doc_no,
                    "hash_mismatch": True
                }
            }

        # Provenance completely verified!
        return {
            "vote": LaneVoteEnum.SUPPORT,
            "status": StatusEnum.VERIFIED,
            "flags": [],
            "provenance_data": {
                "has_seal": True,
                "issuer": issuer_id,
                "issuer_name": ISSUER_METADATA.get(issuer_id, {}).get("name", issuer_id),
                "doc_no": doc_no,
                "signature_valid": True,
                "record_found": True,
                "verified_at": time.time()
            }
        }
