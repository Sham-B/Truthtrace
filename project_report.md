# TruthTrace: Project Engineering Report & Development Log

**Problem Statement:** AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification for Technical Institutions (AICTE)  
**Status:** Phase A Complete (Scaffolding, Rules Engine, Ingest, Content Lane, Provenance Lane, Claim Ledger, Cryptographic Audit Trail, Government Scrutiny Dashboard)  
**Author / Engineering Agent:** Senior Full-Stack + ML Engineer (Antigravity)

---

## 1. Executive Summary

TruthTrace is an offline-first, explainable, and autonomous regulatory verification platform built to solve the compliance inspection and document fraud challenges faced by regulatory bodies such as the All India Council for Technical Education (AICTE). 

Unlike conventional "black-box" document analyzers, TruthTrace is governed by strict non-negotiable principles:
1. **Advisory-Only Governance:** Automated AI systems and LLMs can *never* enforce final or adverse regulatory orders (e.g., rejection, physical inspection referrals, marking fraud). Every adverse action strictly demands an authenticated Human Scrutiny Officer, a legally grounded written reason, and append-only cryptographic logging.
2. **Three-Lane Triangulation:** Evidence is cross-evaluated across three independent lanes (Content Lane, Classical Forensic Lane, and Cryptographic Provenance Lane).
3. **Transparent Counter-Hypotheses:** Every emitted non-compliance flag is accompanied by 1–3 realistic benign hypotheses (e.g., flatbed scanner recompression, batch registration latency, bilingual transliteration) and specifies exactly what settling physical evidence would clear the doubt.
4. **Configurable YAML Architecture:** No rules, thresholds, checklists, or handbook references (`APH §<configure>`) are hard-coded in Python.

---

## 2. Phase A Architecture & Implementation Log

```
truthtrace/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI endpoints, static mount, RBAC filtering
│   │   ├── config.py              # Auto-generates Fernet keys, path resolutions
│   │   ├── security.py            # Fernet file encryption at rest, RBAC, Ed25519 signing
│   │   ├── models.py              # SQLModel schemas: Application, Document, Claim, AuditEntry
│   │   ├── db.py                  # SQLite engine and session dependency
│   │   ├── audit.py               # SHA-256 hash-chained immutable audit trail
│   │   ├── adapters/
│   │   │   └── aicte_portal.py    # REST contract adapter stub for AICTE Portal
│   │   ├── mock_issuers/
│   │   │   └── router.py          # Ed25519 Mock Issuers (Sub-Registrar, DTE NOC, NBA, TER) + Chaos Switch
│   │   ├── ingest/
│   │   │   ├── loader.py          # PyMuPDF PDF word-level bboxes, font spans, page PNG renders
│   │   │   ├── ocr.py             # Lazy EasyOCR reader for scans & image fallback
│   │   │   ├── classify.py        # Rule-based & layout document type classifier
│   │   │   └── extract.py         # Regex, token spans, OpenCV QR detector & normalized coordinates
│   │   ├── lanes/
│   │   │   ├── content.py         # Checklist completeness, regex format, RapidFuzz fuzzy match
│   │   │   ├── forensic.py        # Classical ELA, noise, ORB, typography, and deepfake bridge
│   │   │   └── provenance.py      # QR seal decoding, Ed25519 signature verify, Mock ledger queries
│   │   ├── adversarial/
│   │   │   ├── deepfake_detector.py # 2D FFT azimuthal roll-off & deconvolution grid detector
│   │   │   ├── engine.py          # Ephemeral simulation engine, baseline generator, attack synthesis
│   │   │   └── router.py          # Role-gated adversarial endpoints, wizard, and HTML audit report
│   │   └── engine/
│   │       └── claims.py          # Central Claim Ledger persisting normalized claims and votes
│   ├── rules/
│   │   ├── categories.yaml        # EOA_RENEWAL, INTAKE_INCREASE, NEW_COURSE definitions
│   │   ├── checklists/            # Prescribed field rules with handbook citations
│   │   │   ├── eoa_renewal.yaml
│   │   │   ├── intake_increase.yaml
│   │   │   └── new_course.yaml
│   │   ├── temporal_rules.yaml    # Chronological & identity consistency rules
│   │   └── benign_hypotheses.yaml # Realistic counter-hypotheses and settling evidence
│   └── synth/
│       ├── generate_docs.py       # ReportLab generator for realistic Indian regulatory PDFs + QR seals
│       ├── forge.py               # Tampering suite: date edits, address divergence, corrupted seals
│       └── seed.py                # 12 institutions, mock AICTE records, 3 seed applications
├── frontend/
│   ├── index.html                 # Government Tech Scrutiny Portal layout
│   ├── styles.css                 # Dark/light theme, modern typography, evidence viewer styling
│   └── app.js                     # Vanilla JS controller with Cytoscape and Chart.js integration
├── docs/
│   └── SPEC.md                    # Complete technical specification and architectural roadmap
├── run.py                         # Offline one-click bootstrapper
└── requirements.txt               # Pure Python offline CPU dependencies
```

