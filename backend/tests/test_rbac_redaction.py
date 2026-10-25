import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app

def test_rbac_redaction_for_institution_role():
    client = TestClient(app)

    # 1. Fetch applications
    r_apps = client.get("/applications", headers={"X-Role": "Officer"})
    assert r_apps.status_code == 200
    apps = r_apps.json()
    assert len(apps) > 0
    app_id = apps[0]["id"]

    # 2. Officer request: receives suspicion_score and sufficiency
    r_officer = client.get(f"/reports/{app_id}", headers={"X-Role": "Officer"})
    assert r_officer.status_code == 200
    officer_report = r_officer.json()
    assert "suspicion_score" in officer_report
    assert officer_report["suspicion_score"] is not None
    assert "sufficiency" in officer_report
    assert officer_report["sufficiency"] is not None

    # 3. Institution request: MUST REDACT suspicion_score and forensic detector internals
    r_inst = client.get(f"/reports/{app_id}", headers={"X-Role": "Institution"})
    assert r_inst.status_code == 200
    inst_report = r_inst.json()
    assert inst_report.get("suspicion_score") is None, "CRITICAL RBAC LEAK: suspicion_score exposed to Institution!"
    assert inst_report.get("sufficiency") is None, "CRITICAL RBAC LEAK: sufficiency exposed to Institution!"

    # 4. Check deficiencies redaction for Institution: no forensic flags exposed
    for f in inst_report.get("deficiencies", []):
        assert f.get("source_lane") != "forensic", "CRITICAL RBAC LEAK: forensic flag exposed to Institution!"

    print("RBAC Server-Side Redaction test passed successfully!")

if __name__ == "__main__":
    test_rbac_redaction_for_institution_role()
