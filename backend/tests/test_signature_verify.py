import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.mock_issuers.router import (
    register_mock_issuer_record,
    ISSUER_SUB_REGISTRAR
)
from backend.app.security import (
    sign_issuer_payload,
    verify_issuer_signature,
    get_or_create_issuer_keypair
)

def test_ed25519_signature_signing_and_verification():
    # 1. Register a valid signed document record
    doc_no = "TEST-SIG-2026-0001"
    fields = {
        "pid": "1-1029384751",
        "institution_name": "Test Engineering College",
        "address": "Campus Road 1"
    }
    payload = register_mock_issuer_record(ISSUER_SUB_REGISTRAR, doc_no, fields)

    assert "signature" in payload
    assert "field_hash" in payload
    assert payload["doc_no"] == doc_no

    # Extract signature and un-signed body
    sig_b64 = payload["signature"]
    body = {
        "issuer": payload["issuer"],
        "doc_no": payload["doc_no"],
        "field_hash": payload["field_hash"]
    }

    # Verify signature passes
    valid = verify_issuer_signature(ISSUER_SUB_REGISTRAR, body, sig_b64)
    assert valid is True, "Valid Ed25519 signature failed verification"

    # 2. Corrupt the signature and verify failure
    corrupt_sig = "A" * 64
    invalid = verify_issuer_signature(ISSUER_SUB_REGISTRAR, body, corrupt_sig)
    assert invalid is False, "Corrupt signature unexpectedly passed verification"

    # 3. Mutate the payload content and verify signature detects payload tampering
    tampered_body = dict(body)
    tampered_body["field_hash"] = "0" * 64
    invalid_content = verify_issuer_signature(ISSUER_SUB_REGISTRAR, tampered_body, sig_b64)
    assert invalid_content is False, "Signature failed to detect content tampering"

    print("Ed25519 Signature Signing & Verification test passed successfully!")

if __name__ == "__main__":
    test_ed25519_signature_signing_and_verification()
