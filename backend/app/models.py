import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON


class StatusEnum:
    VERIFIED = "verified"
    MISMATCH_DETECTED = "mismatch_detected"
    EXPIRED = "expired"
    VERIFICATION_PENDING = "verification_pending"
    SOURCE_UNAVAILABLE = "source_unavailable"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"

    ALL_STATUSES = [
        VERIFIED,
        MISMATCH_DETECTED,
        EXPIRED,
        VERIFICATION_PENDING,
        SOURCE_UNAVAILABLE,
        MANUAL_REVIEW_REQUIRED,
    ]


class LaneVoteEnum:
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    WEAK = "WEAK"
    NA = "NA"


class ApplicationCategoryEnum:
    EOA_RENEWAL = "EOA_RENEWAL"
    INTAKE_INCREASE = "INTAKE_INCREASE"
    NEW_COURSE = "NEW_COURSE"


class Institution(SQLModel, table=True):
    id: str = Field(primary_key=True)
    pid: str = Field(index=True, description="Permanent Institute ID, e.g. 1-1029384751")
    name: str = Field(index=True)
    address: str
    state: str
    district: str
    pin_code: str
    contact_email: str = "contact@institution.ac.in"
    deficiency_status: str = "None"
    previous_eoa_status: str = "Approved"
    approved_intake: int = 360
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Application(SQLModel, table=True):
    id: str = Field(primary_key=True)
    institution_id: str = Field(foreign_key="institution.id", index=True)
    category: str = Field(default=ApplicationCategoryEnum.EOA_RENEWAL, index=True)
    academic_year: str = Field(default="2026-2027")
    status: str = Field(default=StatusEnum.VERIFICATION_PENDING, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Dual-axis Triangulation Scores
    assurance_score: float = Field(default=0.0)
    suspicion_score: float = Field(default=0.0)
    sufficiency: int = Field(default=0)  # Count of lanes capable of speaking (0-3)

    # Officer-only Adverse Action Guardrails
    adverse_action: Optional[str] = None  # e.g. 'rejected', 'refer_for_inspection', 'mark_forged'
    adverse_reason: Optional[str] = None
    officer_id: Optional[str] = None
    decision_timestamp: Optional[datetime] = None

    # Version tracking & revision guardrail
    revision: int = Field(default=1)


class Document(SQLModel, table=True):
    id: str = Field(primary_key=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    doc_type: str = Field(index=True)  # e.g. 'affidavit', 'lease_deed', 'state_noc', 'nba_certificate', 'ter_receipt', 'lab_photo'
    original_filename: str
    stored_encrypted_path: str
    page_count: int = 1
    sha256_hash: str = Field(index=True)
    phash: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    status: str = Field(default=StatusEnum.VERIFICATION_PENDING)


class Claim(SQLModel, table=True):
    id: str = Field(primary_key=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    doc_id: str = Field(foreign_key="document.id", index=True)
    field: str = Field(index=True)
    value: str
    normalized_value: str
    page: int = 0
    bbox: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0], sa_column=Column(JSON))
    extraction_confidence: float = 1.0

    # Three Independent Evidence Lane Votes
    content_vote: str = Field(default=LaneVoteEnum.NA)
    forensic_vote: str = Field(default=LaneVoteEnum.NA)
    provenance_vote: str = Field(default=LaneVoteEnum.NA)

    status: str = Field(default=StatusEnum.VERIFICATION_PENDING)
    flags: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class MockAICTERecord(SQLModel, table=True):
    pid: str = Field(primary_key=True)
    name: str
    address: str
    state: str
    district: str
    pin_code: str
    approved_intake: int = 360
    previous_eoa_status: str = "Approved"
    deficiency_status: str = "None"
    ter_fee_required: float = 100000.0
    ter_fee_paid: float = 100000.0
    ter_transaction_id: str = "TER-2026-99120"
    ter_payment_status: str = "Verified"
    previous_eoa_date: str = "2025-05-15"


class AuditEntry(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    actor_role: str = Field(default="System")
    action: str = Field(index=True)  # e.g. 'RULE_EVALUATED', 'OFFICER_DECISION', 'CHAOS_TOGGLED'
    application_id: Optional[str] = Field(default=None, index=True)
    doc_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    prev_hash: str
    current_hash: str = Field(index=True)


class Alert(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    alert_type: str = Field(index=True)  # 'missing', 'expiring', 'pending_source', 'anomaly', 'reuse', 'overdue'
    severity: str = Field(default="warning")  # 'info', 'warning', 'critical'
    title: str
    message: str
    rule_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = Field(default=False)


class ValidationRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    run_number: int = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    trigger: str = Field(default="manual")  # "manual" | "document_replaced" | "seed"
    actor_role: str = Field(default="Officer")
    snapshot_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    snapshot_hash: str = Field(index=True)
    rules_version: str = Field(index=True)
    status_at_run: str
    findings_json: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    counts: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))  # {"open": int, "critical": int}
    revision: int = Field(default=1)

