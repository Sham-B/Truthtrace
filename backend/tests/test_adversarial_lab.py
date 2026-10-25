import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app
from backend.app.db import get_session
from backend.app.audit import verify_audit_chain, AuditEntry

def test_adversarial_lab_rbac():
    client = TestClient(app)
    
    # Institution role should be blocked from all adversarial endpoints (HTTP 403)
    res_docs = client.get("/adversarial/documents", headers={"X-Role": "Institution"})
    assert res_docs.status_code == 403, f"Expected 403 for Institution, got {res_docs.status_code}"
    
    res_wiz = client.get("/adversarial/wizard", headers={"X-Role": "Institution"})
    assert res_wiz.status_code == 403
    
    res_sim = client.post("/adversarial/simulate", json={"base_doc_key": "base_affidavit"}, headers={"X-Role": "Institution"})
    assert res_sim.status_code == 403
    
    # Auditor and Officer should have access (HTTP 200)
    res_auditor = client.get("/adversarial/documents", headers={"X-Role": "Auditor"})
    assert res_auditor.status_code == 200
    
    res_officer = client.get("/adversarial/documents", headers={"X-Role": "Officer"})
    assert res_officer.status_code == 200
    docs = res_officer.json()
    assert len(docs) >= 1
    assert any(d["id"] == "base_affidavit" for d in docs)


def test_adversarial_wizard_scenarios():
    client = TestClient(app)
    res = client.get("/adversarial/wizard", headers={"X-Role": "Officer"})
    assert res.status_code == 200
    scenarios = res.json()
    assert len(scenarios) >= 3
    # Verify key scenario types exist
    scenario_titles = [s["title"] for s in scenarios]
    assert any("Deepfake" in title for title in scenario_titles)
    assert any("Typographic" in title or "White-Out" in title for title in scenario_titles)
    assert any("Seal" in title or "Cryptographic" in title or "QR" in title for title in scenario_titles)


def test_adversarial_simulation_clean_baseline():
    client = TestClient(app)
    payload = {
        "base_doc_key": "base_affidavit",
        "deepfake_photo": False,
        "override_name": "",
        "noise_level": 0.0,
        "rotation_angle": 0.0,
        "corrupt_qr": False,
        "spoof_metadata": False,
        "copy_move": False,
        "jpeg_recompress": False
    }
    res = client.post("/adversarial/simulate", json=payload, headers={"X-Role": "Officer"})
    assert res.status_code == 200
    data = res.json()
    
    assert data["status"] == "verified"
    assert data["suspicion_score"] <= 0.15
    assert "session_id" in data
    assert "detectors" in data
    assert len(data["detectors"]) >= 7
    assert data["flagged_count"] == 0
    
    # All detectors should have passed for clean baseline
    for d in data["detectors"]:
        assert d["status"] == "PASSED"
        assert d["counterfactual_hint"] != ""
        
    assert "audit_entry_id" in data
    assert data["audit_current_hash"] is not None


def test_adversarial_simulation_deepfake_attack():
    client = TestClient(app)
    payload = {
        "base_doc_key": "base_affidavit",
        "deepfake_photo": True,
        "deepfake_intensity": 0.95,
        "override_name": "",
        "noise_level": 0.0,
        "rotation_angle": 0.0
    }
    res = client.post("/adversarial/simulate", json=payload, headers={"X-Role": "Officer"})
    assert res.status_code == 200
    data = res.json()
    
    assert data["status"] in ["manual_review_required", "mismatch_detected"]
    assert data["suspicion_score"] >= 0.25
    assert any("deepfake" in att.lower() for att in data["applied_attacks"])
    assert data["flagged_count"] >= 1
    
    # Deepfake detector probe must be flagged
    deepfake_detector = next((d for d in data["detectors"] if "Deepfake" in d["name"] or "GAN" in d["name"]), None)
    assert deepfake_detector is not None
    assert deepfake_detector["status"] == "FLAGGED"
    assert "frequency domain" in deepfake_detector["plain_language_reason"].lower() or "gan" in deepfake_detector["plain_language_reason"].lower()


def test_adversarial_simulation_text_override_and_corrupt_qr():
    client = TestClient(app)
    payload = {
        "base_doc_key": "base_affidavit",
        "deepfake_photo": False,
        "override_name": "Dr. Malicious Forger",
        "corrupt_qr": True,
        "noise_level": 0.35,
        "rotation_angle": 4.5
    }
    res = client.post("/adversarial/simulate", json=payload, headers={"X-Role": "Officer"})
    assert res.status_code == 200
    data = res.json()
    
    assert data["status"] == "mismatch_detected"
    assert len(data["applied_attacks"]) >= 3
    assert data["flagged_count"] >= 2
    
    # Check text / OCR detector
    ocr_det = next((d for d in data["detectors"] if "OCR" in d["name"] or "Typographic" in d["name"]), None)
    assert ocr_det is not None
    assert ocr_det["status"] == "FLAGGED"
    assert "splicing" in ocr_det["plain_language_reason"].lower() or "override" in ocr_det["plain_language_reason"].lower() or "typography" in ocr_det["plain_language_reason"].lower()
    
    # Check Cryptographic QR detector
    qr_det = next((d for d in data["detectors"] if "QR" in d["name"] or "Signature" in d["name"]), None)
    assert qr_det is not None
    assert qr_det["status"] == "FLAGGED"
    assert "signature" in qr_det["plain_language_reason"].lower() or "seal" in qr_det["plain_language_reason"].lower()


def test_adversarial_export_report_and_audit_integrity():
    client = TestClient(app)
    
    # Run a simulation session first
    payload = {
        "base_doc_key": "base_affidavit",
        "deepfake_photo": True,
        "override_name": "Altered Name Test",
        "corrupt_qr": True
    }
    res = client.post("/adversarial/simulate", json=payload, headers={"X-Role": "Officer"})
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    
    # Export HTML report
    res_report = client.get(f"/adversarial/report/{session_id}", headers={"X-Role": "Officer"})
    assert res_report.status_code == 200
    html_content = res_report.text
    assert "TruthTrace" in html_content
    assert "Adversarial Simulation Report" in html_content
    assert "SIMULATED AUDIT RECORD" in html_content
    assert session_id in html_content
    assert "Deepfake" in html_content
    
    # Test 404 on non-existent report
    res_404 = client.get("/adversarial/report/non_existent_session_999", headers={"X-Role": "Officer"})
    assert res_404.status_code == 404
    
    # Test Audit Trail Hash-Chain Integrity
    db_session = next(get_session())
    try:
        chain_verification = verify_audit_chain(db_session)
        assert chain_verification["valid"] is True, f"Audit chain broken: {chain_verification}"
        assert chain_verification["broken_at_id"] is None
        
        # Verify the logged audit entry is clearly marked as simulated
        last_entry = db_session.query(AuditEntry).filter(AuditEntry.action == "ADVERSARIAL_SIMULATION").order_by(AuditEntry.id.desc()).first()
        assert last_entry is not None
        assert "Simulation" in last_entry.actor_role
        payload_data = last_entry.payload
        assert payload_data.get("is_simulated") is True
        assert payload_data.get("simulation_session_id") == session_id
    finally:
        db_session.close()
