import hashlib
import json
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from backend.app.security import (
    get_or_create_issuer_keypair,
    sign_issuer_payload,
    verify_issuer_signature
)

router = APIRouter(prefix="/mock-issuers", tags=["Mock Issuers"])

# Pre-defined Mock Issuer IDs
ISSUER_UNI = "UNI_MOCK"
ISSUER_STATE_NOC = "STATE_NOC_MOCK"
ISSUER_NBA = "NBA_MOCK"
ISSUER_SUB_REGISTRAR = "SUB_REGISTRAR_MOCK"
ISSUER_TER_PAY = "TER_PAY_MOCK"

ISSUER_METADATA = {
    ISSUER_UNI: {
        "name": "State Technological University (MOCK)",
        "jurisdiction": "All State Technical Affiliated Colleges",
        "description": "Statutory state university granting academic curriculum affiliation"
    },
    ISSUER_STATE_NOC: {
        "name": "Directorate of Technical Education (MOCK)",
        "jurisdiction": "State Government Higher Education Dept",
        "description": "Government statutory NOC clearance authority"
    },
    ISSUER_NBA: {
        "name": "National Board of Accreditation (MOCK)",
        "jurisdiction": "National Technical Quality Accreditation",
        "description": "Tier-1 & Tier-2 engineering program accreditation body"
    },
    ISSUER_SUB_REGISTRAR: {
        "name": "Department of Registration & Stamps (MOCK)",
        "jurisdiction": "District Sub-Registrar Land Title Registry",
        "description": "Official registry for e-stamps and long-term institutional lease indentures"
    },
    ISSUER_TER_PAY: {
        "name": "AICTE Centralized Payment Gateway (MOCK)",
        "jurisdiction": "National Treasury Collection",
        "description": "Processing gateway for Technical Education Regulatory (TER) fees"
    }
}

# Chaos switch state: { issuer_id: {"down": bool, "timeout_seconds": float} }
_CHAOS_STATE: Dict[str, Dict[str, Any]] = {
    ISSUER_UNI: {"down": False, "timeout_seconds": 0.0},
    ISSUER_STATE_NOC: {"down": False, "timeout_seconds": 0.0},
    ISSUER_NBA: {"down": False, "timeout_seconds": 0.0},
    ISSUER_SUB_REGISTRAR: {"down": False, "timeout_seconds": 0.0},
    ISSUER_TER_PAY: {"down": False, "timeout_seconds": 0.0},
}

# Issuer In-Memory Master Database for validation: { issuer_id: { doc_no: { fields... } } }
_MOCK_ISSUER_RECORDS: Dict[str, Dict[str, Dict[str, Any]]] = {
    ISSUER_UNI: {},
    ISSUER_STATE_NOC: {},
    ISSUER_NBA: {},
    ISSUER_SUB_REGISTRAR: {},
    ISSUER_TER_PAY: {}
}