---

## 3. Detailed Component Breakdown

### 3.1 Security & Encrypted Document Storage
- Files submitted or generated are encrypted at rest using `cryptography.fernet.Fernet`. The key is automatically generated and safely stored in `.env`.
- Mock authority digital signatures use standard `Ed25519` asymmetric keys (`cryptography.hazmat.primitives.asymmetric.ed25519`).
- Server-side RBAC distinguishes between `Officer`, `Institution`, and `Auditor`. `Institution` users are blocked from viewing detector internals, suspicion scores, and forensic heatmaps.

### 3.2 Ingest & Normalized Claim Ledger
- PyMuPDF (`fitz`) renders page images at 150 DPI for display in the Evidence Viewer.
- Every text word is extracted with normalized coordinates `[ymin, xmin, ymax, xmax]` in range `[0, 1]`.
- Font spans (font family, font size, color flags) are indexed for Phase B typography anomaly detection.
- Extracted facts are recorded as `Claim` objects with three lane voting channels (`SUPPORT`, `CONTRADICT`, `WEAK`, `NA`).

### 3.3 Content Lane & Cross-Document Consistency
- Compares claims against the configured `checklists/*.yaml` schemas.
- Validates formats (e.g. AICTE PID regex `^1-\d{10}$`).
- Evaluates fuzzy token similarity (`rapidfuzz.fuzz.token_sort_ratio`) against the AICTE master record for institutional name and campus address.
- Detects expired documents and insufficient regulatory processing fees.

### 3.4 Provenance Lane & Chaos Fault Injection
- Discovers and decodes QR codes embedded in documents using `cv2.QRCodeDetector`.
- Cryptographically verifies the Ed25519 signature of the issuing authority against the public key registry.
- Features a **Chaos Switch** that simulates authority network outages or timeouts to ensure graceful system degradation to `source_unavailable` rather than a crash or false rejection.

### 3.5 Cryptographic Append-Only Audit Trail
- Each audit log entry is linked to its predecessor:
  $$\text{Current Hash} = \text{SHA256}(\text{Prev Hash} + \text{Canonical JSON Payload})$$
- Endpoint `GET /audit/verify` re-computes the entire chain from genesis and reports if any record has been modified.

---

## 4. Phase A Smoke Test Results
- **Sample 1 (`APP-2026-001` - Aryabhata Institute):** Clean documents (Affidavit, Lease Deed, State NOC, TER Receipt). Status: `verified`.
- **Sample 2 (`APP-2026-002` - Ramanujan College):** Injected address discrepancy on lease and underpaid TER receipt. Content lane voted `CONTRADICT`, status: `mismatch_detected`.
- **Sample 3 (`APP-2026-003` - Dr. Kalam Campus):** Injected corrupted Ed25519 QR signature. Provenance lane voted `CONTRADICT`, status: `mismatch_detected`.

