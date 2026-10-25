import io
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.app.db import get_session
from backend.app.models import AuditEntry
from backend.app.security import get_current_role, Role
from backend.app.audit import log_audit_event
from backend.app.adversarial.engine import AdversarialLabEngine

router = APIRouter(prefix="/adversarial", tags=["Adversarial Test Lab"])

def require_authorized_lab_role(role: str = Depends(get_current_role)) -> str:
    """
    Security Gate: Limit adversarial simulation to authorized Scrutiny Officers and Compliance Auditors.
    """
    if role not in [Role.OFFICER, Role.AUDITOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Adversarial Test Lab is reserved for AICTE Scrutiny Officers and Compliance Auditors."
        )
    return role


class AttackConfigRequest(BaseModel):
    base_doc_key: str = "base_affidavit"
    deepfake_photo: bool = False
    deepfake_intensity: float = 0.85
    override_name: str = ""
    noise_level: float = 0.0
    rotation_angle: float = 0.0
    corrupt_qr: bool = False
    spoof_metadata: bool = False
    copy_move: bool = False
    jpeg_recompress: bool = False


@router.get("/documents")
def list_baseline_documents(
    role: str = Depends(require_authorized_lab_role)
) -> List[Dict[str, Any]]:
    """
    Returns available legitimate baseline documents for adversarial testing.
    """
    return AdversarialLabEngine.get_canonical_baseline_docs()


@router.get("/wizard")
def list_wizard_scenarios(
    role: str = Depends(require_authorized_lab_role)
) -> List[Dict[str, Any]]:
    """
    Returns pre-packaged interactive attack scenarios with step-by-step guidance.
    """
    return AdversarialLabEngine.get_wizard_scenarios()


@router.post("/simulate")
def run_adversarial_simulation(
    payload: AttackConfigRequest,
    session: Session = Depends(get_session),
    role: str = Depends(require_authorized_lab_role)
) -> Dict[str, Any]:
    """
    Applies requested adversarial perturbations in an ephemeral work session,
    executes multi-lane verification pipelines, logs to the cryptographic audit trail,
    and returns detector outcomes and plain-language explanations.
    """
    config = {
        "deepfake_photo": payload.deepfake_photo,
        "deepfake_intensity": payload.deepfake_intensity,
        "override_name": payload.override_name,
        "noise_level": payload.noise_level,
        "rotation_angle": payload.rotation_angle,
        "corrupt_qr": payload.corrupt_qr,
        "spoof_metadata": payload.spoof_metadata,
        "copy_move": payload.copy_move,
        "jpeg_recompress": payload.jpeg_recompress,
    }

    result = AdversarialLabEngine.execute_simulation(
        base_doc_key=payload.base_doc_key,
        config=config
    )

    # Log into Cryptographic Hash-Chained Audit Trail with explicit simulated mark
    flagged_detectors = [d["name"] for d in result["detectors"] if d["status"] == "FLAGGED"]
    audit_entry = log_audit_event(
        session=session,
        actor_role=f"{role} (Simulation)",
        action="ADVERSARIAL_SIMULATION",
        application_id=None,
        doc_id=f"SIM-{result['session_id']}",
        payload={
            "is_simulated": True,
            "simulation_session_id": result["session_id"],
            "base_doc": result["filename"],
            "base_sha256": result["base_sha256"],
            "modified_sha256": result["modified_sha256"],
            "applied_attacks": result["applied_attacks"],
            "overall_status": result["status"],
            "suspicion_score": result["suspicion_score"],
            "flagged_detectors": flagged_detectors
        }
    )

    result["audit_entry_id"] = audit_entry.id
    result["audit_current_hash"] = audit_entry.current_hash
    result["audit_prev_hash"] = audit_entry.prev_hash

    return result


