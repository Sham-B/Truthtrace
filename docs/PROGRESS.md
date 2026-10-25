# TruthTrace Implementation Progress Tracker

Track completion of stages across Phases B, C, and D.

- [x] Phase A: Architecture, Ingest, Content Lane, Provenance Lane, Claim Ledger, Core API, Dashboard & Smoke Test
- [x] Stage 1: Classical Forensic Lane (ELA, noise residual, ORB copy-move, metadata, mixed font spans, preliminary indicator labels)
- [x] Stage 2: Dual-Axis Triangulation (Assurance, Suspicion, Sufficiency, Decision Table, Blind-Spot Disclosure, LLM/Template advisory)
- [x] Stage 3: Contradiction Graph & Temporal Rules Engine (Cytoscape graph, temporal rules, identity concordance, benign hypotheses)
- [x] Stage 4: Cryptographic Hash-Chained Audit & RBAC Decision Gate (SHA-256 chain, audit tamper simulation & detection, officer decision gate test)
- [x] Stage 5: Regulatory Alerts Engine (Missing documents, expiring tenancies, pending sources, anomalies, SLA overdue tracking)
- [x] Stage 6: Forgery Drill & Adversarial Evaluation Suite (10 attack variants, ground_truth.json, drill API, heatmap, honest blind-spots table, EVAL.md)
- [x] Stage 7: Scrutiny Dashboard Polish (Assurance x Suspicion interactive scatter plot, queue status filters, KPI counters, bilingual UTF-8 rendering)
- [x] Stage 8: Institution Pre-Flight & Document Replacement (Content-only self check, redaction of forensic internals, versioned document replacement, lock enforcement)
- [x] Stage 9: Multi-Application Reuse Ring Engine (Shared document number collisions, pHash near-duplicates, text-shingle Jaccard, ring alerts)
- [x] Stage 10: Infrastructure Vision Assistant (DETR/OpenCV workstation count, EXIF check, non-fatal advisory fallback)
- [x] Stage 11: Pytest Suite, Documentation & Final Verification (13 baseline passed tests, README with Mermaid & Essential Safeguards mapping, DEMO_SCRIPT.md walkthrough, run.py verified)
- [x] Stage 12: Adversarial Forgery Simulation & Explanation (Adversarial Test Lab, 2D FFT deepfake detector, attack toggles, 8-probe detector matrix, attack wizard, HTML audit report export, 19 total passed tests)

## UI/UX Redesign Stages (10-Second Plain Language Interface)
- [x] Stage 1: Structure and Navigation (Left sidebar, top bar with tricolour accent line, role picker, welcome modal, 5-step coach-mark tour, demo controls drawer, role-based permission visibility)
- [x] Stage 2: Home Dashboard (Row of 4 stat cards with animated count-up, priority attention list, Chart.js donut chart breakdown, last checked timestamp)
- [x] Stage 3: Application List and Detail (Cards with plain status chips, SVG progress rings, 2 action buttons only, "What to do next" guidance banner, 4 workspace tabs: Summary, Documents side-by-side with zoom & bboxes, Cross-checks table & Cytoscape graph, History timeline)
- [x] Stage 4: Data and Logic Fixes (Idempotent validation, finding deduplication by rule/claim/doc, unified compute_plain_status function, 5 canonical archetype seed applications, college pre-submission self-check)
- [x] Stage 5: Insights Pages (Alerts grouped by type, Risk Map scatter plot with X=Concern and Y=Confidence, Duplicate document check cross-college ring, Fraud detection test 10-variant benchmark matrix)
- [x] Stage 6: Decision Flow (Record my decision modal with 3 plain options + reject, mandatory written reason with live character counter, automated check advisory notice, SHA-256 audit log)
- [x] Stage 7: Help and Glossary (6-step visual verification flow, plain-language terminology glossary, Who is Who role guide, GIGW accessibility A-/A/A+ zoom, English / हिन्दी bilingual toggle)
- [x] Stage 8: Offline and Polish (Vendored Chart.js and Cytoscape into frontend/vendor/, updated DEMO_SCRIPT.md 3-minute walkthrough, all 13 pytests passing)

## Check History and What Changed (Versioned, Immutable Validation Runs)
- [x] Stage 1 - Engine (ValidationRun model, snapshot hashing, SHA-1 fingerprinting, diff_runs before/after comparison, determinism)
- [x] Stage 2 - Wiring (Record run on manual/replace/seed, snapshot deduplication idempotency, revision guard 409, RUN_RECORDED audit chain event)
- [x] Stage 3 - API and Access Control (GET /runs list, GET /runs/{n}, GET /runs/diff, Institution content-only redaction, immutability)
- [x] Stage 4 - UI (What changed card, 3 filter tiles, collapsed fixed group, slim summary banner, diff chips, college result panel)
- [x] Stage 5 - Demo Data, Tests, Docs (Seed canonical Check #1, corrected NBA certificate PDF, comprehensive test_run_history.py suite, all 29 tests passing, README & DEMO_SCRIPT updated)
- [x] Stage 6 - Honesty and Tidy-Up (Replaced 100% coverage claim with real 29 tests count, removed 'and diffusion' note, synthetic attack disclaimer added, HTML report linked to audit log, Insights navigation unified under Fraud detection test)

## Public Hosting & GitHub Readiness
- [x] Stage 0: Inspection completed (Python 3.14.8, 29 passing tests, uninitialized git, relative URL and lean hosting plan identified)
- [x] Stage 1: Backend hosting readiness (env-driven settings, derived Fernet key, background seeding, lean health check, CORS & preflight, rate limits, security headers, LOW_MEMORY 110 DPI & OpenCV fallback, demo samples download)
- [x] Stage 2: Render configuration (requirements-render.txt lean runtime, render.yaml blueprint for truthtrace-api in Singapore, Python 3.12 compatibility verified)
- [x] Stage 3: Frontend for GitHub Pages (relative URLs, config.js with API_BASE and apiUrl/api helpers, startup health splash with retry, slim demo notice banner, sample download link in demo controls & college view, cross-origin tested)
- [x] Stage 4: GitHub Pages workflow (.github/workflows/pages.yml with push/workflow_dispatch trigger, site copy to _site, config.js injection from vars.API_BASE_URL, .nojekyll, pages deploy steps)
- [x] Stage 5: Repo hygiene and documentation (.gitignore updated, safe .env.example, Apache-2.0 LICENSE with Sham-B, secret scan clean, README live demo & hosting mode notes, docs/DEPLOYMENT.md guide)
- [x] Stage 6: Git repository initialized with branch main, remote origin configured, clean logical commits prepared without secrets or storage artifacts
- [x] Stage 7: Final checks verified (all 29 tests passing, DEMO_MODE/LOW_MEMORY/DISABLE_OCR verified, rate limit & upload caps enforced, health transitions ready=True)

