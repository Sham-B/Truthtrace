import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from sqlmodel import Session, select
from backend.app.config import ENCRYPTED_DOCS_DIR, BASE_DIR
from backend.app.db import engine, init_db
from backend.app.models import (
    Institution, Application, Document, MockAICTERecord,
    ApplicationCategoryEnum, StatusEnum, AuditEntry, Alert, Claim,
    ValidationRun
)
from backend.app.mock_issuers.router import _CHAOS_STATE
from backend.app.security import save_encrypted_file
from backend.app.audit import log_audit_event
from backend.app.engine.runs import record_run
from backend.app.ingest.loader import DocumentLoader
from backend.app.ingest.classify import classify_document
from backend.app.ingest.extract import FieldExtractor
from backend.app.engine.claims import ClaimLedger
from backend.synth.generate_docs import DocumentGenerator
from backend.synth.forge import DocumentTamperer

SEED_INSTITUTIONS = [
    {
        "pid": "1-1029384751",
        "name": "Aryabhata Institute of Engineering & Technology",
        "address": "Plot 12, Institutional Area, Sector 62, Noida, Uttar Pradesh - 201309",
        "state": "Uttar Pradesh",
        "district": "Gautam Buddha Nagar",
        "pin_code": "201309",
        "approved_intake": 480,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-99120"
    },
    {
        "pid": "1-1029384752",
        "name": "Ramanujan College of Advanced Computing",
        "address": "Survey No. 45/2, IT Expressway, OMR, Sholinganallur, Chennai, Tamil Nadu - 600119",
        "state": "Tamil Nadu",
        "district": "Chennai",
        "pin_code": "600119",
        "approved_intake": 360,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-88219"
    },
    {
        "pid": "1-1029384753",
        "name": "Dr. A.P.J. Abdul Kalam Technical University Campus",
        "address": "Sector 11, Jankipuram Vistar, Lucknow, Uttar Pradesh - 226031",
        "state": "Uttar Pradesh",
        "district": "Lucknow",
        "pin_code": "226031",
        "approved_intake": 600,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-77312"
    },
    {
        "pid": "1-1029384754",
        "name": "Visvesvaraya Institute of Technology & Research",
        "address": "Jnana Sangama, Machhe, Belagavi, Karnataka - 590018",
        "state": "Karnataka",
        "district": "Belagavi",
        "pin_code": "590018",
        "approved_intake": 420,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-66415"
    },
    {
        "pid": "1-1029384755",
        "name": "Bhabha Atomic Engineering Academy",
        "address": "Trombay Institutional Enclave, Chembur, Mumbai, Maharashtra - 400085",
        "state": "Maharashtra",
        "district": "Mumbai Suburban",
        "pin_code": "400085",
        "approved_intake": 300,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-55518"
    },
    {
        "pid": "1-1029384756",
        "name": "CV Raman Global Engineering Institute",
        "address": "Bidyanagar, Mahura, Janla, Bhubaneswar, Odisha - 752054",
        "state": "Odisha",
        "district": "Khordha",
        "pin_code": "752054",
        "approved_intake": 540,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-44621"
    },
    {
        "pid": "1-1029384757",
        "name": "Srinivasa Technical Campus",
        "address": "Gachibowli Financial District, Nanakramguda, Hyderabad, Telangana - 500032",
        "state": "Telangana",
        "district": "Hyderabad",
        "pin_code": "500032",
        "approved_intake": 480,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-33724"
    },
    {
        "pid": "1-1029384758",
        "name": "Meghnad Saha Institute of Computer Sciences",
        "address": "Nazirabad, Uchhepota, EM Bypass, Kolkata, West Bengal - 700150",
        "state": "West Bengal",
        "district": "Kolkata",
        "pin_code": "700150",
        "approved_intake": 360,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-22827"
    },
    {
        "pid": "1-1029384759",
        "name": "Vikram Sarabhai Institute of Space Technology",
        "address": "Veli Hills, Thiruvananthapuram, Kerala - 695022",
        "state": "Kerala",
        "district": "Thiruvananthapuram",
        "pin_code": "695022",
        "approved_intake": 300,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-11930"
    },
    {
        "pid": "1-1029384760",
        "name": "Birla Technological Academy",
        "address": "Vidya Vihar Campus, Pilani, Rajasthan - 333031",
        "state": "Rajasthan",
        "district": "Jhunjhunu",
        "pin_code": "333031",
        "approved_intake": 600,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-90133"
    },
    {
        "pid": "1-1029384761",
        "name": "Homi Bhabha Institute of Artificial Intelligence",
        "address": "University Road, Navrangpura, Ahmedabad, Gujarat - 380009",
        "state": "Gujarat",
        "district": "Ahmedabad",
        "pin_code": "380009",
        "approved_intake": 240,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-80236"
    },
    {
        "pid": "1-1029384762",
        "name": "Sardar Patel College of Technology",
        "address": "Bhavan's Campus, Munshi Nagar, Andheri West, Mumbai, Maharashtra - 400058",
        "state": "Maharashtra",
        "district": "Mumbai Suburban",
        "pin_code": "400058",
        "approved_intake": 480,
        "ter_fee": 100000.0,
        "ter_txn": "TER-2026-70339"
    }
]