def register_mock_issuer_record(issuer_id: str, doc_no: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Register a record in mock issuer's ledger and generate its Ed25519 signed QR seal.
    """
    if issuer_id not in _MOCK_ISSUER_RECORDS:
        _MOCK_ISSUER_RECORDS[issuer_id] = {}

    # Compute deterministic SHA256 of canonical fields
    fields_canonical = json.dumps(fields, sort_keys=True, separators=(',', ':'))
    field_hash = hashlib.sha256(fields_canonical.encode('utf-8')).hexdigest()

    seal_payload = {
        "issuer": issuer_id,
        "doc_no": doc_no,
        "field_hash": field_hash
    }
    signature = sign_issuer_payload(issuer_id, seal_payload)
    seal_payload["signature"] = signature

    _MOCK_ISSUER_RECORDS[issuer_id][doc_no] = {
        "fields": fields,
        "seal_payload": seal_payload
    }
    return seal_payload


def get_mock_issuer_record(issuer_id: str, doc_no: str) -> Optional[Dict[str, Any]]:
    return _MOCK_ISSUER_RECORDS.get(issuer_id, {}).get(doc_no)


@router.get("/registry")
def get_issuer_registry() -> Dict[str, Any]:
    """
    Returns public keys and metadata for all mock issuers.
    """
    registry = {}
    for issuer_id, meta in ISSUER_METADATA.items():
        keypair = get_or_create_issuer_keypair(issuer_id)
        registry[issuer_id] = {
            "name": meta["name"],
            "jurisdiction": meta["jurisdiction"],
            "description": meta["description"],
            "public_key_b64": keypair["public_key_b64"],
            "chaos_status": _CHAOS_STATE.get(issuer_id, {"down": False, "timeout_seconds": 0.0})
        }
    return registry


class VerifyRequest(BaseModel):
    doc_no: str
    fields_to_check: Dict[str, Any]
    signature: Optional[str] = None


@router.post("/{issuer_id}/verify")
def verify_issuer_record(issuer_id: str, payload: VerifyRequest) -> Dict[str, Any]:
    """
    Verify document validity against mock issuer authority.
    Subject to Chaos Switch state (timeout / down).
    """
    if issuer_id not in ISSUER_METADATA:
        raise HTTPException(status_code=404, detail=f"Issuer '{issuer_id}' not found.")

    chaos = _CHAOS_STATE.get(issuer_id, {"down": False, "timeout_seconds": 0.0})
    if chaos.get("timeout_seconds", 0) > 0:
        time.sleep(min(chaos["timeout_seconds"], 5.0))

    if chaos.get("down", False):
        raise HTTPException(
            status_code=503,
            detail=f"MOCK ISSUER OUTAGE: Service '{issuer_id}' is temporarily unreachable (Chaos Simulation Active)."
        )

    record = get_mock_issuer_record(issuer_id, payload.doc_no)
    if not record:
        return {
            "verified": False,
            "status": "mismatch_detected",
            "reason": f"Document reference '{payload.doc_no}' not found in {issuer_id} registry.",
            "issuer": issuer_id,
            "doc_no": payload.doc_no,
            "timestamp": time.time()
        }

    # Verify signature if provided
    sig_valid = True
    if payload.signature:
        sig_valid = verify_issuer_signature(
            issuer_id=issuer_id,
            payload_dict={
                "issuer": issuer_id,
                "doc_no": payload.doc_no,
                "field_hash": record["seal_payload"]["field_hash"]
            },
            signature_b64=payload.signature
        )

    # Compare fields
    registered_fields = record["fields"]
    mismatched_fields = {}
    for k, v in payload.fields_to_check.items():
        if k in registered_fields:
            reg_val = str(registered_fields[k]).strip().lower()
            chk_val = str(v).strip().lower()
            if reg_val != chk_val:
                mismatched_fields[k] = {"submitted": v, "official_record": registered_fields[k]}

    if not sig_valid:
        return {
            "verified": False,
            "status": "mismatch_detected",
            "reason": "Cryptographic signature failed Ed25519 verification against issuer public key.",
            "issuer": issuer_id,
            "doc_no": payload.doc_no,
            "signature_valid": False,
            "mismatched_fields": mismatched_fields,
            "timestamp": time.time()
        }

    if mismatched_fields:
        return {
            "verified": False,
            "status": "mismatch_detected",
            "reason": f"Field values differ from issuer master ledger: {list(mismatched_fields.keys())}",
            "issuer": issuer_id,
            "doc_no": payload.doc_no,
            "signature_valid": True,
            "mismatched_fields": mismatched_fields,
            "timestamp": time.time()
        }

    return {
        "verified": True,
        "status": "verified",
        "reason": f"Cryptographically authenticated and confirmed by {issuer_id} master ledger.",
        "issuer": issuer_id,
        "doc_no": payload.doc_no,
        "signature_valid": True,
        "timestamp": time.time()
    }


class ChaosToggleRequest(BaseModel):
    down: Optional[bool] = None
    timeout_seconds: Optional[float] = None


@router.post("/{issuer_id}/chaos")
def toggle_issuer_chaos(issuer_id: str, body: ChaosToggleRequest) -> Dict[str, Any]:
    """
    Toggle chaos settings (outage or artificial latency) for demoing graceful routing and fallback.
    """
    if issuer_id not in _CHAOS_STATE:
        raise HTTPException(status_code=404, detail=f"Issuer '{issuer_id}' not found.")

    if body.down is not None:
        _CHAOS_STATE[issuer_id]["down"] = body.down
    if body.timeout_seconds is not None:
        _CHAOS_STATE[issuer_id]["timeout_seconds"] = max(0.0, body.timeout_seconds)

    return {
        "issuer": issuer_id,
        "chaos_state": _CHAOS_STATE[issuer_id],
        "message": f"Chaos configuration for {issuer_id} updated."
    }
