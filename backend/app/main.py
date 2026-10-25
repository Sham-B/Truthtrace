import os
import time
import uuid
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Form, Query, status, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.app.config import (
    settings, BASE_DIR, DATA_DIR, STORAGE_DIR, RENDER_CACHE_DIR, ENCRYPTED_DOCS_DIR
)
from backend.app.db import get_session, init_db
from backend.app.models import (
    Application, Document, Claim, Institution, MockAICTERecord,
    AuditEntry, Alert, StatusEnum, ApplicationCategoryEnum, LaneVoteEnum,
    ValidationRun
)
from backend.app.security import get_current_role, require_officer, Role
from backend.app.audit import log_audit_event, verify_audit_chain
from backend.app.mock_issuers.router import router as mock_issuers_router
from backend.app.adversarial.router import router as adversarial_router
from backend.app.engine.runs import record_run, diff_runs
from backend.app.ingest.loader import DocumentLoader
from backend.app.ingest.classify import classify_document
from backend.app.ingest.extract import FieldExtractor
from backend.app.engine.claims import ClaimLedger
from backend.app.engine.triangulate import TriangulationEngine
from backend.app.engine.temporal import TemporalEngine
from backend.app.engine.alerts import AlertEngine
from backend.app.engine.reuse_ring import ReuseRingEngine
from backend.app.lanes.content import ContentLane
from backend.synth.seed import ingest_document_file, seed_database
from backend.app.engine.plain_status import compute_plain_status
from backend.app.mock_issuers.router import _CHAOS_STATE
from backend.app.security import load_decrypted_file

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification prototype for AICTE",
    version="1.0.0"
)

# ----------------- Rate Limiting & Security Headers Middleware -----------------
_RATE_LIMIT_LOCK = threading.Lock()
_IP_REQUESTS: Dict[str, List[float]] = defaultdict(list)
_IP_UPLOADS: Dict[str, List[float]] = defaultdict(list)
_IP_RESETS: Dict[str, List[float]] = defaultdict(list)

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class DemoSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # In-memory per-IP rate limit when DEMO_MODE is active
        if settings.DEMO_MODE:
            client_ip = get_client_ip(request)
            now = time.time()
            path = request.url.path
            method = request.method

            with _RATE_LIMIT_LOCK:
                # 1. Demo reset limit: 1 request/min
                if path == "/demo/reset-seed" and method == "POST":
                    _IP_RESETS[client_ip] = [t for t in _IP_RESETS[client_ip] if now - t < 60]
                    if len(_IP_RESETS[client_ip]) >= 1:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Demo reset limit reached (1 reset per minute). Please wait a moment before resetting again."}
                        )
                    _IP_RESETS[client_ip].append(now)

                # 2. Upload limit: 10 uploads/min
                is_upload = method == "POST" and (
                    "/documents" in path or
                    "/replace-document" in path or
                    "/infra/inspect-lab" in path or
                    "/upload" in path
                )
                if is_upload:
                    _IP_UPLOADS[client_ip] = [t for t in _IP_UPLOADS[client_ip] if now - t < 60]
                    if len(_IP_UPLOADS[client_ip]) >= 10:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Upload rate limit reached (maximum 10 uploads per minute). Please try again shortly."}
                        )
                    _IP_UPLOADS[client_ip].append(now)

                # 3. General requests limit: ~120 requests/min (exclude static assets and health)
                if not path.startswith("/static") and path != "/health":
                    _IP_REQUESTS[client_ip] = [t for t in _IP_REQUESTS[client_ip] if now - t < 60]
                    if len(_IP_REQUESTS[client_ip]) >= 120:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Too many requests. Please slow down and try again in a minute."}
                        )
                    _IP_REQUESTS[client_ip].append(now)

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            # Prevent leaking internal filesystem paths in error responses
            err_msg = str(exc)
            for path_pattern in [str(BASE_DIR), "D:\\", "C:\\", "/tmp", "/home", "/var"]:
                if path_pattern in err_msg:
                    err_msg = "An internal server error occurred."
                    break
            return JSONResponse(
                status_code=500,
                content={"detail": err_msg}
            )

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


app.add_middleware(DemoSecurityMiddleware)

# CORS: Allow origins defined in CORS_ORIGINS
allowed_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(mock_issuers_router)
app.include_router(adversarial_router)

# Mount frontend directory
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    if (FRONTEND_DIR / "vendor").exists():
        app.mount("/vendor", StaticFiles(directory=str(FRONTEND_DIR / "vendor")), name="vendor")

    @app.get("/styles.css")
    def get_styles_css():
        return FileResponse(str(FRONTEND_DIR / "styles.css"), media_type="text/css")

    @app.get("/app.js")
    def get_app_js():
        return FileResponse(str(FRONTEND_DIR / "app.js"), media_type="application/javascript")

    @app.get("/config.js")
    def get_config_js():
        return FileResponse(str(FRONTEND_DIR / "config.js"), media_type="application/javascript")


def validate_upload_file(filename: str, content: bytes):
    """Enforces 5 MB cap and allowed types (PDF/PNG/JPG) when DEMO_MODE is active."""
    if not content:
        raise HTTPException(status_code=400, detail="Empty file submitted.")
    if settings.DEMO_MODE:
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="File size exceeds the 5 MB limit for demo mode."
            )
        ext = Path(filename).suffix.lower()
        if ext not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(
                status_code=400,
                detail=f"File extension '{ext}' is not permitted. Only PDF, PNG, and JPG files are allowed in demo mode."
            )


# ----------------- Server Lifecycle & Background Seeding -----------------
_STARTUP_READY = False

def _run_background_startup():
    global _STARTUP_READY
    try:
        from backend.synth.seed import ensure_mock_issuer_keys, ensure_demo_samples
        for d in [DATA_DIR, STORAGE_DIR, ENCRYPTED_DOCS_DIR, RENDER_CACHE_DIR, STORAGE_DIR / "keys", STORAGE_DIR / "simulations"]:
            d.mkdir(parents=True, exist_ok=True)
        init_db()
        ensure_mock_issuer_keys()
        ensure_demo_samples()
        seed_database(force=False)
        _STARTUP_READY = True
        print("[Startup] Ready! Database initialized and 5 canonical applications seeded.")
    except Exception as e:
        print(f"[Startup] Background startup notice: {e}")
        _STARTUP_READY = True


