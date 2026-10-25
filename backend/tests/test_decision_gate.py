import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.synth.seed import seed_database
from backend.app.models import StatusEnum

def test_officer_decision_gate_and_rbac():
    seed_database(force=False)
    client = TestClient(app)

    # 1. Non-negotiable test: AI endpoints cannot set an adverse outcome directly
    val_resp = client.post("/applications/APP-2026-001/validate", headers={"X-Role": "Officer"})
    assert val_resp.status_code == 200
    app_data = client.get("/applications/APP-2026-001", headers={"X-Role": "Officer"}).json()
    assert app_data["adverse_action"] is None, "AI validation endpoint automatically set an adverse outcome!"

    # 2. Adverse action fails if role is not Officer
    inst_resp = client.post(
        "/decisions",
        json={"application_id": "APP-2026-002", "action": "reject", "written_reason": "Rejected by automated script"},
        headers={"X-Role": "Institution"}
    )
    assert inst_resp.status_code == 403, f"Expected 403 Forbidden for Institution role, got {inst_resp.status_code}"

    # 3. Adverse action fails if written reason is empty or shorter than 10 characters
    short_resp = client.post(
        "/decisions",
        json={"application_id": "APP-2026-002", "action": "reject", "written_reason": "Too short"},
        headers={"X-Role": "Officer"}
    )
    assert short_resp.status_code == 400

    # 4. Valid Officer decision succeeds and records officer ID
    officer_resp = client.post(
        "/decisions",
        json={
            "application_id": "APP-2026-002",
            "action": "reject",
            "written_reason": "Document address on lease deed contradicts AICTE master record; rejected under APH §Appendix-4.1."
        },
        headers={"X-Role": "Officer", "X-Officer-Id": "REG-OFFICER-44"}
    )
    assert officer_resp.status_code == 200
    assert officer_resp.json()["officer_action"] == "reject"
    assert officer_resp.json()["officer_id"] == "REG-OFFICER-44"

    # 5. RBAC Redaction Test: Institution role MUST NOT see suspicion scores or forensic internals
    inst_report = client.get("/applications/APP-2026-002/report", headers={"X-Role": "Institution"}).json()
    assert inst_report["suspicion_score"] is None, "Suspicion score leaked to Institution role!"
    assert inst_report["assurance_score"] is None, "Assurance score leaked to Institution role!"
    # Ensure no forensic lane flags in institution view
    for d in inst_report.get("deficiencies", []):
        assert d.get("source_lane") != "forensic", "Forensic detector internal flag leaked to Institution!"

    print("STAGE 4 DECISION GATE & RBAC TESTS PASSED!")

if __name__ == "__main__":
    test_officer_decision_gate_and_rbac()
