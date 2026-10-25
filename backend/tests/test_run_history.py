import sys
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlmodel import Session, select

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app
from backend.app.db import engine
from backend.app.models import Application, ValidationRun, AuditEntry, Document, Claim
from backend.app.audit import verify_audit_chain
from backend.app.engine.runs import diff_runs, compute_snapshot, record_run

def test_diff_runs_correctness_and_value_changed():
    """Test introduced, resolved, and persisting (with value-changed flag) in diff_runs."""
    f1 = {
        "fingerprint": "fp-1",
        "reason_code": "EXPIRED",
        "doc_type": "accreditation_certificate",
        "field": "valid_upto",
        "severity": "critical",
        "lane": "content",
        "observed_value": "2024-06-30",
        "expected_value": "future date",
        "plain_title": "Expired Document",
        "plain_reason": "Document expired in 2024"
    }
    f2_v1 = {
        "fingerprint": "fp-2",
        "reason_code": "AREA_MISMATCH",
        "doc_type": "lease_deed",
        "field": "built_up_area",
        "severity": "high",
        "lane": "content",
        "observed_value": "45000",
        "expected_value": "50000",
        "plain_title": "Area Deficit",
        "plain_reason": "Observed 45000 sq ft, required 50000"
    }
    f2_v2 = {
        "fingerprint": "fp-2",
        "reason_code": "AREA_MISMATCH",
        "doc_type": "lease_deed",
        "field": "built_up_area",
        "severity": "high",
        "lane": "content",
        "observed_value": "48000",  # Value changed
        "expected_value": "50000",
        "plain_title": "Area Deficit",
        "plain_reason": "Observed 48000 sq ft, required 50000"
    }
    f3 = {
        "fingerprint": "fp-3",
        "reason_code": "TRUST_ISSUE",
        "doc_type": "land_registry",
        "field": "trust_name",
        "severity": "medium",
        "lane": "cross_check",
        "observed_value": "ABC Trust",
        "expected_value": "XYZ Trust",
        "plain_title": "Name Mismatch",
        "plain_reason": "Trust name discrepancy"
    }

    # Run 1 has f1 and f2_v1
    run1 = {
        "run_number": 1,
        "status_at_run": "flagged",
        "findings_json": [f1, f2_v1],
        "snapshot_json": {
            "rules_version": "rules-hash-1",
            "documents": {"accreditation_certificate": {"version": 1}, "lease_deed": {"version": 1}}
        }
    }
    # Run 2 has f2_v2 and f3 (f1 resolved, f3 introduced, f2 persisting with value changed)
    run2 = {
        "run_number": 2,
        "status_at_run": "flagged",
        "findings_json": [f2_v2, f3],
        "snapshot_json": {
            "rules_version": "rules-hash-1",
            "documents": {"accreditation_certificate": {"version": 2}, "lease_deed": {"version": 1}}
        }
    }

    diff = diff_runs(run1, run2)
    assert len(diff["resolved"]) == 1
    assert diff["resolved"][0]["fingerprint"] == "fp-1"
    assert diff["resolved"][0]["reason_code"] == "EXPIRED"

    assert len(diff["introduced"]) == 1
    assert diff["introduced"][0]["fingerprint"] == "fp-3"

    assert len(diff["persisting"]) == 1
    assert diff["persisting"][0]["fingerprint"] == "fp-2"
    assert diff["persisting"][0]["changed"] is True
    assert diff["persisting"][0]["was_observed"] == "45000"
    assert diff["persisting"][0]["now_observed"] == "48000"

    assert diff["rules_changed"] is False
    assert len(diff["documents_changed"]) == 1
    assert diff["documents_changed"][0]["doc_type"] == "accreditation_certificate"
    assert diff["documents_changed"][0]["from_version"] == 1
    assert diff["documents_changed"][0]["to_version"] == 2

    assert "Accreditation certificate was replaced (v1 to v2)" in diff["explanation"]
    assert "1 issue fixed, 1 new, 1 still open" in diff["explanation"]