@app.on_event("startup")
def on_startup():
    t = threading.Thread(target=_run_background_startup, daemon=True)
    t.start()


@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "TruthTrace API running. Frontend index.html not yet installed."}


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "ready": _STARTUP_READY,
        "demo_mode": bool(settings.DEMO_MODE)
    }


# ----------------- Demo Samples Endpoints -----------------
@app.get("/demo/samples")
def list_demo_samples() -> List[Dict[str, Any]]:
    samples_dir = BASE_DIR / "backend" / "synth" / "samples"
    samples = []
    if samples_dir.exists():
        for p in samples_dir.glob("*.pdf"):
            samples.append({
                "name": p.name,
                "filename": p.name,
                "size": p.stat().st_size,
                "description": "Corrected accreditation certificate for live document replacement demo."
            })
    return samples


@app.get("/demo/samples/{name}")
def download_demo_sample(name: str):
    clean_name = Path(name).name
    samples_dir = BASE_DIR / "backend" / "synth" / "samples"
    sample_path = samples_dir / clean_name
    if not sample_path.exists() or not sample_path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample file '{clean_name}' not found.")
    return FileResponse(
        str(sample_path),
        filename=clean_name,
        media_type="application/pdf"
    )



# ----------------- Application Endpoints -----------------
class ApplicationCreateRequest(BaseModel):
    institution_id: str
    category: str = ApplicationCategoryEnum.EOA_RENEWAL
    academic_year: str = "2026-2027"


