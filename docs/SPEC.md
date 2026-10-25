# TruthTrace - System Specification & Architecture Brief

AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification prototype for the AICTE Problem Statement.

---

## 1. System Overview & Philosophy

**TruthTrace** is a free, fully local, open-source prototype designed for autonomous, explainable verification of institutional applications, regulatory compliance documents, and institutional claims for regulatory bodies like AICTE.

### Non-Negotiables & Guiding Principles
1. **AI Only Advises (Advisory-Only Engine)**:
   - Automated components, pipelines, or LLMs can NEVER set a final or adverse outcome (e.g., `rejected`, `refer_for_inspection`, `mark_forged`).
   - Adverse decisions strictly require an authenticated **Officer** role, a written human justification, and are recorded with cryptographic audit logging.
   - An automated test will explicitly verify that AI endpoints cannot transition application states to adverse outcomes directly.
2. **Explainable Flag Specification**:
   - Every flag emitted contains:
     - `reason_code` (e.g., `DATE_ORDER_VIOLATION`, `SEAL_SIGNATURE_MISMATCH`)
     - `plain_language_reason` (clear explanation without technical jargon)
     - `evidence` (document ID, page number, normalized bounding box `[ymin, xmin, ymax, xmax]`)
     - `rule_id` (identifier pointing to YAML configuration, e.g., `TR_001`, `APH §<configure>`)
     - `source_lane` (`content`, `forensic`, or `provenance`)
     - `benign_explanations` (1–3 realistic benign hypotheses explaining why this flag might be a false positive, e.g., scanner compression artifacts, renewal pending).
3. **Configurable YAML Rules**:
   - All checklists, field extraction schemas, validity rules, categories, and handbook references (`APH §<configure>`) are defined in YAML files (`backend/rules/`), never hard-coded.
4. **Role-Based Access Control (RBAC)**:
   - Server-side role enforcement supporting:
     - `Officer`: Full access, views suspicion/assurance scores, forensic internals, decision panel with mandatory written justification.
     - `Institution`: Pre-flight compliance checks, deficiency rectification, uploads. Strictly BLOCKED from viewing detector internals, suspicion scores, or forensic heatmaps to prevent gaming.
     - `Auditor`: Cryptographic audit log inspection and tamper-verification.
   - Header-based demo authorization (`X-Role: Officer`, `X-Role: Institution`, `X-Role: Auditor`).
5. **Encrypted Storage at Rest**:
   - Uploaded and synthetic documents stored encrypted using `cryptography.fernet.Fernet`. The secret key is loaded/auto-generated in `.env` and kept out of version control.
6. **Standardized Status Vocabulary**:
   - Statuses are strictly limited to:
     - `verified`
     - `mismatch_detected`
     - `expired`
     - `verification_pending`
     - `source_unavailable`
     - `manual_review_required`
7. **Offline CPU First**:
   - Runs 100% locally on CPU without paid cloud APIs.
   - Optional local Ollama (`http://localhost:11434`) or Gemini free key for natural language assistance, with fallback to deterministic rule-based extractors.

---

## 2. Core Concepts & Architecture

### 2.1 The Claim Ledger
Every extracted fact is normalized and stored as a structured `Claim`:
- `id`: Unique identifier (UUID).
- `application_id`: Associated application ID.
- `doc_id`: Originating document ID.
- `field`: Canonical name (e.g., `institution_name`, `lease_start_date`, `land_area_acres`, `approved_intake`).
- `value`: Raw extracted string.
- `normalized_value`: Standardized representation (ISO 8601 dates, numeric acres, canonical strings).
- `page`: Page index (0-indexed).
- `bbox`: Normalized coordinates `[ymin, xmin, ymax, xmax]` in range `[0, 1]`.
- `extraction_confidence`: Extraction confidence score `[0, 1]`.
- `lane_votes`: Votes from the three lanes:
  - `content`: `SUPPORT` | `CONTRADICT` | `WEAK` | `NA`
  - `forensic`: `SUPPORT` | `CONTRADICT` | `WEAK` | `NA`
  - `provenance`: `SUPPORT` | `CONTRADICT` | `WEAK` | `NA`
- `status`: Standard claim status.
- `flags`: Associated list of explainable flags.

