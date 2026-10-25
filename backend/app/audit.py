import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from backend.app.models import AuditEntry

GENESIS_HASH = "0" * 64

def calculate_audit_hash(prev_hash: str, actor_role: str, action: str, application_id: Optional[str], doc_id: Optional[str], payload: Dict[str, Any], timestamp_str: str) -> str:
    serialized_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    raw_str = f"{prev_hash}|{actor_role}|{action}|{application_id or ''}|{doc_id or ''}|{serialized_payload}|{timestamp_str}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

def log_audit_event(
    session: Session,
    actor_role: str,
    action: str,
    application_id: Optional[str] = None,
    doc_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None
) -> AuditEntry:
    if payload is None:
        payload = {}

    # Get the latest audit entry to link hashes
    statement = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)
    last_entry = session.exec(statement).first()
    prev_hash = last_entry.current_hash if last_entry else GENESIS_HASH

    now = datetime.now(timezone.utc)
    timestamp_str = now.isoformat()
    current_hash = calculate_audit_hash(
        prev_hash=prev_hash,
        actor_role=actor_role,
        action=action,
        application_id=application_id,
        doc_id=doc_id,
        payload=payload,
        timestamp_str=timestamp_str
    )

    entry = AuditEntry(
        timestamp=now,
        actor_role=actor_role,
        action=action,
        application_id=application_id,
        doc_id=doc_id,
        payload=payload,
        prev_hash=prev_hash,
        current_hash=current_hash
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry

def verify_audit_chain(session: Session) -> Dict[str, Any]:
    statement = select(AuditEntry).order_by(AuditEntry.id.asc())
    entries = session.exec(statement).all()

    if not entries:
        return {
            "valid": True,
            "total_entries": 0,
            "broken_at_id": None,
            "message": "Audit trail is empty (genesis state)."
        }

    expected_prev_hash = GENESIS_HASH
    for entry in entries:
        if entry.prev_hash != expected_prev_hash:
            return {
                "valid": False,
                "total_entries": len(entries),
                "broken_at_id": entry.id,
                "message": f"Hash chain broken at entry #{entry.id}: prev_hash mismatch."
            }

        recalculated_hash = calculate_audit_hash(
            prev_hash=entry.prev_hash,
            actor_role=entry.actor_role,
            action=entry.action,
            application_id=entry.application_id,
            doc_id=entry.doc_id,
            payload=entry.payload or {},
            timestamp_str=entry.timestamp.isoformat()
        )

        if recalculated_hash != entry.current_hash:
            return {
                "valid": False,
                "total_entries": len(entries),
                "broken_at_id": entry.id,
                "message": f"Tampering detected at entry #{entry.id}: current_hash signature mismatch."
            }

        expected_prev_hash = entry.current_hash

    return {
        "valid": True,
        "total_entries": len(entries),
        "broken_at_id": None,
        "message": f"Cryptographic audit chain intact across all {len(entries)} events."
    }
