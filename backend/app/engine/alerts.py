import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import yaml
from sqlmodel import Session, select
from dateutil import parser as date_parser

from backend.app.config import RULES_DIR
from backend.app.models import Application, Document, Claim, Alert, StatusEnum

CATEGORIES_YAML_PATH = RULES_DIR / "categories.yaml"

def load_categories_yaml() -> Dict[str, Any]:
    if CATEGORIES_YAML_PATH.exists():
        try:
            with open(CATEGORIES_YAML_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Alerts] Error loading categories.yaml: {e}")
    return {}


class AlertEngine:
    @classmethod
    def scan_application_alerts(
        cls,
        session: Session,
        application_id: str,
        expiry_warning_days: int = 180
    ) -> List[Alert]:
        """
        Scans an application for the 6 canonical alert categories:
        1. missing (required documents according to categories.yaml)
        2. expiring (lease or certificate expiring within configurable days)
        3. pending_source (issuing authority verification pending or unreachable)
        4. anomaly (forensic or content tamper flags)
        5. reuse (multi-application reuse ring detected)
        6. overdue (scrutiny timeline SLA exceeded)
        """
        app = session.get(Application, application_id)
        if not app:
            return []

        docs = session.exec(select(Document).where(Document.application_id == application_id)).all()
        claims = session.exec(select(Claim).where(Claim.application_id == application_id)).all()

        cats = load_categories_yaml().get("categories", {})
        cat_spec = cats.get(app.category, {})
        required_docs = cat_spec.get("required_documents", [])

        generated_alerts: List[Alert] = []

        # 1. Missing Documents Alert
        present_types = set(d.doc_type for d in docs)
        for req in required_docs:
            req_type = req.get("doc_type")
            req_name = req.get("name", req_type)
            if req_type not in present_types:
                alert = Alert(
                    id=f"alert-missing-{application_id}-{req_type}",
                    application_id=application_id,
                    alert_type="missing",
                    severity="critical",
                    title=f"Missing Mandatory Document: {req_name}",
                    message=f"Category '{app.category}' requires submission of '{req_name}' per {cat_spec.get('handbook_ref', 'APH §Regulations')}.",
                    rule_id=f"REQ_DOC_{req_type.upper()}",
                    created_at=datetime.now(timezone.utc)
                )
                generated_alerts.append(alert)

        # 2. Expiring / Expired Document Alert
        now = datetime.now(timezone.utc)
        threshold_dt = now + timedelta(days=expiry_warning_days)

        for c in claims:
            if "expiry" in c.field or "valid_upto" in c.field or any("EXPIRED" in f.get("reason_code", "") for f in (c.flags or [])):
                try:
                    dt = date_parser.parse(c.normalized_value or c.value)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt <= threshold_dt:
                        days_left = (dt - now).days
                        is_past = days_left < 0
                        date_str = dt.strftime("%Y-%m-%d")
                        alert_msg = f"Document field '{c.field}' expired on {date_str}." if is_past else f"Document field '{c.field}' expires in {days_left} days ({date_str})."
                        alert = Alert(
                            id=f"alert-expiring-{c.id}",
                            application_id=application_id,
                            alert_type="expiring",
                            severity="critical" if is_past else "warning",
                            title=f"{'Expired' if is_past else 'Expiring Soon'}: {c.field}",
                            message=alert_msg,
                            rule_id="ALERT_EXPIRING_TIMELINE",
                            created_at=datetime.now(timezone.utc)
                        )
                        generated_alerts.append(alert)
                except Exception:
                    pass

        # 3. Pending Source Verification Alert
        if any(c.status in [StatusEnum.SOURCE_UNAVAILABLE, StatusEnum.VERIFICATION_PENDING] for c in claims) or app.status in [StatusEnum.SOURCE_UNAVAILABLE, StatusEnum.VERIFICATION_PENDING]:
            alert = Alert(
                id=f"alert-source-{application_id}",
                application_id=application_id,
                alert_type="pending_source",
                severity="warning" if app.status == StatusEnum.SOURCE_UNAVAILABLE else "info",
                title="Statutory Source Verification Pending / Unreachable",
                message="Issuing authority gateway timed out or simulated outage active. Awaiting source ledger confirmation.",
                rule_id="ALERT_SOURCE_UNAVAILABLE",
                created_at=datetime.now(timezone.utc)
            )
            generated_alerts.append(alert)

        # 4. Anomaly / Discrepancy Alert
        discrepancy_claims = [c for c in claims if (c.flags or [])]
        if discrepancy_claims:
            is_critical = any(c.status == StatusEnum.MISMATCH_DETECTED for c in claims)
            alert = Alert(
                id=f"alert-anomaly-{application_id}",
                application_id=application_id,
                alert_type="anomaly",
                severity="critical" if is_critical else "warning",
                title="Document Tamper or Verification Anomaly Flagged",
                message=f"{len(discrepancy_claims)} claim(s) contain discrepancy flags or verification anomalies requiring scrutiny.",
                rule_id="ALERT_ANOMALY",
                created_at=datetime.now(timezone.utc)
            )
            generated_alerts.append(alert)

        # 5. Duplicate Document Reuse Ring Alert
        reg_claims = [c for c in claims if c.field in ["registered_doc_no", "state_noc_number", "ter_transaction_id"] and c.normalized_value]
        for rc in reg_claims:
            val = str(rc.normalized_value).strip().upper()
            other_claim = session.exec(
                select(Claim).where(Claim.field == rc.field, Claim.normalized_value == val, Claim.application_id != application_id)
            ).first()
            if other_claim:
                alert = Alert(
                    id=f"alert-reuse-{application_id}-{rc.id}",
                    application_id=application_id,
                    alert_type="reuse",
                    severity="critical",
                    title="Duplicate Document Reuse Collision Detected",
                    message=f"Registration identifier '{val}' is claimed across multiple college applications ({application_id} and {other_claim.application_id}).",
                    rule_id="ALERT_REUSE_RING",
                    created_at=datetime.now(timezone.utc)
                )
                generated_alerts.append(alert)
                break

        # 6. Overdue Scrutiny SLA Alert
        created_at = app.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if (now - created_at).days > 7 and app.status == StatusEnum.VERIFICATION_PENDING:
            alert = Alert(
                id=f"alert-overdue-{application_id}",
                application_id=application_id,
                alert_type="overdue",
                severity="info",
                title="Scrutiny Processing SLA Exceeded",
                message="Application has been in scrutiny queue for over 7 days without regulatory decision.",
                rule_id="ALERT_SLA_OVERDUE",
                created_at=datetime.now(timezone.utc)
            )
            generated_alerts.append(alert)

        # Persist or update alerts in DB
        for a in generated_alerts:
            existing = session.get(Alert, a.id)
            if not existing:
                session.add(a)
        session.commit()

        return generated_alerts