def ingest_document_file(
    session: Session,
    application_id: str,
    filename: str,
    file_bytes: bytes,
    known_doc_type: str = ""
) -> Document:
    doc_id = str(uuid.uuid4())
    stored_path = ENCRYPTED_DOCS_DIR / f"{doc_id}.enc"
    save_encrypted_file(file_bytes, stored_path)

    # Inspect PDF or Image
    if filename.lower().endswith(".pdf"):
        inspect_data = DocumentLoader.inspect_and_render_pdf(file_bytes, doc_id)
    else:
        inspect_data = DocumentLoader.inspect_and_render_image(file_bytes, doc_id)

    doc_type = known_doc_type
    if not doc_type:
        classify_res = classify_document(inspect_data, filename)
        doc_type = classify_res["doc_type"]

    doc_obj = Document(
        id=doc_id,
        application_id=application_id,
        doc_type=doc_type,
        original_filename=filename,
        stored_encrypted_path=str(stored_path),
        page_count=inspect_data["page_count"],
        sha256_hash=inspect_data["sha256"],
        phash=inspect_data["phash"],
        status=StatusEnum.VERIFICATION_PENDING
    )
    session.add(doc_obj)
    session.commit()
    session.refresh(doc_obj)

    # Extract fields
    extracted = FieldExtractor.extract_fields_from_doc(doc_type, inspect_data)

    # Record in Claim Ledger
    page_renders = [p.get("render_path", "") for p in inspect_data.get("pages", [])]
    claims = ClaimLedger.record_and_evaluate_claims(
        session=session,
        application_id=application_id,
        doc_id=doc_id,
        doc_type=doc_type,
        extracted_fields=extracted,
        page_renders=page_renders,
        inspect_data=inspect_data,
        doc_bytes=file_bytes
    )

    # Update document status based on claim flags
    if any(c.status == StatusEnum.SOURCE_UNAVAILABLE for c in claims):
        doc_obj.status = StatusEnum.SOURCE_UNAVAILABLE
    elif any(c.status == StatusEnum.EXPIRED for c in claims):
        doc_obj.status = StatusEnum.EXPIRED
    elif any(c.status == StatusEnum.MISMATCH_DETECTED for c in claims):
        doc_obj.status = StatusEnum.MISMATCH_DETECTED
    else:
        doc_obj.status = StatusEnum.VERIFIED

    session.add(doc_obj)
    session.commit()
    session.refresh(doc_obj)

    log_audit_event(
        session=session,
        actor_role="System",
        action="DOCUMENT_INGESTED",
        application_id=application_id,
        doc_id=doc_id,
        payload={"doc_type": doc_type, "filename": filename, "claims_extracted": len(claims)}
    )

    return doc_obj


