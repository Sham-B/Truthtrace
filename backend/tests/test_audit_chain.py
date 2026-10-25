import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.main import app
from backend.app.db import engine
from backend.app.models import AuditEntry
from backend.app.audit import verify_audit_chain, log_audit_event, calculate_audit_hash

def repair_tampered_demo_entries():
    with Session(engine) as session:
        entries = session.exec(select(AuditEntry)).all()
        for e in entries:
            if e.payload and "_UNAUTHORIZED_MUTATION_DEMO" in e.payload:
                new_payload = dict(e.payload)
                del new_payload["_UNAUTHORIZED_MUTATION_DEMO"]
                e.payload = new_payload
                session.add(e)
        session.commit()

def test_hash_chained_audit_integrity():
    client = TestClient(app)

    # Ensure clean state from any prior demo tamper
    repair_tampered_demo_entries()

    # 1. Verify pristine audit trail is intact
    ver_res = client.get("/audit/verify").json()
    assert ver_res["valid"] is True, f"Expected valid audit chain, got: {ver_res['message']}"

    # 2. Add an audit event and verify hash chaining
    with Session(engine) as session:
        new_entry = log_audit_event(
            session=session,
            actor_role="Officer",
            action="TEST_VERIFY_CHAIN",
            application_id="APP-2026-001",
            payload={"test_key": "test_val"}
        )
        assert len(new_entry.current_hash) == 64
        assert len(new_entry.prev_hash) == 64

    # Verification must still pass
    ver_res2 = client.get("/audit/verify").json()
    assert ver_res2["valid"] is True

    # 3. Simulate unauthorized database row tampering
    tamper_res = client.post("/audit/tamper-demo").json()
    assert tamper_res["status"] == "tampered"
    tampered_id = tamper_res["tampered_entry_id"]

    # 4. Verify that audit chain immediately catches tampering and pinpoints broken ID
    ver_tampered = client.get("/audit/verify").json()
    assert ver_tampered["valid"] is False, "Cryptographic audit chain failed to detect row tampering!"
    assert ver_tampered["broken_at_id"] == tampered_id, f"Expected broken at #{tampered_id}, got #{ver_tampered['broken_at_id']}"

    # Clean up so subsequent tests don't see tampered state
    repair_tampered_demo_entries()

    print("STAGE 4 HASH-CHAINED AUDIT TESTS PASSED!")

if __name__ == "__main__":
    test_hash_chained_audit_integrity()