### 2.2 The Three Independent Evidence Lanes
1. **Content Lane (`backend/app/lanes/content.py`)**:
   - Checklist completeness & required fields presence.
   - Format validity (regex: PAN, PIN code, Registration numbers).
   - Expiry checks against configurable reference dates.
   - Cross-document consistency & Institutional record match (fuzzy matching via `rapidfuzz` against mock AICTE master records: Permanent Institute ID [PID], name, address, previous EoA, approved intake, TER payment, deficiency status).
2. **Forensic Lane (`backend/app/lanes/forensic.py`)**:
   - Classical, explainable, fast CPU-based forensic checks:
     - Error Level Analysis (ELA) map.
     - Local noise-residual inconsistency.
     - JPEG double-compression artifacts.
     - Copy-move forgery detection using OpenCV ORB feature matching.
     - PDF metadata anomaly analysis (producer/creator strings like Photoshop, Canva, GIMP; modDate > creationDate, incremental updates).
     - Mixed font spans in single text block via PyMuPDF font/size inspection.
     - Text-layer vs OCR-of-rendered-page mismatch (detects overlaid/modified text).
     - Perceptual hash (`imagehash.phash`) duplicate detection.
   - Every forensic result is explicitly labelled: `"preliminary indicator"`.
3. **Provenance Lane (`backend/app/lanes/provenance.py` + `backend/app/mock_issuers/router.py`)**:
   - Mock Issuers:
     - Affiliating University (`UNI_MOCK`)
     - State Technical Education Directorate / NOC Authority (`STATE_NOC_MOCK`)
     - National Board of Accreditation (`NBA_MOCK`)
     - Sub-Registrar / Department of Stamps & Registration (`SUB_REGISTRAR_MOCK`)
     - AICTE TER Payment Gateway (`TER_PAY_MOCK`)
   - Cryptographic signing: Issuers sign records with Ed25519 (`cryptography.hazmat.primitives.asymmetric.ed25519`).
   - Documents embed a verifiable QR seal containing `{issuer, doc_no, field_hashes, signature}`.
   - Provenance engine decodes QR via `cv2.QRCodeDetector`, verifies the Ed25519 signature against issuer public keys in registry, and queries mock issuer endpoints.
   - **Chaos Switch**: UI/API toggle enabling simulated timeouts and `source_unavailable` errors to test and demonstrate graceful degradation.

### 2.3 Dual-Axis Triangulation (`backend/app/engine/triangulate.py`)
No single naive "trust score". TruthTrace outputs:
- **Assurance Score**: Positive evidence aggregate, heavily weighted by cryptographic provenance.
- **Suspicion Score**: Anomaly and contradiction aggregate from forensic and content lanes.
- **Sufficiency**: Count of lanes capable of speaking for this claim/document (`0` to `3`).
- **Deterministic Decision Table**:
  - Provenance mismatch $\rightarrow$ `mismatch_detected` regardless of visual appearance.
  - Provenance verified + Content valid $\rightarrow$ `verified`.
  - Forensic anomaly + Provenance unavailable $\rightarrow$ `manual_review_required`.
  - No lane able to speak $\rightarrow$ `"cannot assess"` (never reported as "safe").
- **Forensic Blind-Spot Disclosure**:
  - Mandatory disclosure text attached to every document: `"Pixel forensics may not detect generative AI inpainting or subtle typographical modifications without verifiable cryptographic provenance or cross-document consistency."`

### 2.4 Temporal & Identity Contradiction Graph (`backend/app/engine/temporal.py`)
- Rules configured in `temporal_rules.yaml`:
  - `lease_start <= affidavit_date <= application_date`
  - `lease_expiry > application_date + min_months`
  - Canonical institution name, PID, address consistency across all affidavits, NOCs, certificates.
  - `noc_date < approval_request_date`
  - `ter_fee_paid_date <= application_submission_date`
- Emits contradiction edges (`Claim A` $\leftrightarrow$ `Claim B`, rule ID, reason) rendered as an interactive Cytoscape.js graph.

### 2.5 Counter-Hypotheses Engine (`backend/app/engine/explain.py`)
- For every emitted flag, automatically attaches 1–3 realistic benign hypotheses from `benign_hypotheses.yaml` (e.g., `"scanner re-compression artifact"`, `"sub-registrar seal uses standard district stamp font"`, `"institution renewal letter in transit"`).
- Explains what specific physical or official evidence would settle the doubt.