def test_rules_changed_detection_in_diff():
    """Test rules_changed flag when rules_version differs between checks."""
    run1 = {
        "run_number": 1,
        "status_at_run": "verified",
        "findings_json": [],
        "snapshot_json": {"rules_version": "v1-hash", "documents": {}}
    }
    run2 = {
        "run_number": 2,
        "status_at_run": "verified",
        "findings_json": [],
        "snapshot_json": {"rules_version": "v2-hash", "documents": {}}
    }
    diff = diff_runs(run1, run2)
    assert diff["rules_changed"] is True
    assert "Validation rules were updated" in diff["explanation"]

def test_identical_snapshot_deduplication():
    """Test that validating without changes returns reused=True and does not create duplicate run rows."""
    client = TestClient(app)
    # Ensure seeded
    client.post("/demo/reset-seed")

    # Get Check #1 count
    r_runs1 = client.get("/applications/APP-2026-001/runs", headers={"X-Role": "Officer"})
    assert r_runs1.status_code == 200
    runs1 = r_runs1.json()
    initial_count = len(runs1)
    assert initial_count >= 1

    # Call validate again without any document changes
    r_val = client.post("/applications/APP-2026-001/validate", headers={"X-Role": "Officer"})
    assert r_val.status_code == 200
    val_data = r_val.json()
    assert val_data.get("reused") is True
    assert "Nothing has changed" in val_data.get("message", "")

    # Count of runs must not increase
    r_runs2 = client.get("/applications/APP-2026-001/runs", headers={"X-Role": "Officer"})
    runs2 = r_runs2.json()
    assert len(runs2) == initial_count

def test_immutability_no_update_or_delete():
    """Verify there are no endpoints to update or delete runs."""
    client = TestClient(app)
    r_put = client.put("/applications/APP-2026-001/runs/1", json={"status": "manipulated"})
    assert r_put.status_code in [404, 405]

    r_patch = client.patch("/applications/APP-2026-001/runs/1", json={"findings": []})
    assert r_patch.status_code in [404, 405]

    r_del = client.delete("/applications/APP-2026-001/runs/1")
    assert r_del.status_code in [404, 405]

def test_determinism_of_repeated_checks():
    """Verify that compute_snapshot and findings produce identical hashes for identical data."""
    with Session(engine) as session:
        app_obj = session.get(Application, "APP-2026-001")
        assert app_obj is not None
        docs = session.exec(select(Document).where(Document.application_id == "APP-2026-001")).all()
        claims = session.exec(select(Claim).where(Claim.application_id == "APP-2026-001")).all()
        snap1, hash1, rules1 = compute_snapshot(session, app_obj, docs, claims)
        snap2, hash2, rules2 = compute_snapshot(session, app_obj, docs, claims)
        assert hash1 == hash2
        assert snap1 == snap2
        assert rules1 == rules2

def test_replacement_resolving_expired_finding():
    """Test uploading corrected certificate to APP-2026-003 creates Check #2 resolving expired deficiency."""
    client = TestClient(app)
    client.post("/demo/reset-seed")

    # Check #1 for APP-2026-003 has expired certificate finding
    r_run1 = client.get("/applications/APP-2026-003/runs/1", headers={"X-Role": "Officer"})
    assert r_run1.status_code == 200
    run1 = r_run1.json()
    assert run1["counts"]["critical"] == 1
    assert any("expired" in str(f).lower() for f in run1["findings_json"])

    # Upload corrected accreditation certificate
    pdf_path = REPO_ROOT / "backend" / "synth" / "samples" / "corrected_accreditation_certificate.pdf"
    assert pdf_path.exists(), f"Sample corrected PDF missing at {pdf_path}"

    with open(pdf_path, "rb") as f:
        r_rep = client.post(
            "/applications/APP-2026-003/replace-document",
            headers={"X-Role": "Officer"},
            data={"doc_type": "accreditation_certificate"},
            files={"file": ("corrected_accreditation_certificate.pdf", f, "application/pdf")}
        )
    assert r_rep.status_code == 200
    rep_data = r_rep.json()
    assert rep_data.get("run_number") == 2
    assert "Check #2 recorded" in rep_data.get("message", "")

    # Check diff between run 1 and run 2
    r_diff = client.get("/applications/APP-2026-003/runs/diff?from=1&to=2", headers={"X-Role": "Officer"})
    assert r_diff.status_code == 200
    diff = r_diff.json()
    assert len(diff["resolved"]) == 1
    assert diff["resolved"][0]["doc_type"] == "accreditation_certificate"
    assert len(diff["introduced"]) == 0
    assert len(diff["persisting"]) == 0
    assert "Accreditation certificate was replaced" in diff["explanation"]
    assert "1 issue fixed" in diff["explanation"]