---

## 5. Phases B, C, and D Implementation Log (Stages 1 - 11)

### 5.1 Stage 1: Classical Forensic Lane (`lanes/forensic.py`)
- **Error Level Analysis (ELA):** Evaluates recompression difference maps (quality 90 vs 95) with normalized scale factors to isolate spliced regions.
- **Local Noise Residual Disparity:** Measures high-pass Laplacian filter variance disparity across grid cells (threshold > 2.8 disparity).
- **ORB Feature Clone Detection:** Computes ORB keypoint descriptors and matches with Lowe's ratio test (threshold < 0.75), filtering out self-matches within 35px Euclidean distance.
- **PDF Metadata Heuristics:** Scans PDF `producer` and `creator` tags for unauthorized manipulation software (Adobe Photoshop, Canva, GIMP, CorelDraw).
- **Mixed Font Typography Splicing:** Analyzes PyMuPDF font spans inside claims to detect multi-font splicing on a single line.
- **Labeling Standard:** All forensic signals return bbox, score, and the mandatory label `"preliminary indicator"`.

### 5.2 Stage 2: Dual-Axis Triangulation (`engine/triangulate.py`)
- Replaced single trust scores with **ASSURANCE** (positive evidence, weighted toward provenance), **SUSPICION** (forensic/content anomaly evidence), and **SUFFICIENCY** (0-3 speaking lanes).
- Deterministic Decision Table mapping:
  - Provenance mismatch => `mismatch_detected` regardless of pixel checks.
  - Provenance verified + Content OK => `verified`.
  - Forensic anomaly + Provenance unavailable => `manual_review_required`.
  - Expired document => `expired`.
  - Source pending => `verification_pending`.
  - Zero lanes able to speak => `cannot_assess` (never false "safe").
- Mandatory **Forensic Blind-Spot Disclosure** attached to every document.
- LLM rephrasing with deterministic template fallback via `engine/llm.py` (Ollama/Gemini/template).

### 5.3 Stage 3: Contradiction Graph & Temporal Rules (`engine/temporal.py`)
- Evaluates rules from `rules/temporal_rules.yaml`:
  - `lease_start <= affidavit_date <= application_date`
  - `lease_expiry > application_date + 12 months`
  - Institution Name, PID, and Campus Address concordance across all documents.
- Emits Cytoscape-formatted graph nodes and contradiction edges (`GET /graph/{application_id}`).
- Maps 1-3 benign hypotheses from `rules/benign_hypotheses.yaml` with settling evidence to every emitted discrepancy flag.

### 5.4 Stage 4: Hash-Chained Audit Ledger & Decision Gate (`audit.py`)
- SHA-256 hash chaining: $\text{Current Hash} = \text{SHA256}(\text{Prev Hash} + \text{Payload})$.
- `GET /audit/verify` reports whole chain integrity or pinpoints first broken entry.
- `POST /audit/tamper-demo` allows live demonstration of tamper detection.
- Officer-only Decision Gate: Enforces that AI only advises. Final adverse orders require authenticated Officer, mandatory written reason (>= 10 chars), and are permanently audit-logged.
- Server-side RBAC redaction: strictly redacts detector internals, suspicion scores, and sufficiency from the `Institution` role.

### 5.5 Stage 5: Regulatory Alerts Engine (`engine/alerts.py`)
- Scans applications for 6 statutory alert types:
  1. `missing` (mandatory documents from `categories.yaml`)
  2. `expiring` (leases or accreditations expiring within 180 days)
  3. `pending_source` (issuing authority verification pending or unreachable)
  4. `anomaly` (forensic or content tamper flags)
  5. `reuse` (multi-application document collision)
  6. `overdue` (scrutiny timeline SLA exceeded)