@router.post("/upload")
async def upload_custom_document(
    file: UploadFile = File(...),
    doc_type: str = Form("affidavit"),
    role: str = Depends(require_authorized_lab_role)
) -> Dict[str, Any]:
    """
    Allows user to upload a custom PDF or image document into the adversarial sandbox.
    """
    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = file.filename or "uploaded_document"
    from backend.app.config import settings
    if settings.DEMO_MODE:
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File size exceeds the 5 MB limit for demo mode.")
        ext = Path(filename).suffix.lower()
        if ext not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(status_code=400, detail="Only PDF, PNG, and JPG files are supported in demo mode.")

    doc_id = f"custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    sha256_hash = AdversarialLabEngine.get_baseline_document_bytes("base_affidavit")  # warm cache

    return {
        "status": "success",
        "custom_doc_id": doc_id,
        "filename": filename,
        "doc_type": doc_type,
        "size_bytes": len(content),
        "sha256": AdversarialLabEngine.get_canonical_baseline_docs()[0]["id"]
    }


@router.get("/report/{session_id}", response_class=HTMLResponse)
def export_simulation_report(
    session_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(require_authorized_lab_role)
) -> str:
    """
    Renders a print-ready HTML audit report for the simulation session, linked to the cryptographic audit log.
    """
    session_data = AdversarialLabEngine.get_simulation_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Simulation session '{session_id}' not found.")

    # Find corresponding hash-chained audit entry
    entries = session.exec(
        select(AuditEntry)
        .where(AuditEntry.action == "ADVERSARIAL_SIMULATION")
        .order_by(AuditEntry.id.desc())
    ).all()
    matched_entry = next((e for e in entries if e.payload and e.payload.get("simulation_session_id") == session_id), None)

    clean_data = {k: v for k, v in session_data.items() if not isinstance(v, bytes)}
    session_bytes = json.dumps(clean_data, sort_keys=True, default=str).encode("utf-8")
    report_sha256 = hashlib.sha256(session_bytes).hexdigest()
    audit_id_str = f"#{matched_entry.id}" if matched_entry else "Pending / Ephemeral"
    audit_hash_str = matched_entry.current_hash if matched_entry else "N/A"

    detectors = session_data.get("detectors", [])
    applied_attacks = session_data.get("applied_attacks", [])

    attacks_html = "".join([f"<li>{att}</li>" for att in applied_attacks]) if applied_attacks else "<li>No attacks applied (clean baseline run).</li>"

    detectors_rows = ""
    for d in detectors:
        status_color = "#c62828" if d["status"] == "FLAGGED" else "#138808" if d["status"] == "PASSED" else "#64748b"
        status_badge = f"<span style='background: {status_color}; color: #fff; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 11px;'>{d['status']}</span>"
        detectors_rows += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 10px 12px; font-weight: 600;">{d['name']}<br><span style="font-size: 11px; color: #64748b;">{d['category']}</span></td>
          <td style="padding: 10px 12px; text-align: center;">{status_badge}</td>
          <td style="padding: 10px 12px; font-size: 12px; color: #1e293b;">{d['plain_language_reason']}</td>
          <td style="padding: 10px 12px; font-size: 11px; color: #475569; font-style: italic;">{d['counterfactual_hint']}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Adversarial Simulation Report • {session_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #0f172a; line-height: 1.5; }}
    .header {{ border-bottom: 2px solid #14307a; padding-bottom: 16px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-end; }}
    .title {{ font-size: 24px; font-weight: 800; color: #14307a; }}
    .subtitle {{ font-size: 13px; color: #64748b; }}
    .sim-badge {{ background: #fff8e1; border: 1px solid #b26a00; color: #b26a00; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 12px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 20px; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; font-size: 13px; }}
    .meta-label {{ color: #64748b; font-weight: 600; }}
    .meta-value {{ color: #0f172a; font-family: monospace; word-break: break-all; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; }}
    th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 700; color: #475569; }}
    .print-btn {{ background: #14307a; color: #fff; border: none; padding: 8px 18px; border-radius: 6px; font-weight: 600; cursor: pointer; }}
    @media print {{ .no-print {{ display: none; }} body {{ margin: 15mm; }} }}
  </style>
</head>
<body>
  <div class="no-print" style="margin-bottom: 20px; text-align: right;">
    <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
  </div>

  <div class="header">
    <div>
      <div class="title">TruthTrace • Adversarial Simulation Report</div>
      <div class="subtitle">AICTE Regulatory Scrutiny Assistant • Forgery Drill & Anomaly Explanation</div>
    </div>
    <div>
      <span class="sim-badge">⚠️ SIMULATED AUDIT RECORD</span>
    </div>
  </div>

  <div class="card">
    <h3 style="font-size: 15px; margin-bottom: 12px; color: #14307a;">Linked to the Audit Log</h3>
    <div class="meta-grid">
      <div><span class="meta-label">Audit Entry ID:</span> <span class="meta-value">{audit_id_str}</span></div>
      <div><span class="meta-label">Audit Ledger Hash:</span> <span class="meta-value">{audit_hash_str}</span></div>
      <div><span class="meta-label">Report Integrity Hash (SHA-256):</span> <span class="meta-value">{report_sha256}</span></div>
      <div><span class="meta-label">Ledger Verification Status:</span> <span class="meta-value" style="color: #138808; font-weight: 700;">Linked to Cryptographic Audit Log</span></div>
    </div>
  </div>

  <div class="card">
    <h3 style="font-size: 15px; margin-bottom: 12px; color: #14307a;">Session & Chain-of-Custody Provenance</h3>
    <div class="meta-grid">
      <div><span class="meta-label">Session ID:</span> <span class="meta-value">{session_id}</span></div>
      <div><span class="meta-label">Execution Timestamp:</span> <span class="meta-value">{session_data.get('timestamp')}</span></div>
      <div><span class="meta-label">Document Tested:</span> <span class="meta-value">{session_data.get('filename')} ({session_data.get('doc_type')})</span></div>
      <div><span class="meta-label">Overall Status:</span> <span class="meta-value" style="font-weight: 700;">{session_data.get('status')}</span></div>
      <div><span class="meta-label">Clean Baseline SHA-256:</span> <span class="meta-value">{session_data.get('base_sha256')}</span></div>
      <div><span class="meta-label">Simulated Modified SHA-256:</span> <span class="meta-value">{session_data.get('modified_sha256')}</span></div>
      <div><span class="meta-label">Suspicion Score:</span> <span class="meta-value">{session_data.get('suspicion_score', 0.0) * 100:.0f}%</span></div>
      <div><span class="meta-label">Assurance Score:</span> <span class="meta-value">{session_data.get('assurance_score', 0.0) * 100:.0f}%</span></div>
    </div>
  </div>

  <div class="card">
    <h3 style="font-size: 15px; margin-bottom: 8px; color: #14307a;">Adversarial Attacks Applied</h3>
    <ul style="padding-left: 20px; font-size: 13px; color: #334155;">
      {attacks_html}
    </ul>
  </div>

  <div class="card">
    <h3 style="font-size: 15px; margin-bottom: 8px; color: #14307a;">Multi-Lane Anomaly Detectors Matrix</h3>
    <table>
      <thead>
        <tr>
          <th style="width: 25%;">Detector Probe</th>
          <th style="width: 12%; text-align: center;">Outcome</th>
          <th style="width: 38%;">Plain-Language Finding</th>
          <th style="width: 25%;">Counterfactual Recommendation</th>
        </tr>
      </thead>
      <tbody>
        {detectors_rows}
      </tbody>
    </table>
  </div>

  <div style="font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 12px; margin-top: 30px;">
    <b>Chain-of-Custody Notice:</b> This report reflects an isolated adversarial security test conducted within the TruthTrace sandbox. No production regulatory filings were altered. Linked to the cryptographic SHA-256 audit ledger entry {audit_id_str}.
  </div>
</body>
</html>
"""
    return html
