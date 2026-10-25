import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlmodel import Session, select
from fastapi import HTTPException, status

from backend.app.config import RULES_DIR
from backend.app.models import Application, Document, Claim, MockAICTERecord, ValidationRun
from backend.app.mock_issuers.router import _CHAOS_STATE
from backend.app.audit import log_audit_event

_REASON_CODE_TITLES = {
    "PID_FORMAT_INVALID": "Permanent Institute ID Format",
    "PID_MASTER_MISMATCH": "Permanent Institute ID Discrepancy",
    "NAME_FUZZY_MISMATCH": "Institution Name Discrepancy",
    "ADDRESS_FUZZY_MISMATCH": "Campus Address Discrepancy",
    "DOC_EXPIRED": "Document Expiration",
    "LEASE_EXPIRED": "Lease Deed Tenure Expired",
    "NBA_EXPIRED": "Accreditation Certificate Expired",
    "TER_FEE_INSUFFICIENT": "Regulatory Fee Deficit",
    "TER_TXN_MISMATCH": "Payment Transaction ID Mismatch",
    "QR_DECODE_FAILED": "Missing Cryptographic QR Seal",
    "QR_SIG_INVALID": "Invalid Digital Signature",
    "FOR_ELA_RESIDUAL": "Error Level Compression Anomaly",
    "FOR_NOISE_DISPARITY": "Sensor Noise Disparity",
    "FOR_CLONE_ORB": "Visual Copy-Move Patching",
    "FOR_META_PRODUCER": "Editing Software Metadata",
    "FOR_FONT_SPLICE": "Typographic Font Splicing",
    "REUSE_RING_DOC_COLLISION": "Multi-College Document Number Collision",
    "DEEPFAKE_FACE_SYNTHESIS": "Synthetic Deepfake Face ID",
    "TEMP_CHRONOLOGY_INVALID": "Chronological Sequence Conflict",
    "IR_CAMPUS_ADDR_DIVERGENCE": "Cross-Document Address Conflict"
}


def compute_rules_version() -> str:
    """
    Computes a deterministic SHA-256 hash over the sorted contents of all YAML files in rules/.
    """
    yaml_files = sorted(RULES_DIR.rglob("*.yaml"))
    h = hashlib.sha256()
    for yf in yaml_files:
        rel_path = str(yf.relative_to(RULES_DIR)).replace("\\", "/")
        h.update(rel_path.encode("utf-8"))
        try:
            content = yf.read_bytes()
            h.update(content)
        except Exception:
            pass
    return h.hexdigest()