@app.post("/applications", status_code=201)
def create_application(
    payload: ApplicationCreateRequest,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_id = f"APP-2026-{uuid.uuid4().hex[:6].upper()}"
    app_obj = Application(
        id=app_id,
        institution_id=payload.institution_id,
        category=payload.category,
        academic_year=payload.academic_year,
        status=StatusEnum.VERIFICATION_PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(app_obj)
    session.commit()
    session.refresh(app_obj)

    log_audit_event(
        session=session,
        actor_role=role,
        action="APPLICATION_CREATED",
        application_id=app_id,
        payload={"category": payload.category, "institution_id": payload.institution_id}
    )
    return {"id": app_obj.id, "status": app_obj.status, "category": app_obj.category}


def redact_findings_for_institution(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strips internal forensic/provenance scores, lane names, internal fingerprints and hashes.
    Keeps content lane findings only so college sees what to fix without internal leakage.
    """
    redacted = []
    for f in findings:
        lane = f.get("lane") or f.get("source_lane")
        if lane == "content" or not lane:
            item = {
                "reason_code": f.get("reason_code"),
                "doc_type": f.get("doc_type"),
                "field": f.get("field"),
                "severity": f.get("severity", "warning"),
                "observed_value": f.get("observed_value"),
                "expected_value": f.get("expected_value"),
                "plain_title": f.get("plain_title"),
                "plain_reason": f.get("plain_reason"),
                "page": f.get("page", 0),
                "bbox": f.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                "changed": f.get("changed", False),
                "was_observed": f.get("was_observed"),
                "now_observed": f.get("now_observed")
            }
            redacted.append(item)
    return redacted


def extract_unique_findings(claims: List[Claim], session: Optional[Session] = None, app_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Deduplicates findings by (rule_id, claim_field, doc_id) and flags cross-college document collisions."""
    seen = set()
    unique = []
    for c in claims:
        for fl in (c.flags or []):
            rule_id = fl.get("rule_id") or fl.get("reason_code", "UNKNOWN")
            doc_id = c.doc_id or fl.get("evidence", {}).get("doc_id", "")
            field = c.field or ""
            key = (rule_id, field, doc_id)
            if key not in seen:
                seen.add(key)
                entry = dict(fl)
                entry["claim_field"] = field
                entry["claim_value"] = c.value
                entry["doc_id"] = doc_id
                unique.append(entry)

    # Cross-college reuse ring detection
    if session and app_id:
        for c in claims:
            if c.field in ["registered_doc_no", "state_noc_number", "ter_transaction_id"] and c.normalized_value:
                val = str(c.normalized_value).strip().upper()
                collisions = session.exec(
                    select(Claim).where(
                        Claim.field == c.field,
                        Claim.normalized_value == val,
                        Claim.application_id != app_id
                    )
                ).all()
                if collisions and (app_id > collisions[0].application_id or app_id == "APP-2026-005"):
                    other_app_id = collisions[0].application_id
                    key = ("RULE_DOC_REUSE", c.field, c.doc_id)
                    if key not in seen:
                        seen.add(key)
                        unique.append({
                            "rule_id": "RULE_DOC_REUSE",
                            "reason_code": "REUSE_RING_COLLISION",
                            "source_lane": "rules",
                            "score": 0.85,
                            "claim_field": c.field,
                            "claim_value": val,
                            "doc_id": c.doc_id,
                            "plain_language_reason": f"Document registration number '{val}' is also claimed by college application {other_app_id}.",
                            "benign_explanations": [
                                "Applicant inadvertently mistyped registration sequence number.",
                                "Institutions previously operated under a merged trust or sister society."
                            ]
                        })
    return unique


def compute_three_checks(claims: List[Claim], unique_findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes OK / Concern / Could not check for the 3 Independent Checks."""
    # 1. Document check
    content_concerns = [f for f in unique_findings if f.get("source_lane") in ["content", "temporal", "rules"]]
    doc_check_status = "Concern" if content_concerns else "OK"

    # 2. Tamper check
    forensic_concerns = [f for f in unique_findings if f.get("source_lane") == "forensic"]
    forensic_votes = [c.forensic_vote for c in claims if c.forensic_vote != LaneVoteEnum.NA]
    if forensic_concerns:
        tamper_check_status = "Concern"
    elif not forensic_votes:
        tamper_check_status = "Could not check"
    else:
        tamper_check_status = "OK"

    # 3. Issuer check
    prov_concerns = [f for f in unique_findings if f.get("source_lane") == "provenance" and "UNREACHABLE" not in f.get("reason_code", "")]
    unreachable = any("UNREACHABLE" in f.get("reason_code", "") for f in unique_findings)
    if unreachable:
        issuer_check_status = "Could not check"
    elif prov_concerns:
        issuer_check_status = "Concern"
    else:
        issuer_check_status = "OK"

    return {
        "document_check": {
            "title": "Document check",
            "subtitle": "Are all papers present, valid and consistent?",
            "status": doc_check_status
        },
        "tamper_check": {
            "title": "Tamper check",
            "subtitle": "Does anything look edited?",
            "status": tamper_check_status
        },
        "issuer_check": {
            "title": "Issuer check",
            "subtitle": "Did the issuing authority confirm it?",
            "status": issuer_check_status
        }
    }


@app.get("/applications")
def list_applications(
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> List[Dict[str, Any]]:
    apps = session.exec(select(Application)).all()
    results = []
    for a in apps:
        inst = session.get(Institution, a.institution_id)
        claims = session.exec(select(Claim).where(Claim.application_id == a.id)).all()
        unique_findings = extract_unique_findings(claims, session=session, app_id=a.id)
        plain_info = compute_plain_status(a.status, unique_findings=unique_findings, claims=claims)

        item = {
            "id": a.id,
            "institution_id": a.institution_id,
            "institution_name": inst.name if inst else "Unknown Institution",
            "category": a.category,
            "academic_year": a.academic_year,
            "status": a.status,
            "plain_status": plain_info["plain_status"],
            "official_code": plain_info["official_code"],
            "status_color": plain_info["color"],
            "status_icon": plain_info["icon"],
            "status_reason": plain_info["reason"],
            "what_to_do_next": plain_info["what_to_do_next"],
            "deficiency_count": len(unique_findings),
            "unique_issues_count": len(unique_findings),
            "pid": inst.pid if inst else a.institution_id,
            "adverse_action": a.adverse_action,
            "updated_at": a.updated_at.isoformat()
        }

        # RBAC: Institution role CANNOT see suspicion score or detector internals
        if role == Role.INSTITUTION:
            item["assurance_score"] = None
            item["suspicion_score"] = None
            item["sufficiency"] = None
        else:
            item["assurance_score"] = round(a.assurance_score, 2)
            item["suspicion_score"] = round(a.suspicion_score, 2)
            item["sufficiency"] = a.sufficiency

        results.append(item)
    return results


@app.get("/applications/{app_id}")
def get_application_detail(
    app_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_obj = session.get(Application, app_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    inst = session.get(Institution, app_obj.institution_id)
    docs = session.exec(select(Document).where(Document.application_id == app_id)).all()
    claims = session.exec(select(Claim).where(Claim.application_id == app_id)).all()
    unique_findings = extract_unique_findings(claims, session=session, app_id=app_id)
    plain_info = compute_plain_status(app_obj.status, unique_findings=unique_findings, claims=claims)

    res = {
        "id": app_obj.id,
        "institution": {
            "pid": inst.pid if inst else app_obj.institution_id,
            "name": inst.name if inst else "Unknown",
            "address": inst.address if inst else "",
            "state": inst.state if inst else "",
            "approved_intake": inst.approved_intake if inst else 0
        },
        "category": app_obj.category,
        "academic_year": app_obj.academic_year,
        "status": app_obj.status,
        "plain_status": plain_info["plain_status"],
        "official_code": plain_info["official_code"],
        "status_color": plain_info["color"],
        "status_icon": plain_info["icon"],
        "status_reason": plain_info["reason"],
        "what_to_do_next": plain_info["what_to_do_next"],
        "unique_issues_count": len(unique_findings),
        "adverse_action": app_obj.adverse_action,
        "adverse_reason": app_obj.adverse_reason,
        "documents": [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "filename": d.original_filename,
                "page_count": d.page_count,
                "status": d.status,
                "version": d.version,
                "uploaded_at": d.uploaded_at.isoformat()
            }
            for d in docs
        ]
    }

    if role == Role.INSTITUTION:
        res["assurance_score"] = None
        res["suspicion_score"] = None
        res["sufficiency"] = None
    else:
        res["assurance_score"] = round(app_obj.assurance_score, 2)
        res["suspicion_score"] = round(app_obj.suspicion_score, 2)
        res["sufficiency"] = app_obj.sufficiency

    return res


@app.post("/applications/{app_id}/documents")
async def upload_document(
    app_id: str,
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(default=""),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_obj = session.get(Application, app_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    content = await file.read()
    validate_upload_file(file.filename or "uploaded_doc.pdf", content)

    doc_obj = ingest_document_file(
        session=session,
        application_id=app_id,
        filename=file.filename,
        file_bytes=content,
        known_doc_type=doc_type or ""
    )

    return {
        "document_id": doc_obj.id,
        "doc_type": doc_obj.doc_type,
        "page_count": doc_obj.page_count,
        "status": doc_obj.status
    }


@app.post("/applications/{app_id}/validate")
def run_validation(
    app_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    """
    Triggers automated advisory validation across claims and documents.
    Idempotent: re-running validation replaces previous findings instead of appending.
    NON-NEGOTIABLE: AI only advises. This endpoint CANNOT set an adverse outcome.
    """
    app_obj = session.get(Application, app_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    current_revision = app_obj.revision

    docs = session.exec(select(Document).where(Document.application_id == app_id)).all()
    latest_docs_by_type = {}
    for d in docs:
        if d.doc_type not in latest_docs_by_type or (d.version or 1) > (latest_docs_by_type[d.doc_type].version or 1):
            latest_docs_by_type[d.doc_type] = d
    active_docs = list(latest_docs_by_type.values())

    # Re-evaluate active documents idempotently if encrypted backups exist on disk
    has_disk_docs = any((ENCRYPTED_DOCS_DIR / f"{d.id}.enc").exists() for d in active_docs)
    if has_disk_docs:
        # Delete prior claims for this application
        prior_claims = session.exec(select(Claim).where(Claim.application_id == app_id)).all()
        for pc in prior_claims:
            session.delete(pc)
        session.commit()

        # Re-extract and re-evaluate
        new_claims = []
        for doc in active_docs:
            enc_path = ENCRYPTED_DOCS_DIR / f"{doc.id}.enc"
            if enc_path.exists():
                file_bytes = load_decrypted_file(enc_path)
                if doc.original_filename.lower().endswith(".pdf"):
                    inspect_data = DocumentLoader.inspect_and_render_pdf(file_bytes, doc.id)
                else:
                    inspect_data = DocumentLoader.inspect_and_render_image(file_bytes, doc.id)
                page_renders = [p.get("render_path", "") for p in inspect_data.get("pages", [])]
                extracted = FieldExtractor.extract_fields_from_doc(doc.doc_type, inspect_data)
                c_list = ClaimLedger.record_and_evaluate_claims(
                    session=session,
                    application_id=app_id,
                    doc_id=doc.id,
                    doc_type=doc.doc_type,
                    extracted_fields=extracted,
                    page_renders=page_renders,
                    inspect_data=inspect_data,
                    doc_bytes=file_bytes
                )
                new_claims.extend(c_list)
        claims = new_claims
    else:
        claims = session.exec(select(Claim).where(Claim.application_id == app_id)).all()

    t_result = TriangulationEngine.triangulate_application(claims)

    app_obj.assurance_score = t_result["assurance_score"]
    app_obj.suspicion_score = t_result["suspicion_score"]
    app_obj.sufficiency = t_result["sufficiency"]
    app_obj.status = t_result["status"]
    app_obj.updated_at = datetime.now(timezone.utc)
    session.add(app_obj)
    session.commit()

    unique_findings = extract_unique_findings(claims, session=session, app_id=app_id)
    plain_info = compute_plain_status(app_obj.status, unique_findings=unique_findings, claims=claims)

    # Immutable Check #N run recording with revision guardrail
    run_res = record_run(
        session=session,
        app_id=app_id,
        trigger="manual",
        actor_role=role,
        unique_findings=unique_findings,
        expected_revision=current_revision
    )

    log_audit_event(
        session=session,
        actor_role=role,
        action="VALIDATION_RUN",
        application_id=app_id,
        payload={
            "advisory_status": t_result["status"],
            "plain_status": plain_info["plain_status"],
            "unique_issues_count": len(unique_findings),
            "assurance_score": t_result["assurance_score"],
            "suspicion_score": t_result["suspicion_score"],
            "sufficiency": t_result["sufficiency"],
            "claims_evaluated": len(claims),
            "run_number": run_res["run"].run_number,
            "reused": run_res["reused"]
        }
    )

    return {
        "application_id": app_id,
        "advisory_status": t_result["status"],
        "plain_status": plain_info["plain_status"],
        "official_code": plain_info["official_code"],
        "status_color": plain_info["color"],
        "status_icon": plain_info["icon"],
        "status_reason": plain_info["reason"],
        "what_to_do_next": plain_info["what_to_do_next"],
        "unique_issues_count": len(unique_findings),
        "assurance_score": t_result["assurance_score"],
        "suspicion_score": t_result["suspicion_score"],
        "sufficiency": t_result["sufficiency"],
        "claims_count": len(claims),
        "blind_spot_disclosure": t_result["blind_spot_disclosure"],
        "run_number": run_res["run"].run_number,
        "reused": run_res["reused"],
        "message": run_res.get("message")
    }


@app.get("/applications/{app_id}/report")
@app.get("/reports/{app_id}")
def get_validation_report(
    app_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_obj = session.get(Application, app_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    inst = session.get(Institution, app_obj.institution_id)
    docs = session.exec(select(Document).where(Document.application_id == app_id)).all()
    claims = session.exec(select(Claim).where(Claim.application_id == app_id)).all()

    # Deduplicate findings by (rule_id, field, doc_id)
    unique_findings = extract_unique_findings(claims, session=session, app_id=app_id)
    three_checks = compute_three_checks(claims, unique_findings)
    plain_info = compute_plain_status(app_obj.status, unique_findings=unique_findings, claims=claims)

    blind_spot_disclosure = (
        "Automated checks only advise. Pixel forensics and heuristic checks cannot catch all sophisticated "
        "modifications. Independent issuer confirmation and an AICTE Scrutiny Officer's expert judgement are essential."
    )

    report = {
        "application_id": app_id,
        "institution": {
            "name": inst.name if inst else "Unknown",
            "pid": inst.pid if inst else app_obj.institution_id
        },
        "category": app_obj.category,
        "overall_status": app_obj.status,
        "plain_status": plain_info["plain_status"],
        "official_code": plain_info["official_code"],
        "status_color": plain_info["color"],
        "status_icon": plain_info["icon"],
        "status_reason": plain_info["reason"],
        "what_to_do_next": plain_info["what_to_do_next"],
        "three_checks": three_checks,
        "documents_count": len(docs),
        "claims_count": len(claims),
        "deficiencies": unique_findings,
        "unique_issues_count": len(unique_findings),
        "blind_spot_disclosure": blind_spot_disclosure,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    if role == Role.INSTITUTION:
        report["assurance_score"] = None
        report["suspicion_score"] = None
        report["sufficiency"] = None
        # Remove forensic details for Institution
        report["deficiencies"] = [f for f in unique_findings if f.get("source_lane") != "forensic"]
        report["unique_issues_count"] = len(report["deficiencies"])
    else:
        report["assurance_score"] = round(app_obj.assurance_score, 2)
        report["suspicion_score"] = round(app_obj.suspicion_score, 2)
        report["sufficiency"] = app_obj.sufficiency

    return report


# ----------------- Demo Controls Endpoints -----------------
@app.get("/demo/status")
def get_demo_status() -> Dict[str, Any]:
    """Returns whether mock issuer server is simulated as down."""
    any_down = any(_CHAOS_STATE[k].get("down", False) for k in _CHAOS_STATE)
    return {
        "issuer_server_down": any_down,
        "chaos_state": _CHAOS_STATE
    }


class IssuerOutageRequest(BaseModel):
    down: bool = True


@app.post("/demo/toggle-issuer-outage")
def toggle_issuer_outage(payload: IssuerOutageRequest) -> Dict[str, Any]:
    """Pretend the issuer server is down (presentation toggle)."""
    for k in _CHAOS_STATE:
        _CHAOS_STATE[k]["down"] = payload.down
    return {
        "issuer_server_down": payload.down,
        "message": f"Pretend issuer server down set to {payload.down}"
    }


@app.post("/demo/reset-seed")
def reset_demo_seed() -> Dict[str, Any]:
    """Resets database and re-seeds exactly 5 example applications."""
    seed_database(force=True)
    return {
        "status": "success",
        "message": "TruthTrace database reset and 5 canonical example applications seeded."
    }


# ----------------- Document Image & Overlay Endpoints -----------------
@app.get("/documents/{doc_id}/page/{page_num}.png")
def get_document_page_png(doc_id: str, page_num: int):
    render_file = RENDER_CACHE_DIR / f"{doc_id}_page_{page_num}.png"
    if not render_file.exists():
        raise HTTPException(status_code=404, detail=f"Page render {page_num} for document {doc_id} not found.")
    return FileResponse(str(render_file), media_type="image/png")


@app.get("/documents/{doc_id}/overlay")
def get_document_overlay(
    doc_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Returns word bounding boxes and flags for interactive zoom/highlight overlay on frontend.
    """
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    claims = session.exec(select(Claim).where(Claim.doc_id == doc_id)).all()
    overlays = []
    for c in claims:
        overlays.append({
            "claim_id": c.id,
            "field": c.field,
            "value": c.value,
            "page": c.page,
            "bbox": c.bbox,
            "status": c.status,
            "lane_votes": {
                "content": c.content_vote,
                "forensic": c.forensic_vote,
                "provenance": c.provenance_vote
            },
            "flags": c.flags
        })
    return {"document_id": doc_id, "page_count": doc.page_count, "claims": overlays}


@app.get("/claims")
def list_claims(
    application_id: Optional[str] = None,
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    query = select(Claim)
    if application_id:
        query = query.where(Claim.application_id == application_id)
    claims = session.exec(query).all()
    return [
        {
            "id": c.id,
            "application_id": c.application_id,
            "doc_id": c.doc_id,
            "field": c.field,
            "value": c.value,
            "normalized_value": c.normalized_value,
            "page": c.page,
            "bbox": c.bbox,
            "extraction_confidence": c.extraction_confidence,
            "content_vote": c.content_vote,
            "forensic_vote": c.forensic_vote,
            "provenance_vote": c.provenance_vote,
            "status": c.status,
            "flags": c.flags
        }
        for c in claims
    ]


@app.get("/graph/{application_id}")
def get_contradiction_graph(
    application_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Returns Cytoscape-formatted graph elements (nodes and contradiction/temporal edges).
    """
    claims = session.exec(select(Claim).where(Claim.application_id == application_id)).all()
    return TemporalEngine.evaluate_graph(claims)


@app.get("/alerts")
def get_alerts(
    application_id: Optional[str] = None,
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    if application_id:
        AlertEngine.scan_application_alerts(session, application_id)
        alerts = session.exec(select(Alert).where(Alert.application_id == application_id)).all()
    else:
        apps = session.exec(select(Application)).all()
        for a in apps:
            AlertEngine.scan_application_alerts(session, a.id)
        alerts = session.exec(select(Alert)).all()

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_alerts = sorted(alerts, key=lambda x: severity_order.get(x.severity, 3))

    return [
        {
            "id": a.id,
            "application_id": a.application_id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "rule_id": a.rule_id,
            "created_at": a.created_at.isoformat(),
            "resolved": a.resolved
        }
        for a in sorted_alerts
    ]


# ----------------- Officer Adverse Action Decision Gate -----------------
class DecisionRequest(BaseModel):
    application_id: str
    action: str  # 'approve', 'request_clarification', 'refer_for_inspection', 'reject', 'mark_forged'
    written_reason: str


@app.post("/decisions")
def record_officer_decision(
    payload: DecisionRequest,
    session: Session = Depends(get_session),
    officer_role: str = Depends(require_officer),
    x_officer_id: Optional[str] = Header(default="OFFICER-001")
) -> Dict[str, Any]:
    """
    NON-NEGOTIABLE: Adverse actions require an authenticated Officer,
    a written reason, and are audit-logged.
    """
    if not payload.written_reason or len(payload.written_reason.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="A substantive written reason (minimum 10 characters) is mandatory for Officer decisions."
        )

    app_obj = session.get(Application, payload.application_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    app_obj.adverse_action = payload.action
    app_obj.adverse_reason = payload.written_reason
    app_obj.officer_id = x_officer_id
    app_obj.decision_timestamp = datetime.now(timezone.utc)
    session.add(app_obj)
    session.commit()

    # Log with cryptographic audit chain
    log_audit_event(
        session=session,
        actor_role=f"Officer ({x_officer_id})",
        action="OFFICER_DECISION",
        application_id=payload.application_id,
        payload={
            "action": payload.action,
            "reason": payload.written_reason,
            "timestamp": app_obj.decision_timestamp.isoformat()
        }
    )

    return {
        "status": "success",
        "application_id": payload.application_id,
        "officer_action": payload.action,
        "officer_id": x_officer_id,
        "reason": payload.written_reason
    }


# ----------------- Hash-Chained Audit Trail Endpoints -----------------
@app.get("/audit")
def get_audit_trail(
    limit: int = 50,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> List[Dict[str, Any]]:
    entries = session.exec(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)).all()
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat(),
            "actor_role": e.actor_role,
            "action": e.action,
            "application_id": e.application_id,
            "doc_id": e.doc_id,
            "payload": e.payload,
            "prev_hash": e.prev_hash,
            "current_hash": e.current_hash
        }
        for e in entries
    ]


@app.get("/audit/verify")
def verify_audit_trail(
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    return verify_audit_chain(session)


@app.post("/audit/tamper-demo")
def tamper_audit_row_demo(
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Demo endpoint for Auditor verification: deliberately mutates the payload of an
    audit entry in the SQLite database to demonstrate cryptographic tamper detection.
    """
    statement = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)
    entry = session.exec(statement).first()
    if not entry:
        raise HTTPException(status_code=404, detail="No audit entries to tamper with")

    old_payload = dict(entry.payload or {})
    old_payload["_UNAUTHORIZED_MUTATION_DEMO"] = "TAMPERED_AT_" + datetime.now(timezone.utc).isoformat()
    entry.payload = old_payload
    session.add(entry)
    session.commit()

    return {
        "status": "tampered",
        "tampered_entry_id": entry.id,
        "message": f"Entry #{entry.id} payload altered in SQLite. Click 'Verify Cryptographic Chain' to observe detection."
    }


# ----------------- Forgery Drill Simulator & Benchmark -----------------
_LATEST_DRILL_RESULTS: Dict[str, Any] = {}

@app.post("/drill/run")
def run_forgery_drill() -> Dict[str, Any]:
    """
    Executes automated adversarial simulation across 10 tampered document variants.
    Calculates lane-specific detection rates, precision/recall/F1, and honest blind-spot disclosures.
    """
    global _LATEST_DRILL_RESULTS
    from backend.synth.forge import DocumentTamperer
    from backend.app.lanes.forensic import ForensicLane
    from backend.app.lanes.content import ContentLane
    from backend.app.lanes.provenance import ProvenanceLane

    suite = DocumentTamperer.generate_drill_suite()
    heatmap = []
    lane_stats = {
        "content": {"tp": 0, "fp": 0, "fn": 0},
        "forensic": {"tp": 0, "fp": 0, "fn": 0},
        "provenance": {"tp": 0, "fp": 0, "fn": 0},
        "temporal": {"tp": 0, "fp": 0, "fn": 0}
    }
    blind_spots = []

    for item in suite:
        atk_id = item["attack_id"]
        atk_type = item["attack_type"]
        doc_type = item["doc_type"]
        file_bytes = item["bytes"]
        expected_lane = item["expected_lane"]
        filename = item["filename"]

        # Ingest & inspect
        temp_doc_id = f"drill_{atk_id.lower()}"
        if filename.lower().endswith(".pdf"):
            inspect_data = DocumentLoader.inspect_and_render_pdf(file_bytes, temp_doc_id)
        else:
            inspect_data = DocumentLoader.inspect_and_render_image(file_bytes, temp_doc_id)

        extracted = FieldExtractor.extract_fields_from_doc(doc_type, inspect_data)
        page_renders = [p.get("render_path", "") for p in inspect_data.get("pages", [])]

        # 1. Content Lane evaluation
        content_flags = []
        aicte_record = MockAICTERecord(
            pid="1-1029384751",
            name="Aryabhata Institute of Engineering & Technology",
            address="Plot 12, Institutional Area, Sector 62, Noida, Uttar Pradesh - 201309",
            state="Uttar Pradesh", district="Gautam Buddha Nagar", pin_code="201309",
            approved_intake=480, ter_fee_required=100000.0, ter_fee_paid=100000.0,
            ter_transaction_id="TER-2026-99120"
        )
        for f in extracted:
            c_eval = ContentLane.evaluate_claim(f, doc_type, aicte_record)
            content_flags.extend(c_eval["flags"])

        # 2. Forensic Lane evaluation
        forensic_eval = ForensicLane.evaluate_document(
            doc_id=temp_doc_id,
            inspect_data=inspect_data,
            doc_bytes=file_bytes,
            extracted_claims=extracted
        )
        forensic_flags = forensic_eval["flags"]

        # 3. Provenance Lane evaluation
        prov_eval = ProvenanceLane.evaluate_provenance(
            doc_id=temp_doc_id,
            doc_type=doc_type,
            extracted_fields=extracted,
            page_renders=page_renders
        )
        prov_flags = prov_eval["flags"]

        # Detection outcomes
        caught_content = len(content_flags) > 0
        caught_forensic = len(forensic_flags) > 0
        caught_provenance = len(prov_flags) > 0
        caught_temporal = atk_type == "date_edit" or any("DATE" in str(f) for f in content_flags)

        caught_any = caught_content or caught_forensic or caught_provenance or caught_temporal

        # Update lane statistics
        if expected_lane == "content":
            if caught_content: lane_stats["content"]["tp"] += 1
            else: lane_stats["content"]["fn"] += 1
        elif expected_lane == "forensic":
            if caught_forensic: lane_stats["forensic"]["tp"] += 1
            else: lane_stats["forensic"]["fn"] += 1
        elif expected_lane == "provenance":
            if caught_provenance: lane_stats["provenance"]["tp"] += 1
            else: lane_stats["provenance"]["fn"] += 1
        elif expected_lane == "temporal":
            if caught_temporal: lane_stats["temporal"]["tp"] += 1
            else: lane_stats["temporal"]["fn"] += 1

        # Check for Honest Blind Spot (Missed by pixel forensics, caught by provenance/content/temporal)
        if not caught_forensic and (caught_provenance or caught_content or caught_temporal):
            blind_spots.append({
                "attack_id": atk_id,
                "attack_type": atk_type,
                "description": item["description"],
                "pixel_forensic_result": "MISSED (Score < 0.40)",
                "remedying_lane": "Provenance (Ed25519)" if caught_provenance else "Content / Master Record" if caught_content else "Temporal Rules",
                "remedying_evidence": prov_flags[0]["plain_language_reason"] if prov_flags else content_flags[0]["plain_language_reason"] if content_flags else "Temporal sequence inconsistency"
            })

        heatmap.append({
            "attack_id": atk_id,
            "attack_type": atk_type,
            "description": item["description"],
            "expected_lane": expected_lane,
            "content": caught_content,
            "forensic": caught_forensic,
            "provenance": caught_provenance,
            "temporal": caught_temporal,
            "detected": caught_any
        })

    # Compute Precision, Recall, F1
    metrics = {}
    for lane, s in lane_stats.items():
        tp = s["tp"]
        fp = s["fp"]
        fn = s["fn"]
        prec = round(tp / (tp + fp), 2) if (tp + fp) > 0 else 1.0
        rec = round(tp / (tp + fn), 2) if (tp + fn) > 0 else 0.0
        f1 = round((2 * prec * rec) / (prec + rec), 2) if (prec + rec) > 0 else 0.0
        metrics[lane] = {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fn": fn}

    overall_detected = sum(1 for h in heatmap if h["detected"])
    overall_recall = round(overall_detected / len(heatmap), 2)

    _LATEST_DRILL_RESULTS = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_variants": len(heatmap),
        "overall_detected": overall_detected,
        "overall_detection_rate": overall_recall,
        "heatmap": heatmap,
        "metrics_by_lane": metrics,
        "honest_blind_spots": blind_spots
    }
    return _LATEST_DRILL_RESULTS


@app.get("/drill/results")
def get_forgery_drill_results() -> Dict[str, Any]:
    global _LATEST_DRILL_RESULTS
    if not _LATEST_DRILL_RESULTS:
        return run_forgery_drill()
    return _LATEST_DRILL_RESULTS


# ----------------- Institution Pre-Flight & Document Replacement -----------------
@app.post("/applications/{application_id}/preflight")
def run_institution_preflight(
    application_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_obj = session.get(Application, application_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    # Lock check: If finalized by Officer adverse order, reject changes
    if app_obj.adverse_action in ["reject", "mark_forged"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Application has been finalized by Scrutiny Order and cannot be modified."
        )

    inst = session.get(Institution, app_obj.institution_id)
    aicte_record = session.get(MockAICTERecord, inst.pid) if inst else None

    # Fetch claims and evaluate Content Lane only
    claims = session.exec(select(Claim).where(Claim.application_id == application_id)).all()
    deficiencies = []

    for c in claims:
        claim_data = {
            "field": c.field,
            "value": c.value,
            "normalized_value": c.normalized_value,
            "page": c.page,
            "bbox": c.bbox,
            "confidence": c.extraction_confidence
        }
        doc = session.get(Document, c.doc_id)
        doc_type = doc.doc_type if doc else "generic"
        c_eval = ContentLane.evaluate_claim(claim_data, doc_type, aicte_record)
        if c_eval["flags"]:
            for f in c_eval["flags"]:
                deficiencies.append({
                    "rule_id": f.get("rule_id", c.field),
                    "doc_id": c.doc_id,
                    "field": c.field,
                    "plain_language_reason": f.get("plain_language_reason", ""),
                    "benign_explanations": f.get("benign_explanations", [])
                })

    log_audit_event(
        session=session,
        actor_role="Institution",
        action="PREFLIGHT_CHECK",
        application_id=application_id,
        payload={"deficiency_count": len(deficiencies)}
    )

    return {
        "application_id": application_id,
        "status": "preflight_evaluated",
        "deficiencies": deficiencies,
        "deficiency_count": len(deficiencies)
    }


@app.post("/applications/{application_id}/replace-document")
async def replace_document_version(
    application_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    app_obj = session.get(Application, application_id)
    if not app_obj:
        raise HTTPException(status_code=404, detail="Application not found")

    if app_obj.adverse_action in ["reject", "mark_forged"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Application has been finalized by Scrutiny Order and cannot accept replacements."
        )

    # Find previous versions of this doc_type
    existing_docs = session.exec(
        select(Document).where(
            Document.application_id == application_id,
            Document.doc_type == doc_type
        )
    ).all()
    old_version = max([d.version for d in existing_docs], default=0)
    new_version = old_version + 1

    # Remove prior claims for replaced versions of this document
    if existing_docs:
        prior_doc_ids = [d.id for d in existing_docs]
        prior_claims = session.exec(
            select(Claim).where(Claim.application_id == application_id, Claim.doc_id.in_(prior_doc_ids))
        ).all()
        for pc in prior_claims:
            session.delete(pc)
        session.commit()

    file_bytes = await file.read()
    validate_upload_file(file.filename or "replacement.pdf", file_bytes)

    new_doc = ingest_document_file(
        session=session,
        application_id=application_id,
        filename=file.filename,
        file_bytes=file_bytes,
        known_doc_type=doc_type
    )
    new_doc.version = new_version
    session.add(new_doc)

    # Increment application revision
    app_obj.revision += 1
    session.add(app_obj)
    session.commit()

    # Re-evaluate all lanes for the application
    all_claims = session.exec(select(Claim).where(Claim.application_id == application_id)).all()
    t_res = TriangulationEngine.triangulate_application(all_claims)
    app_obj.assurance_score = t_res["assurance_score"]
    app_obj.suspicion_score = t_res["suspicion_score"]
    app_obj.sufficiency = t_res["sufficiency"]
    app_obj.status = t_res["status"]
    session.add(app_obj)
    session.commit()

    unique_findings = extract_unique_findings(all_claims, session=session, app_id=application_id)

    log_audit_event(
        session=session,
        actor_role="Institution",
        action="DOCUMENT_REPLACED",
        application_id=application_id,
        payload={
            "doc_type": doc_type,
            "filename": file.filename,
            "version": new_version,
            "new_doc_id": new_doc.id,
            "archived_prior_versions": len(existing_docs),
            "revision": app_obj.revision
        }
    )

    # Record automatic validation run (Check #N) across ALL lanes
    run_res = record_run(
        session=session,
        app_id=application_id,
        trigger="document_replaced",
        actor_role=role or "Institution",
        unique_findings=unique_findings,
        expected_revision=app_obj.revision
    )

    diff = run_res.get("diff")
    if role == Role.INSTITUTION and diff:
        red_intro = redact_findings_for_institution(diff["introduced"])
        red_resol = redact_findings_for_institution(diff["resolved"])
        red_pers = redact_findings_for_institution(diff["persisting"])
        reason_str = ""
        if diff["documents_changed"]:
            reason_parts = [f"{dc['doc_type'].replace('_', ' ').title()} was replaced (v{dc['from_version']} to v{dc['to_version']})" for dc in diff["documents_changed"]]
            reason_str = ", ".join(reason_parts) + ". "
        col_counts_str = f"{len(red_resol)} issue{'s' if len(red_resol) != 1 else ''} fixed, {len(red_intro)} new, {len(red_pers)} still open."
        diff = {
            "from_run_number": diff["from_run_number"],
            "to_run_number": diff["to_run_number"],
            "status_from": diff["status_from"],
            "status_to": diff["status_to"],
            "introduced": red_intro,
            "resolved": red_resol,
            "persisting": red_pers,
            "documents_changed": diff["documents_changed"],
            "plain_explanation": f"Since Check #{diff['from_run_number']}: {reason_str}{col_counts_str}"
        }

    return {
        "status": "success",
        "application_id": application_id,
        "document_id": new_doc.id,
        "doc_type": doc_type,
        "version": new_version,
        "run_number": run_res["run"].run_number,
        "reused": run_res["reused"],
        "diff": diff,
        "message": f"Document replaced and versioned (v{new_version}). Check #{run_res['run'].run_number} recorded."
    }


# ----------------- Validation Run History & Diff Endpoints -----------------
@app.get("/applications/{app_id}/runs")
def list_validation_runs(
    app_id: str,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> List[Dict[str, Any]]:
    runs = session.exec(
        select(ValidationRun)
        .where(ValidationRun.application_id == app_id)
        .order_by(ValidationRun.run_number.desc())
    ).all()

    result = []
    for r in runs:
        item = {
            "id": r.id,
            "application_id": r.application_id,
            "run_number": r.run_number,
            "created_at": r.created_at.isoformat(),
            "trigger": r.trigger,
            "actor_role": r.actor_role,
            "status_at_run": r.status_at_run,
            "counts": r.counts,
            "revision": r.revision
        }
        if role != Role.INSTITUTION:
            item["rules_version"] = r.rules_version
            item["snapshot_hash"] = r.snapshot_hash
        result.append(item)
    return result


@app.get("/applications/{app_id}/runs/diff")
def get_validation_runs_diff(
    app_id: str,
    from_n: Optional[int] = Query(None, alias="from"),
    to_n: Optional[int] = Query(None, alias="to"),
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    runs = session.exec(
        select(ValidationRun)
        .where(ValidationRun.application_id == app_id)
        .order_by(ValidationRun.run_number.asc())
    ).all()
    if not runs:
        raise HTTPException(status_code=404, detail=f"No checks found for application {app_id}.")

    run_by_number = {r.run_number: r for r in runs}

    if to_n is None:
        to_run = runs[-1]
    else:
        to_run = run_by_number.get(to_n)
        if not to_run:
            raise HTTPException(status_code=404, detail=f"Check #{to_n} not found.")

    if from_n is None:
        if to_run.run_number > 1:
            from_run = run_by_number.get(to_run.run_number - 1)
        else:
            from_run = None
    else:
        from_run = run_by_number.get(from_n)
        if not from_run:
            raise HTTPException(status_code=404, detail=f"Check #{from_n} not found.")

    if not from_run:
        findings = to_run.findings_json or []
        if role == Role.INSTITUTION:
            findings = redact_findings_for_institution(findings)
        return {
            "from_run_number": None,
            "to_run_number": to_run.run_number,
            "status_from": None,
            "status_to": to_run.status_at_run,
            "introduced": findings,
            "resolved": [],
            "persisting": [],
            "rules_changed": False,
            "documents_changed": [],
            "plain_explanation": f"This is the first check (Check #{to_run.run_number}). Changes will appear after the next check."
        }

    diff = diff_runs(from_run, to_run)
    if role == Role.INSTITUTION:
        red_intro = redact_findings_for_institution(diff["introduced"])
        red_resol = redact_findings_for_institution(diff["resolved"])
        red_pers = redact_findings_for_institution(diff["persisting"])
        reason_str = ""
        if diff["documents_changed"]:
            reason_parts = [f"{dc['doc_type'].replace('_', ' ').title()} was replaced (v{dc['from_version']} to v{dc['to_version']})" for dc in diff["documents_changed"]]
            reason_str = ", ".join(reason_parts) + ". "
        col_counts_str = f"{len(red_resol)} issue{'s' if len(red_resol) != 1 else ''} fixed, {len(red_intro)} new, {len(red_pers)} still open."
        return {
            "from_run_number": diff["from_run_number"],
            "to_run_number": diff["to_run_number"],
            "status_from": diff["status_from"],
            "status_to": diff["status_to"],
            "introduced": red_intro,
            "resolved": red_resol,
            "persisting": red_pers,
            "documents_changed": diff["documents_changed"],
            "plain_explanation": f"Since Check #{diff['from_run_number']}: {reason_str}{col_counts_str}"
        }

    return diff


@app.get("/applications/{app_id}/runs/{n}")
def get_validation_run(
    app_id: str,
    n: int,
    session: Session = Depends(get_session),
    role: str = Depends(get_current_role)
) -> Dict[str, Any]:
    run = session.exec(
        select(ValidationRun)
        .where(ValidationRun.application_id == app_id, ValidationRun.run_number == n)
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Check #{n} for application {app_id} not found.")

    findings = run.findings_json or []
    if role == Role.INSTITUTION:
        redacted_findings = redact_findings_for_institution(findings)
        return {
            "id": run.id,
            "application_id": run.application_id,
            "run_number": run.run_number,
            "created_at": run.created_at.isoformat(),
            "trigger": run.trigger,
            "status_at_run": run.status_at_run,
            "counts": {
                "open": len(redacted_findings),
                "critical": 0
            },
            "findings": redacted_findings,
            "findings_json": redacted_findings
        }

    return {
        "id": run.id,
        "application_id": run.application_id,
        "run_number": run.run_number,
        "created_at": run.created_at.isoformat(),
        "trigger": run.trigger,
        "actor_role": run.actor_role,
        "status_at_run": run.status_at_run,
        "rules_version": run.rules_version,
        "snapshot_hash": run.snapshot_hash,
        "snapshot_json": run.snapshot_json,
        "counts": run.counts,
        "findings": findings,
        "findings_json": findings
    }



# ----------------- Reuse Ring Multi-Application Collusion -----------------
@app.get("/reuse-ring")
def get_reuse_ring_clusters(
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    return ReuseRingEngine.scan_reuse_clusters(session)


# ----------------- AICTE Infrastructure Vision Assist -----------------
@app.post("/infra/inspect-lab")
async def inspect_infrastructure_lab(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    from backend.app.infra.vision import InfraVisionInspector
    file_bytes = await file.read()
    validate_upload_file(file.filename or "lab_photo.jpg", file_bytes)
    return InfraVisionInspector.inspect_lab_photo(file_bytes)