def ensure_mock_issuer_keys() -> None:
    """Pre-generate persistent Ed25519 keypairs for all mock issuers at startup."""
    from backend.app.security import get_or_create_issuer_keypair
    for issuer in ["sro_delhi", "aicte_portal", "dte_maharashtra", "nba_india"]:
        get_or_create_issuer_keypair(issuer)


def ensure_demo_samples() -> None:
    """Pre-generate corrected sample certificates for live demo downloads."""
    samples_dir = BASE_DIR / "backend" / "synth" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = samples_dir / "corrected_accreditation_certificate.pdf"
    if not sample_pdf.exists():
        inst3 = SEED_INSTITUTIONS[2]
        corrected_acc = DocumentGenerator.generate_nba_certificate_pdf(
            inst_name=inst3["name"], pid=inst3["pid"],
            valid_upto="2028-06-30", cert_no="NBA-2024-ENG-99120", qr_tampered=False
        )
        sample_pdf.write_bytes(corrected_acc)


def seed_database(force: bool = False) -> None:
    init_db()
    ensure_mock_issuer_keys()
    ensure_demo_samples()

    with Session(engine) as session:
        existing_apps = session.exec(select(Application)).all()
        has_encrypted_files = any(ENCRYPTED_DOCS_DIR.glob("*.enc")) if ENCRYPTED_DOCS_DIR.exists() else False
        if len(existing_apps) == 5 and has_encrypted_files and not force:
            print("[Seed] 5 Canonical applications already seeded with documents. Skipping.")
            return

        if force or (len(existing_apps) > 0 and not has_encrypted_files):
            print("[Seed] Resetting database tables, clearing TEST_* audits, and resetting chaos switches...")
            for model in [Claim, Document, Application, Alert, Institution, MockAICTERecord, ValidationRun]:
                for row in session.exec(select(model)).all():
                    session.delete(row)
            for audit in session.exec(select(AuditEntry)).all():
                if audit.application_id and audit.application_id.startswith("TEST_"):
                    session.delete(audit)
                elif audit.actor_role == "TEST":
                    session.delete(audit)
            for k in _CHAOS_STATE:
                _CHAOS_STATE[k]["down"] = False
                _CHAOS_STATE[k]["timeout_seconds"] = 0.0
            session.commit()

        print("[Seed] Seeding institutions and AICTE master records...")
        for data in SEED_INSTITUTIONS:
            inst = Institution(
                id=data["pid"],
                pid=data["pid"],
                name=data["name"],
                address=data["address"],
                state=data["state"],
                district=data["district"],
                pin_code=data["pin_code"],
                approved_intake=data["approved_intake"]
            )
            session.add(inst)

            record = MockAICTERecord(
                pid=data["pid"],
                name=data["name"],
                address=data["address"],
                state=data["state"],
                district=data["district"],
                pin_code=data["pin_code"],
                approved_intake=data["approved_intake"],
                ter_fee_required=data["ter_fee"],
                ter_fee_paid=data["ter_fee"],
                ter_transaction_id=data["ter_txn"],
                previous_eoa_date="2025-05-10"
            )
            session.add(record)
        session.commit()

        # =========================================================================
        # Application 1: Clean Application -> Verified
        # Aryabhata Institute of Engineering & Technology (Noida, UP)
        # =========================================================================
        inst1 = SEED_INSTITUTIONS[0]
        app1_id = "APP-2026-001"
        app1 = Application(
            id=app1_id,
            institution_id=inst1["pid"],
            category=ApplicationCategoryEnum.EOA_RENEWAL,
            academic_year="2026-2027",
            status=StatusEnum.VERIFICATION_PENDING,
            assurance_score=0.98,
            suspicion_score=0.02,
            sufficiency=3
        )
        session.add(app1)
        session.commit()

        print(f"[Seed] Generating documents for {app1_id} (1/5 Clean Verified)...")
        aff1_bytes = DocumentGenerator.generate_affidavit_pdf(
            inst_name=inst1["name"], pid=inst1["pid"], trustee_name="Dr. K. S. Radhakrishnan"
        )
        ingest_document_file(session, app1_id, "Affidavit_AICTE_Format.pdf", aff1_bytes, "affidavit")

        lease1_bytes = DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst1["name"], pid=inst1["pid"], address=inst1["address"],
            lease_start="2021-01-01", lease_expiry="2051-12-31", acres=5.2, doc_no="SUBREG-NOIDA-2021-1029"
        )
        ingest_document_file(session, app1_id, "Registered_Lease_Indenture.pdf", lease1_bytes, "lease_deed")

        noc1_bytes = DocumentGenerator.generate_state_noc_pdf(
            inst_name=inst1["name"], pid=inst1["pid"], noc_no="UP-DTE-NOC-2025-9912", issue_date="2025-10-15"
        )
        ingest_document_file(session, app1_id, "State_Government_NOC.pdf", noc1_bytes, "state_noc")

        ter1_bytes = DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst1["name"], pid=inst1["pid"], txn_id=inst1["ter_txn"], amount=inst1["ter_fee"]
        )
        ingest_document_file(session, app1_id, "TER_Payment_Receipt.pdf", ter1_bytes, "ter_receipt")

        app1.status = StatusEnum.VERIFIED
        session.add(app1)
        session.commit()
        record_run(session, app1_id, trigger="seed", actor_role="System")

        # =========================================================================
        # Application 2: Forged Issuer Signature -> Mismatch found
        # Ramanujan College of Advanced Computing (Chennai, Tamil Nadu)
        # =========================================================================
        inst2 = SEED_INSTITUTIONS[1]
        app2_id = "APP-2026-002"
        app2 = Application(
            id=app2_id,
            institution_id=inst2["pid"],
            category=ApplicationCategoryEnum.EOA_RENEWAL,
            academic_year="2026-2027",
            status=StatusEnum.VERIFICATION_PENDING,
            assurance_score=0.20,
            suspicion_score=0.95,
            sufficiency=3
        )
        session.add(app2)
        session.commit()

        print(f"[Seed] Generating documents for {app2_id} (2/5 Forged Issuer Signature)...")
        aff2_bytes = DocumentGenerator.generate_affidavit_pdf(
            inst_name=inst2["name"], pid=inst2["pid"], trustee_name="Prof. Sundaram Raman"
        )
        ingest_document_file(session, app2_id, "Affidavit_Prescribed.pdf", aff2_bytes, "affidavit")

        # Lease deed with invalid signature in QR seal
        forged_lease2 = DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst2["name"], pid=inst2["pid"], address=inst2["address"],
            lease_start="2020-07-01", lease_expiry="2050-06-30", acres=6.1, doc_no="SUBREG-TN-2020-7711",
            corrupt_signature="AAAA" * 16
        )
        ingest_document_file(session, app2_id, "Lease_Deed_Forged_QR_Seal.pdf", forged_lease2, "lease_deed")

        noc2_bytes = DocumentGenerator.generate_state_noc_pdf(
            inst_name=inst2["name"], pid=inst2["pid"], noc_no="TN-DTE-NOC-2025-4411", issue_date="2025-09-12"
        )
        ingest_document_file(session, app2_id, "State_NOC_Clearance.pdf", noc2_bytes, "state_noc")

        ter2_bytes = DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst2["name"], pid=inst2["pid"], txn_id=inst2["ter_txn"], amount=inst2["ter_fee"]
        )
        ingest_document_file(session, app2_id, "TER_Payment_Receipt.pdf", ter2_bytes, "ter_receipt")

        app2.status = StatusEnum.MISMATCH_DETECTED
        session.add(app2)
        session.commit()
        record_run(session, app2_id, trigger="seed", actor_role="System")

        # =========================================================================
        # Application 3: Expired Accreditation / Lease -> Expired
        # Visvesvaraya Institute of Technology & Research (Belagavi, Karnataka)
        # =========================================================================
        inst3 = SEED_INSTITUTIONS[3]  # Visvesvaraya Institute
        app3_id = "APP-2026-003"
        app3 = Application(
            id=app3_id,
            institution_id=inst3["pid"],
            category=ApplicationCategoryEnum.EOA_RENEWAL,
            academic_year="2026-2027",
            status=StatusEnum.VERIFICATION_PENDING,
            assurance_score=0.45,
            suspicion_score=0.75,
            sufficiency=3
        )
        session.add(app3)
        session.commit()

        print(f"[Seed] Generating documents for {app3_id} (3/5 Expired Accreditation Certificate)...")
        aff3_bytes = DocumentGenerator.generate_affidavit_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], trustee_name="Dr. H. N. Viswanath"
        )
        ingest_document_file(session, app3_id, "Affidavit_Standard.pdf", aff3_bytes, "affidavit")

        lease3_bytes = DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], address=inst3["address"],
            doc_no="SUBREG-KA-2018-9912", lease_start="2018-05-15", lease_expiry="2068-05-14"
        )
        ingest_document_file(session, app3_id, "Registered_Lease_Indenture.pdf", lease3_bytes, "lease_deed")

        expired_acc3 = DocumentGenerator.generate_nba_certificate_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], acc_no="NBA-ACC-2021-9941", valid_upto="2024-06-30"
        )
        ingest_document_file(session, app3_id, "Accreditation_Certificate_Expired.pdf", expired_acc3, "accreditation_certificate")

        noc3_bytes = DocumentGenerator.generate_state_noc_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], noc_no="KA-DTE-NOC-2025-1102", issue_date="2025-08-20"
        )
        ingest_document_file(session, app3_id, "State_NOC_Clearance.pdf", noc3_bytes, "state_noc")

        ter3_bytes = DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], txn_id=inst3["ter_txn"], amount=inst3["ter_fee"]
        )
        ingest_document_file(session, app3_id, "TER_Payment_Receipt.pdf", ter3_bytes, "ter_receipt")

        # Generate sample corrected accreditation certificate for live demo
        samples_dir = Path(__file__).resolve().parent / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)
        corrected_acc = DocumentGenerator.generate_nba_certificate_pdf(
            inst_name=inst3["name"], pid=inst3["pid"], acc_no="NBA-ACC-2024-9941", valid_upto="2028-06-30"
        )
        (samples_dir / "corrected_accreditation_certificate.pdf").write_bytes(corrected_acc)

        app3.status = StatusEnum.EXPIRED
        session.add(app3)
        session.commit()
        record_run(session, app3_id, trigger="seed", actor_role="System")

        # =========================================================================
        # Application 4: Address & Date Contradictions -> Needs review
        # Dr. A.P.J. Abdul Kalam Technical University Campus (Lucknow, UP)
        # =========================================================================
        inst4 = SEED_INSTITUTIONS[2]  # Dr. APJ Abdul Kalam Tech Campus
        app4_id = "APP-2026-004"
        app4 = Application(
            id=app4_id,
            institution_id=inst4["pid"],
            category=ApplicationCategoryEnum.EOA_RENEWAL,
            academic_year="2026-2027",
            status=StatusEnum.VERIFICATION_PENDING,
            assurance_score=0.55,
            suspicion_score=0.65,
            sufficiency=3
        )
        session.add(app4)
        session.commit()

        print(f"[Seed] Generating documents for {app4_id} (4/5 Cross-Doc Contradictions)...")
        # Affidavit says Lucknow, UP
        aff4_bytes = DocumentGenerator.generate_affidavit_pdf(
            inst_name=inst4["name"], pid=inst4["pid"], trustee_name="Dr. Shailendra Mishra",
            affidavit_date="2026-02-15"
        )
        ingest_document_file(session, app4_id, "Affidavit_Standard.pdf", aff4_bytes, "affidavit")

        # Lease deed diverges: claims Plot 88, Andheri West, Mumbai (date 2018)
        divergent_lease4 = DocumentTamperer.tamper_address_divergence(
            inst_name=inst4["name"], pid=inst4["pid"]
        )
        ingest_document_file(session, app4_id, "Lease_Deed_Divergent_Address.pdf", divergent_lease4, "lease_deed")

        noc4_bytes = DocumentGenerator.generate_state_noc_pdf(
            inst_name=inst4["name"], pid=inst4["pid"], noc_no="UP-DTE-NOC-2025-6619", issue_date="2025-09-12"
        )
        ingest_document_file(session, app4_id, "State_NOC_Clearance.pdf", noc4_bytes, "state_noc")

        ter4_bytes = DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst4["name"], pid=inst4["pid"], txn_id=inst4["ter_txn"], amount=inst4["ter_fee"]
        )
        ingest_document_file(session, app4_id, "TER_Payment_Receipt.pdf", ter4_bytes, "ter_receipt")

        app4.status = StatusEnum.MANUAL_REVIEW_REQUIRED
        session.add(app4)
        session.commit()
        record_run(session, app4_id, trigger="seed", actor_role="System")

        # =========================================================================
        # Application 5: Reused Lease Document Number -> Needs review
        # Bhabha Atomic Engineering Academy (Mumbai, Maharashtra)
        # Reuses exact lease registration number SUBREG-NOIDA-2021-1029 from App 1
        # =========================================================================
        inst5 = SEED_INSTITUTIONS[4]  # Bhabha Atomic Engineering Academy
        app5_id = "APP-2026-005"
        app5 = Application(
            id=app5_id,
            institution_id=inst5["pid"],
            category=ApplicationCategoryEnum.EOA_RENEWAL,
            academic_year="2026-2027",
            status=StatusEnum.VERIFICATION_PENDING,
            assurance_score=0.60,
            suspicion_score=0.60,
            sufficiency=3
        )
        session.add(app5)
        session.commit()

        print(f"[Seed] Generating documents for {app5_id} (5/5 Reused Lease Indenture Number)...")
        aff5_bytes = DocumentGenerator.generate_affidavit_pdf(
            inst_name=inst5["name"], pid=inst5["pid"], trustee_name="Prof. Homi J. Sethna"
        )
        ingest_document_file(session, app5_id, "Affidavit_Prescribed.pdf", aff5_bytes, "affidavit")

        # Lease deed using identical doc_no to App 1 ("SUBREG-NOIDA-2021-1029")
        reused_lease5 = DocumentGenerator.generate_lease_deed_pdf(
            inst_name=inst5["name"], pid=inst5["pid"], address=inst5["address"],
            lease_start="2021-01-01", lease_expiry="2051-12-31", acres=5.0, doc_no="SUBREG-NOIDA-2021-1029"
        )
        ingest_document_file(session, app5_id, "Registered_Lease_Reused_Number.pdf", reused_lease5, "lease_deed")

        noc5_bytes = DocumentGenerator.generate_state_noc_pdf(
            inst_name=inst5["name"], pid=inst5["pid"], noc_no="MH-DTE-NOC-2025-3312", issue_date="2025-07-18"
        )
        ingest_document_file(session, app5_id, "State_NOC_Clearance.pdf", noc5_bytes, "state_noc")

        ter5_bytes = DocumentGenerator.generate_ter_receipt_pdf(
            inst_name=inst5["name"], pid=inst5["pid"], txn_id=inst5["ter_txn"], amount=inst5["ter_fee"]
        )
        ingest_document_file(session, app5_id, "TER_Payment_Receipt.pdf", ter5_bytes, "ter_receipt")

        app5.status = StatusEnum.MANUAL_REVIEW_REQUIRED
        session.add(app5)
        session.commit()
        record_run(session, app5_id, trigger="seed", actor_role="System")

        print("[Seed] Initial seed of exactly 5 clean test applications completed successfully.")

if __name__ == "__main__":
    seed_database(force=True)
