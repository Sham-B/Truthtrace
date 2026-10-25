import io
import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app
from backend.synth.generate_docs import DocumentGenerator

def test_institution_preflight_and_versioned_replacement():
    client = TestClient(app)

    # 1. Fetch applications
    r_apps = client.get("/applications", headers={"X-Role": "Institution"})
    assert r_apps.status_code == 200
    apps = r_apps.json()
    assert len(apps) > 0
    app_id = apps[0]["id"]

    # 2. Run Pre-Flight check as Institution
    r_pre = client.post(f"/applications/{app_id}/preflight", headers={"X-Role": "Institution"})
    assert r_pre.status_code == 200
    pre_data = r_pre.json()
    assert "deficiencies" in pre_data
    assert "deficiency_count" in pre_data

    # 3. Test versioned document replacement
    clean_lease_pdf = DocumentGenerator.generate_lease_deed_pdf(
        inst_name="Aryabhata Institute of Engineering & Technology",
        pid="1-1029384751",
        address="Plot 12, Institutional Area, Sector 62, Noida, Uttar Pradesh - 201309"
    )

    files = {
        "file": ("Updated_Lease_Deed_v2.pdf", io.BytesIO(clean_lease_pdf), "application/pdf")
    }
    data = {"doc_type": "lease_deed"}

    r_repl = client.post(
        f"/applications/{app_id}/replace-document",
        headers={"X-Role": "Institution"},
        files=files,
        data=data
    )
    assert r_repl.status_code == 200, f"Replace failed: {r_repl.text}"
    repl_data = r_repl.json()
    assert repl_data["status"] == "success"
    assert repl_data["version"] >= 2
    assert "document_id" in repl_data

    # 4. Verify audit entry logged for replacement
    r_audit = client.get("/audit", headers={"X-Role": "Auditor"})
    assert r_audit.status_code == 200
    audit_entries = r_audit.json()
    assert any(e["action"] == "DOCUMENT_REPLACED" for e in audit_entries)

    print("Stage 8 (Institution Pre-Flight & Document Versioning) passed successfully!")

if __name__ == "__main__":
    test_institution_preflight_and_versioned_replacement()
