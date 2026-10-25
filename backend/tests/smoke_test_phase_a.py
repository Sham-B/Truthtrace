import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.synth.seed import seed_database
from backend.app.models import StatusEnum

def run_phase_a_smoke_test():
    print("\n--- RUNNING PHASE A SMOKE TEST ---")
    # 1. Initialize and force-seed database
    print("[1/8] Seeding database with 12 institutions and 3 test applications...")
    seed_database(force=True)

    client = TestClient(app)

    # 2. Test /health endpoint
    print("[2/8] Testing /health...")
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    assert res.json()["status"] == "healthy"

    # 3. Test /applications endpoint
    print("[3/8] Testing /applications list...")
    res = client.get("/applications", headers={"X-Role": "Officer"})
    assert res.status_code == 200
    apps = res.json()
    assert len(apps) >= 3, f"Expected at least 3 seeded applications, got {len(apps)}"
    app_ids = [a["id"] for a in apps]
    assert "APP-2026-001" in app_ids
    assert "APP-2026-002" in app_ids
    assert "APP-2026-003" in app_ids

    # 4. Verify Application 1 (Clean Verified)
    print("[4/8] Testing Application 1 (Clean)...")
    res1 = client.get("/applications/APP-2026-001/report", headers={"X-Role": "Officer"})
    assert res1.status_code == 200
    report1 = res1.json()
    assert report1["overall_status"] == StatusEnum.VERIFIED
    assert len(report1["deficiencies"]) == 0

    # 5. Verify Application 2 (Content Mismatch: Address & Fee)
    print("[5/8] Testing Application 2 (Content Discrepancy)...")
    res2 = client.get("/applications/APP-2026-002/report", headers={"X-Role": "Officer"})
    assert res2.status_code == 200
    report2 = res2.json()
    assert report2["overall_status"] == StatusEnum.MISMATCH_DETECTED
    assert len(report2["deficiencies"]) >= 2
    # Check flags have required fields
    for flag in report2["deficiencies"]:
        assert "reason_code" in flag
        assert "plain_language_reason" in flag
        assert "evidence" in flag
        assert "rule_id" in flag
        assert "source_lane" in flag
        assert "benign_explanations" in flag
        assert len(flag["benign_explanations"]) >= 1

    # 6. Verify Application 3 (Provenance Mismatch: Tampered Ed25519 Seal)
    print("[6/8] Testing Application 3 (Provenance Signature Forgery)...")
    res3 = client.get("/applications/APP-2026-003/report", headers={"X-Role": "Officer"})
    assert res3.status_code == 200
    report3 = res3.json()
    assert report3["overall_status"] == StatusEnum.MISMATCH_DETECTED
    prov_flags = [f for f in report3["deficiencies"] if f["source_lane"] == "provenance"]
    assert len(prov_flags) >= 1
    assert any("SIGNATURE" in f["reason_code"] for f in prov_flags)

    # 7. Test RBAC: Institution role must NOT see suspicion score or forensic internals
    print("[7/8] Testing RBAC Guardrails for Institution role...")
    inst_res = client.get("/applications", headers={"X-Role": "Institution"})
    assert inst_res.status_code == 200
    inst_apps = inst_res.json()
    for a in inst_apps:
        assert a["suspicion_score"] is None, "Institution role leaked suspicion score!"

    # 8. Test Non-Negotiable: AI endpoints cannot set adverse outcome; Officer decision required
    print("[8/8] Testing Non-Negotiable: Adverse action requires Officer with written reason...")
    # Validate endpoint should NOT set adverse action
    val_res = client.post("/applications/APP-2026-002/validate", headers={"X-Role": "Officer"})
    assert val_res.status_code == 200
    app2_detail = client.get("/applications/APP-2026-002", headers={"X-Role": "Officer"}).json()
    assert app2_detail["adverse_action"] is None, "AI validation automatically set an adverse outcome!"

    # Officer decision with missing/short reason must fail (400)
    fail_dec = client.post(
        "/decisions",
        json={"application_id": "APP-2026-002", "action": "reject", "written_reason": "short"},
        headers={"X-Role": "Officer"}
    )
    assert fail_dec.status_code == 400

    # Institution role attempting decision must be forbidden (403)
    inst_dec = client.post(
        "/decisions",
        json={"application_id": "APP-2026-002", "action": "reject", "written_reason": "Attempting reject as institution"},
        headers={"X-Role": "Institution"}
    )
    assert inst_dec.status_code == 403

    # Valid Officer decision
    officer_dec = client.post(
        "/decisions",
        json={
            "application_id": "APP-2026-002",
            "action": "refer_for_inspection",
            "written_reason": "Address in registered lease deed contradicts institutional campus location record; Scrutiny committee inspection ordered."
        },
        headers={"X-Role": "Officer", "X-Officer-Id": "SCRUTINY-OFFICER-701"}
    )
    assert officer_dec.status_code == 200
    assert officer_dec.json()["officer_action"] == "refer_for_inspection"

    # Verify audit chain integrity
    audit_ver = client.get("/audit/verify").json()
    assert audit_ver["valid"] is True, f"Audit chain broken: {audit_ver['message']}"

    print("\n>>> ALL PHASE A SMOKE TESTS PASSED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    run_phase_a_smoke_test()