def compute_snapshot(
    session: Session,
    app_obj: Application,
    docs: List[Document],
    claims: List[Claim],
    aicte_record: Optional[MockAICTERecord] = None
) -> Tuple[Dict[str, Any], str, str]:
    """
    Builds the immutable snapshot dictionary and its canonical SHA-256 hash.
    Returns: (snapshot_json, snapshot_hash, rules_version)
    """
    # 1. Documents (type, version, sha256) - active latest version for each doc_type
    latest_docs_by_type = {}
    for d in docs:
        if d.doc_type not in latest_docs_by_type or (d.version or 1) > (latest_docs_by_type[d.doc_type].version or 1):
            latest_docs_by_type[d.doc_type] = d
    active_docs = list(latest_docs_by_type.values())

    doc_entries = []
    for d in sorted(active_docs, key=lambda x: (x.doc_type, x.version or 1)):
        doc_entries.append({
            "doc_type": d.doc_type,
            "version": d.version or 1,
            "sha256": d.sha256_hash or ""
        })

    # 2. Normalized extracted claims for active documents
    active_doc_ids = set(d.id for d in active_docs)
    doc_type_by_id = {d.id: d.doc_type for d in active_docs}
    extracted_claims = {}
    for c in sorted(claims, key=lambda x: (doc_type_by_id.get(x.doc_id, ""), x.field)):
        if c.doc_id in active_doc_ids:
            dt = doc_type_by_id.get(c.doc_id, "document")
            key = f"{dt}:{c.field}"
            extracted_claims[key] = str(c.normalized_value or c.value or "")

    # 3. Applied checklist id
    checklist_id = (app_obj.category or "eoa_renewal").lower()

    # 4. Rules version
    rules_version = compute_rules_version()

    # 5. Master record hash
    if aicte_record:
        rec_dict = aicte_record.model_dump()
        master_hash = hashlib.sha256(json.dumps(rec_dict, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    else:
        master_hash = "none"

    # 6. Evaluation date (DATE only, so same-day reruns are identical)
    evaluation_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 7. Issuer availability demo state
    issuer_state = {k: bool(_CHAOS_STATE[k].get("down", False)) for k in sorted(_CHAOS_STATE.keys())}

    snapshot_json = {
        "documents": doc_entries,
        "extracted_claims": extracted_claims,
        "checklist_id": checklist_id,
        "rules_version": rules_version,
        "master_record_hash": master_hash,
        "evaluation_date": evaluation_date,
        "issuer_availability": issuer_state
    }

    serialized = json.dumps(snapshot_json, sort_keys=True)
    snapshot_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return snapshot_json, snapshot_hash, rules_version


def build_findings_list(
    unique_findings: List[Dict[str, Any]],
    docs_by_id: Dict[str, Document]
) -> List[Dict[str, Any]]:
    """
    Normalizes findings into structured dictionaries with SHA-1 fingerprints:
    fingerprint = sha1(reason_code|doc_type|field or "document")
    """
    findings = []
    for f in unique_findings:
        reason_code = f.get("reason_code") or f.get("rule_id", "UNKNOWN")
        doc_id = f.get("doc_id", "")
        doc_obj = docs_by_id.get(doc_id)
        doc_type = doc_obj.doc_type if doc_obj else f.get("doc_type", "document")
        field = f.get("claim_field", "")

        raw_fingerprint = f"{reason_code}|{doc_type}|{field or 'document'}"
        fingerprint = hashlib.sha1(raw_fingerprint.encode("utf-8")).hexdigest()

        # Severity classification: critical for invalidating flaws
        sev = f.get("severity", "")
        if not sev:
            critical_codes = [
                "CORRUPT", "FORGED", "EXPIRED", "MISMATCH", "UNAVAILABLE",
                "QR_SIG_INVALID", "LEASE_EXPIRED", "NBA_EXPIRED"
            ]
            if any(term in reason_code.upper() for term in critical_codes):
                sev = "critical"
            else:
                sev = "warning"

        plain_title = _REASON_CODE_TITLES.get(reason_code, reason_code.replace("_", " ").title())
        plain_reason = f.get("plain_language_reason", "")
        observed_val = f.get("claim_value", "")
        expected_val = f.get("expected_value", "")
        lane = f.get("source_lane", "content")
        page = f.get("evidence", {}).get("page", 0) if isinstance(f.get("evidence"), dict) else 0
        bbox = f.get("evidence", {}).get("bbox", [0.0, 0.0, 0.0, 0.0]) if isinstance(f.get("evidence"), dict) else [0.0, 0.0, 0.0, 0.0]

        findings.append({
            "fingerprint": fingerprint,
            "reason_code": reason_code,
            "doc_type": doc_type,
            "field": field,
            "severity": sev,
            "lane": lane,
            "observed_value": observed_val,
            "expected_value": expected_val,
            "plain_title": plain_title,
            "plain_reason": plain_reason,
            "doc_id": doc_id,
            "page": page,
            "bbox": bbox
        })

    # Sort deterministically by fingerprint
    findings.sort(key=lambda x: x["fingerprint"])
    return findings


def _get_run_field(run: Any, field: str, default: Any = None) -> Any:
    if isinstance(run, dict):
        return run.get(field, default)
    return getattr(run, field, default)


def diff_runs(from_run: Any, to_run: Any) -> Dict[str, Any]:
    """
    Compares two validation runs to determine:
    - introduced[] (new)
    - resolved[] (fixed)
    - persisting[] (still open, with changed:bool plus was/now observed values)
    - rules_changed: bool
    - documents_changed: List[{doc_type, from_version, to_version}]
    - status_from, status_to
    - deterministic one-sentence plain explanation
    """
    raw_from_findings = _get_run_field(from_run, "findings_json") or []
    if isinstance(raw_from_findings, str):
        raw_from_findings = json.loads(raw_from_findings)
    raw_to_findings = _get_run_field(to_run, "findings_json") or []
    if isinstance(raw_to_findings, str):
        raw_to_findings = json.loads(raw_to_findings)

    from_map = {f["fingerprint"]: f for f in raw_from_findings}
    to_map = {f["fingerprint"]: f for f in raw_to_findings}

    introduced = [to_map[fp] for fp in to_map if fp not in from_map]
    resolved = [from_map[fp] for fp in from_map if fp not in to_map]

    persisting = []
    for fp, f_to in to_map.items():
        if fp in from_map:
            f_from = from_map[fp]
            item = dict(f_to)
            val_from = str(f_from.get("observed_value", ""))
            val_to = str(f_to.get("observed_value", ""))
            changed = (val_from != val_to and bool(val_from) and bool(val_to))
            item["changed"] = changed
            item["was_observed"] = f_from.get("observed_value")
            item["now_observed"] = f_to.get("observed_value")
            persisting.append(item)

    # Sort outputs deterministically
    introduced.sort(key=lambda x: x["fingerprint"])
    resolved.sort(key=lambda x: x["fingerprint"])
    persisting.sort(key=lambda x: x["fingerprint"])

    # Snapshot documents
    snap_from = _get_run_field(from_run, "snapshot_json") or {}
    if isinstance(snap_from, str):
        snap_from = json.loads(snap_from)
    snap_to = _get_run_field(to_run, "snapshot_json") or {}
    if isinstance(snap_to, str):
        snap_to = json.loads(snap_to)

    rules_from = _get_run_field(from_run, "rules_version", "") or snap_from.get("rules_version", "")
    rules_to = _get_run_field(to_run, "rules_version", "") or snap_to.get("rules_version", "")
    rules_changed = bool(rules_from != rules_to)

    raw_from_docs = snap_from.get("documents", [])
    if isinstance(raw_from_docs, dict):
        from_docs = {k: {"doc_type": k, **v} if isinstance(v, dict) else {"doc_type": k, "version": v} for k, v in raw_from_docs.items()}
    elif isinstance(raw_from_docs, list):
        from_docs = {d["doc_type"]: d for d in raw_from_docs}
    else:
        from_docs = {}

    raw_to_docs = snap_to.get("documents", [])
    if isinstance(raw_to_docs, dict):
        to_docs = {k: {"doc_type": k, **v} if isinstance(v, dict) else {"doc_type": k, "version": v} for k, v in raw_to_docs.items()}
    elif isinstance(raw_to_docs, list):
        to_docs = {d["doc_type"]: d for d in raw_to_docs}
    else:
        to_docs = {}

    documents_changed = []
    for dtype, d_to in to_docs.items():
        d_from = from_docs.get(dtype)
        if not d_from:
            documents_changed.append({
                "doc_type": dtype,
                "from_version": 0,
                "to_version": d_to.get("version", 1)
            })
        elif d_to.get("version") != d_from.get("version") or d_to.get("sha256") != d_from.get("sha256"):
            documents_changed.append({
                "doc_type": dtype,
                "from_version": d_from.get("version", 1),
                "to_version": d_to.get("version", 1)
            })

    # Sort documents_changed deterministically
    documents_changed.sort(key=lambda x: x["doc_type"])

    # Generate deterministic one-sentence plain explanation
    from_num = _get_run_field(from_run, "run_number", 1)
    to_num = _get_run_field(to_run, "run_number", 2)
    status_from = _get_run_field(from_run, "status_at_run", "flagged")
    status_to = _get_run_field(to_run, "status_at_run", "verified")

    reason_parts = []
    if documents_changed:
        for dc in documents_changed:
            friendly_name = dc["doc_type"].replace("_", " ").capitalize()
            if "certificate" not in friendly_name.lower() and "deed" not in friendly_name.lower() and "affidavit" not in friendly_name.lower() and "receipt" not in friendly_name.lower() and "noc" not in friendly_name.lower():
                friendly_name += " document"
            reason_parts.append(f"{friendly_name} was replaced (v{dc['from_version']} to v{dc['to_version']})")
        reason_str = ", ".join(reason_parts) + ". "
    elif rules_changed:
        reason_str = "Validation rules were updated. "
    else:
        reason_str = ""

    counts_str = f"{len(resolved)} issue{'s' if len(resolved) != 1 else ''} fixed, {len(introduced)} new, {len(persisting)} still open."
    plain_explanation = f"Since Check #{from_num}: {reason_str}{counts_str}"

    return {
        "from_run_number": from_num,
        "to_run_number": to_num,
        "status_from": status_from,
        "status_to": status_to,
        "introduced": introduced,
        "resolved": resolved,
        "persisting": persisting,
        "rules_changed": rules_changed,
        "documents_changed": documents_changed,
        "plain_explanation": plain_explanation,
        "explanation": plain_explanation
    }


def record_run(
    session: Session,
    app_id: str,
    trigger: str = "manual",
    actor_role: str = "Officer",
    unique_findings: Optional[List[Dict[str, Any]]] = None,
    expected_revision: Optional[int] = None
) -> Dict[str, Any]:
    """
    Records an immutable ValidationRun for the application.
    Enforces revision guardrails and snapshot idempotency.
    """
    app_obj = session.get(Application, app_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    # Revision guard
    if expected_revision is not None and app_obj.revision != expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Concurrent conflict: Application revision changed from {expected_revision} to {app_obj.revision} during validation."
        )

    docs = session.exec(select(Document).where(Document.application_id == app_id)).all()
    claims = session.exec(select(Claim).where(Claim.application_id == app_id)).all()
    aicte_record = session.get(MockAICTERecord, app_obj.institution_id)

    snapshot_json, snapshot_hash, rules_version = compute_snapshot(
        session=session,
        app_obj=app_obj,
        docs=docs,
        claims=claims,
        aicte_record=aicte_record
    )

    # Check latest run for idempotency
    latest_run = session.exec(
        select(ValidationRun)
        .where(ValidationRun.application_id == app_id)
        .order_by(ValidationRun.run_number.desc())
    ).first()

    if latest_run and latest_run.snapshot_hash == snapshot_hash:
        return {
            "run": latest_run,
            "reused": True,
            "message": f"Nothing has changed since Check #{latest_run.run_number}",
            "diff": None
        }

    # Prepare findings
    docs_by_id = {d.id: d for d in docs}
    if unique_findings is None:
        # Import lazily if not provided
        from backend.app.main import extract_unique_findings
        unique_findings = extract_unique_findings(claims, session=session, app_id=app_id)

    findings_json = build_findings_list(unique_findings, docs_by_id)

    critical_count = sum(1 for f in findings_json if f.get("severity") == "critical")
    open_count = len(findings_json)
    counts = {
        "open": open_count,
        "critical": critical_count
    }

    run_number = (latest_run.run_number + 1) if latest_run else 1

    run = ValidationRun(
        application_id=app_id,
        run_number=run_number,
        created_at=datetime.now(timezone.utc),
        trigger=trigger,
        actor_role=actor_role,
        snapshot_json=snapshot_json,
        snapshot_hash=snapshot_hash,
        rules_version=rules_version,
        status_at_run=app_obj.status,
        findings_json=findings_json,
        counts=counts,
        revision=app_obj.revision
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Audit logging for RUN_RECORDED with delta counts
    delta_open = counts["open"] - (latest_run.counts.get("open", 0) if latest_run and latest_run.counts else 0)
    delta_critical = counts["critical"] - (latest_run.counts.get("critical", 0) if latest_run and latest_run.counts else 0)

    log_audit_event(
        session=session,
        actor_role=actor_role,
        action="RUN_RECORDED",
        application_id=app_id,
        payload={
            "run_id": run.id,
            "run_number": run.run_number,
            "snapshot_hash": run.snapshot_hash,
            "trigger": trigger,
            "status_at_run": run.status_at_run,
            "counts": counts,
            "delta_counts": {
                "open_delta": delta_open,
                "critical_delta": delta_critical
            }
        }
    )

    diff = diff_runs(latest_run, run) if latest_run else None

    return {
        "run": run,
        "reused": False,
        "diff": diff
    }