### 2.6 Multi-Application Reuse Ring (`backend/app/engine/reuse_ring.py`)
- Cross-application similarity detection:
  - Exact or normalized document registration number collision.
  - Perceptual hash hamming distance $< 6$ across unrelated applications.
  - High text-shingle Jaccard similarity across affidavits.
  - Reused lab/infrastructure photos.
- Outputs cluster graph and high-priority cross-application alert.

### 2.7 Hash-Chained Cryptographic Audit Trail (`backend/app/audit.py`)
- Cryptographic append-only log:
  - `entry_id`, `timestamp`, `actor_role`, `action`, `payload`, `prev_hash`, `current_hash = SHA256(prev_hash + payload)`
- Logs all rules applied, records checked, source responses, alerts emitted, and human officer decisions.
- Endpoint `GET /audit/verify` recomputes the hash chain from genesis and reports if integrity holds or flags the exact index of tampering.

### 2.8 Infrastructure & Computer Vision Assist (`backend/app/infra/vision.py`)
- Classical + optional DETR model for counting lab computers, chairs, monitors, and safety equipment in synthetic lab photos.
- Compares detected counts against category norms.
- Strictly advisory: flags `"additional evidence required"` or `"recommend physical inspection"`. Never crashes if models are not present.

---

## 3. Technology Stack & Directory Structure

```
truthtrace/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── audit.py
│   │   ├── ingest/
│   │   │   ├── loader.py
│   │   │   ├── ocr.py
│   │   │   ├── classify.py
│   │   │   └── extract.py
│   │   ├── lanes/
│   │   │   ├── content.py
│   │   │   ├── forensic.py
│   │   │   └── provenance.py
│   │   ├── engine/
│   │   │   ├── claims.py
│   │   │   ├── temporal.py
│   │   │   ├── triangulate.py
│   │   │   ├── reuse_ring.py
│   │   │   ├── explain.py
│   │   │   └── alerts.py
│   │   ├── infra/
│   │   │   └── vision.py
│   │   ├── mock_issuers/
│   │   │   └── router.py
│   │   └── adapters/
│   │       └── aicte_portal.py
│   ├── rules/
│   │   ├── categories.yaml
│   │   ├── checklists/
│   │   │   ├── eoa_renewal.yaml
│   │   │   ├── intake_increase.yaml
│   │   │   └── new_course.yaml
│   │   ├── temporal_rules.yaml
│   │   └── benign_hypotheses.yaml
│   ├── synth/
│   │   ├── generate_docs.py
│   │   ├── forge.py
│   │   └── seed.py
│   ├── eval/
│   │   └── run_eval.py
│   └── tests/
│       ├── test_decision_gate.py
│       ├── test_audit_chain.py
│       ├── test_triangulation.py
│       ├── test_temporal_rules.py
│       └── test_signature_verify.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── docs/
│   ├── SPEC.md
│   ├── README.md
│   ├── DEMO_SCRIPT.md
│   └── EVAL.md
├── project_report.md
├── run.py
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 4. Phased Implementation Roadmap

- **Phase A**: Core architecture, DB models, YAML rules, Ingest (PyMuPDF text layer + words with bboxes + render pages to PNG + OCR fallback), Classifiers & Field Extractors, Content Lane, Mock Issuers with Ed25519 signing & QR verification (Provenance Lane), Claim Ledger, Core FastAPI endpoints, and Minimal Web UI (Queue, Report, Evidence viewer with bounding boxes). Smoke test with 3 synthetic applications.
- **Phase B**: Forensic Lane (ELA, noise residual, JPEG double-compression, ORB copy-move, PDF metadata, font spans, text-layer vs OCR mismatch, pHash), Triangulation (Assurance, Suspicion, Sufficiency, Blind-spot notice), Temporal & Identity Contradiction Graph, Counter-hypotheses engine, Hash-chained Audit trail, Server-side RBAC, Officer Decision gate + test, Alerts engine.
- **Phase C**: Forgery Drill simulator + evaluation matrix (`docs/EVAL.md`), Multi-app Reuse Ring detector, Vision Infra Assist, Dashboard enhancement (Assurance vs Suspicion scatter, Heatmap, Cytoscape graph), Chaos switch, Institution Pre-flight portal.
- **Phase D**: Pytest test suite (Officer decision gate test, Audit integrity test, Triangulation decision table, Temporal rules, Ed25519 QR signature verify), Complete README with Mermaid architecture and API integration guide, DEMO_SCRIPT.md walkthrough, and end-to-end smoke test.