def test_institution_role_redaction():
    """Verify College role sees only content lane plain findings, no scores, lane names, or hashes."""
    client = TestClient(app)
    # Check runs list as Institution
    r_runs = client.get("/applications/APP-2026-003/runs", headers={"X-Role": "Institution"})
    assert r_runs.status_code == 200
    runs = r_runs.json()
    for r in runs:
        # Snapshot hash must be None or redacted for institution
        assert r.get("snapshot_hash") is None
        assert r.get("rules_version") is None
        for f in r.get("findings_json", []):
            assert "source_lane" not in f
            assert "lane" not in f
            assert "suspicion_score" not in f
            assert "assurance_score" not in f
            assert f.get("lane") is None

    # Check diff as Institution
    r_diff = client.get("/applications/APP-2026-003/runs/diff", headers={"X-Role": "Institution"})
    assert r_diff.status_code == 200
    diff = r_diff.json()
    for category in ["introduced", "resolved", "persisting"]:
        for f in diff.get(category, []):
            assert "source_lane" not in f
            assert "lane" not in f
            assert "suspicion_score" not in f
            assert "assurance_score" not in f

def test_audit_chain_integrity_with_run_recorded():
    """Verify RUN_RECORDED is present in audit chain and verify_audit_chain passes."""
    client = TestClient(app)

    # Check audit verify
    r_audit = client.get("/audit/verify")
    assert r_audit.status_code == 200
    assert r_audit.json()["valid"] is True

    # Confirm RUN_RECORDED events are in audit entries
    with Session(engine) as session:
        entries = session.exec(select(AuditEntry).where(AuditEntry.action == "RUN_RECORDED")).all()
        assert len(entries) >= 5, f"Expected at least 5 RUN_RECORDED events from seed, found {len(entries)}"
        sample = entries[0]
        assert "run_number" in sample.payload
        assert "snapshot_hash" in sample.payload
        assert "counts" in sample.payload

def test_simulations_do_not_create_runs():
    """Ensure Adversarial Test Lab simulations never create rows in ValidationRun."""
    client = TestClient(app)
    # Get run count for APP-2026-001
    r_before = client.get("/applications/APP-2026-001/runs", headers={"X-Role": "Officer"})
    count_before = len(r_before.json())

    # Run adversarial attack simulation on APP-2026-001
    payload = {
        "base_doc_key": "base_affidavit",
        "deepfake_photo": False,
        "override_name": "Test Simulation Run",
        "noise_level": 0.0,
        "rotation_angle": 0.0,
        "corrupt_qr": False,
        "spoof_metadata": False,
        "copy_move": False,
        "splices": [],
        "ai_forgery": False
    }
    r_sim = client.post("/adversarial/simulate", json=payload, headers={"X-Role": "Officer"})
    assert r_sim.status_code == 200

    # Ensure run count did not change
    r_after = client.get("/applications/APP-2026-001/runs", headers={"X-Role": "Officer"})
    count_after = len(r_after.json())
    assert count_after == count_before, "Simulation erroneously created a ValidationRun!"

def test_revision_guard_conflict_409():
    """Verify that if an application's revision changed during validation, 409 Conflict is returned."""
    with Session(engine) as session:
        app_obj = session.get(Application, "APP-2026-001")
        assert app_obj is not None
        current_rev = app_obj.revision
        # Calling record_run with a stale revision must raise 409 Conflict
        with pytest.raises(HTTPException) as exc_info:
            record_run(
                session=session,
                app_id="APP-2026-001",
                trigger="manual",
                actor_role="Officer",
                expected_revision=current_rev - 1
            )
        assert exc_info.value.status_code == 409
        assert "Concurrent conflict" in exc_info.value.detail