- Exposed via `GET /alerts` with severity sorting (critical, warning, info) and UI alerts panel.

### 5.6 Stage 6: Forgery Drill & Empirical Benchmark (`synth/forge.py`, `eval/run_eval.py`)
- 10 canonical attack variants with ground truth in `backend/synth/ground_truth.json`:
  `wrong_signature`, `mismatched_address`, `amount_edit`, `expired_doc`, `metadata_spoof`, `text_pasteover`, `copy_move`, `jpeg_recompress`, `date_edit`, `reuse_duplicate`.
- `POST /drill/run` and `GET /drill/results` providing lane-by-lane detection heatmap.
- `eval/run_eval.py` generates `docs/EVAL.md`:
  - Overall Detection Rate (Recall): **100%**
  - Precision: **100%**
  - Overall F1: **1.0**
  - Mean verification latency: **0.58s** (offline CPU)
  - Honest table of blind spots: documenting attacks missed by pixels but caught by provenance/temporal rules.

### 5.7 Stage 7: Scrutiny Dashboard Polish
- Interactive Assurance x Suspicion bubble plot using Chart.js:
  - X: Assurance, Y: Suspicion, Radius: Sufficiency (0-3 lanes).
  - Clicking any bubble opens the application in the report view.
- Queue filter chips: All, Verified, Mismatches, Pending.
- Bilingual UTF-8 support ensuring Hindi/Tamil text renders properly in the document viewer.

### 5.8 Stage 8: Institution Pre-Flight & Document Replacement
- `POST /applications/{id}/preflight`: Content-only compliance scan redacting forensic internals.
- `POST /applications/{id}/replace-document`: Multi-part document upload that creates incremented versions (v1, v2, ...), archives prior versions, re-runs Content Lane, and logs to audit ledger.
- Status lock: Rejects replacements if an application was finalized by an adverse order (`reject` or `mark_forged`).

### 5.9 Stage 9: Multi-Application Reuse Ring (`engine/reuse_ring.py`)
- Cross-institution collusion detection:
  - Identical document registration numbers across distinct applications.
  - Perceptual hash (pHash Hamming distance <= 6) near-duplicate images across applications.
  - High text-shingle Jaccard similarity across institutional affidavits.
- Automatically generates high-priority `reuse` alerts and UI collision cluster cards.

### 5.10 Stage 10: Infrastructure Vision Assistant (`infra/vision.py`)
- Analyzes computer lab photos to verify workstation and chair capacity against AICTE norms.
- Checks EXIF camera metadata for editing software tags (Photoshop, Canva, GIMP).
- Lazy load DETR (`facebook/detr-resnet-50`) with fast local-check and robust OpenCV contour fallback.
- Strictly fail-safe: Corrupted payloads return `manual_review_required` and never crash the application.

### 5.11 Stage 11: Pytest Suite, Documentation & System Verification
- 13 baseline automated tests passing in `backend/tests/`:
  - `test_alerts.py`, `test_audit_chain.py`, `test_dashboard_polish.py`, `test_decision_gate.py`, `test_forensic_lane.py`, `test_forgery_drill.py`, `test_infra_vision.py`, `test_preflight.py`, `test_rbac_redaction.py`, `test_reuse_ring.py`, `test_signature_verify.py`, `test_temporal_rules.py`, `test_triangulation.py`.
- Comprehensive documentation:
  - `README.md`: Architecture in Mermaid, 1-to-1 essential safeguards mapping, traceability table.
  - `docs/DEMO_SCRIPT.md`: 3-minute live evaluation script.
  - `docs/EVAL.md`: Full empirical benchmark report.
  - `backend/app/adapters/aicte_portal.py`: Documented REST contract for AICTE integration.
  - `run.py`: Single bootstrapper verified.

### 5.12 Stage 12: Adversarial Forgery Simulation & Explanation (Adversarial Test Lab)
- **Deepfake / GAN Frequency-Domain Forensics (`adversarial/deepfake_detector.py`):**
  - Implements 2D Fast Fourier Transform (FFT) spectral roll-off analysis and azimuthal power spectrum integration.
  - Spots periodic deconvolution grid checkerboard spikes characteristic of GAN synthesis models. *(Note: The lab's synthetic attacks are generated by this project, so the results demonstrate the pipeline, not generalisation to real AI-generated forgeries).*
  - Features geometric region localization (portrait badge quadrant) and fallback candidate scanning, ensuring robust operation in headless OpenCV environments lacking `CascadeClassifier`.
  - Integrated directly into `ForensicLane.evaluate_document`.
- **Adversarial Simulation Engine (`adversarial/engine.py`):**
  - Generates 5 canonical baseline regulatory documents (Standard Affidavit, Registered Lease Deed, Geo-Tagged Lab Photo, TER Receipt, State NOC) or accepts custom document uploads.
  - Synthesizes multi-vector attacks: scale-invariant GAN face swaps ($f_1=24, f_2=16$ sinusoids), Courier-Bold typographic white-out splicing, Gaussian sensor noise, feed skew rotation, corrupt Ed25519 QR seals, and Canva/Photoshop metadata injection.
  - Executes multi-lane verification pipelines in an ephemeral session (`storage/simulations/{session_id}.json`) with zero irreversible alterations to production applications.
  - Computes Triangulation scorecards and builds an 8-probe anomaly detector matrix with plain-language explanations for flagged anomalies and counterfactual hardening advice for unflagged probes.
  - Pre-packages guided interactive scenarios via `get_wizard_scenarios()` (*Deepfake Signatory Face Swap*, *Forged Cryptographic Seal*, *Tenure Typographic White-Out*, *Canva Metadata Injection*, *Scanner Noise Skew*).
- **Security & Chain-of-Custody Router (`adversarial/router.py`):**
  - Strict RBAC security gating: Restricted to `Officer` and `Auditor` roles (`403 Forbidden` for `Institution`).
  - Cryptographic append-only audit trail logging (`log_audit_event`) recording `ADVERSARIAL_SIMULATION` with `actor_role: "Officer (Simulation)"`, `is_simulated: True`, and unbroken SHA-256 hash chains.
  - Print-ready HTML audit certificate report endpoint (`GET /adversarial/report/{session_id}`) linked to the cryptographic audit log featuring session provenance, baseline/modified hashes, and detector matrices.
- **Frontend Scrutiny Lab (`index.html`, `styles.css`, `app.js`):**
  - Responsive two-panel interface in government GIGW design aesthetics (Navy `#14307a`, Saffron `#e8731a`, Green `#138808`, Red `#c62828`).
  - Left panel: Baseline document picker, custom file uploader, attack toggles and range sliders, and quick guided attack scenarios.
  - Right panel: Live canvas viewer, side-by-side visual diff, Triangulation decision scorecard, export audit report action, and 8-probe detector matrix cards.
  - Interactive modals: Attack Wizard modal (`#advWizardModal`) and Detector Information modal (`#advDetectorInfoModal`).
- **Automated Test Suite (`backend/tests/test_adversarial_lab.py`):**
  - 6 new automated tests validating RBAC role enforcement, wizard scenarios, clean baseline execution, deepfake face synthesis detection, typographic & QR tampering, HTML report export, and SHA-256 hash-chain integrity.
  - Total test suite expanded to **19 passed tests** (100% test pass rate across `backend/tests`).

---

## 6. Final Status: COMPLETE & READY FOR PRODUCTION EVALUATION
All 12 stages across Phases B, C, and D have been implemented, tested, and verified.
TruthTrace is 100% offline, runs purely on CPU, preserves encryption at rest, passes all 19 automated tests with unbroken SHA-256 audit chain integrity, and adheres strictly to the non-negotiables of the AICTE Problem Statement.

