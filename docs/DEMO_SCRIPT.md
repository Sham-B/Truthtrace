# TruthTrace: 3-Minute Plain-Language Scrutiny Walkthrough Demo Script

Follow this step-by-step narrative to demonstrate TruthTrace to an AICTE Scrutiny Officer, college administrator, or hackathon judge in 3 minutes.

---

### Prerequisites & Launch (0:00 - 0:20)
1. In your terminal, run:
   ```bash
   python run.py
   ```
   *TruthTrace starts the local web server at `http://localhost:8000` with 5 canonical example applications seeded.*
2. Open your browser to `http://localhost:8000`.
3. **First-Load Experience (10-Second Test)**:
   - Observe the **Welcome Modal**: 3 plain cards explain each role:
     - 🏛️ **AICTE Scrutiny Officer**: Review applications, run 3-way checks, and record regulatory decisions.
     - 🎓 **College (applicant)**: Check documents before submission and fix issues.
     - 🛡️ **Auditor**: Verify cryptographic hash-chains and tamper-proof logs.
   - Click **AICTE Scrutiny Officer** to begin.
   - Observe the top bar: Navy banner, text wordmark **TruthTrace**, subtitle *"Application Checking Assistant for AICTE"*, and tricolour accent line (saffron/white/green).
   - Click the **❓** button to see the 5-step coach-mark tour (queue -> status -> checks -> evidence -> decision).

---

### Step 1: Clean Application -> "Verified" (0:20 - 0:45)
1. On the **Home Dashboard**, note the 4 stat cards (*Applications to review: 2, Problems found: 2, Waiting for issuer: 0, Cleared: 1*) with animated count-up and the clean donut chart.
2. In the sidebar, click **Applications**.
3. Select **Aryabhata Institute of Engineering & Technology** (`APP-2026-001`).
4. **What to Observe**:
   - Status chip: 🟢 **Verified** (`STATUS_VERIFIED`) with 0 issues.
   - **What to do next** banner: *"All automated checks passed. Review summary cards and proceed to record your approval order."*
   - Three check cards: **Document check** (OK), **Tamper check** (OK), **Issuer check** (OK).
   - Findings section shows a green card: *"All automated document, tamper, and issuer checks passed."*
   - Collapsed **Limits of this check**: Plain-language reminder that automated checks advise and human judgement matters.

---

### Step 2: Forged Issuer Signature -> "Mismatch found" (0:45 - 1:10)
1. Go back to Applications and click **Ramanujan College of Advanced Computing** (`APP-2026-002`).
2. Click **⚡ Run checks**:
   - Watch the 5-step runner animation: *1. Reading documents -> 2. Document check -> 3. Tamper check -> 4. Issuer check -> 5. Result compilation*.
3. **What to Observe**:
   - Status chip: 🔴 **Mismatch found** (`STATUS_MISMATCH_DETECTED`).
   - Three checks: Document check (OK), Tamper check (OK), **Issuer check (Concern)**.
   - Finding card:
     - Title: *"Forged issuer signature: cryptographic seal mismatch"*
     - Where: `lease_deed` (Page 1)
     - What we found vs What was expected.
     - Collapsed *"This could be innocent if..."* counter-hypotheses.
     - Collapsed *"Technical details"* toggle for reason code and rule ID.
4. Click the **Documents** tab:
   - Select `lease_deed` to view the page image with zoom controls (+, -, Reset) and clickable highlighted bounding boxes matching the discrepancy.

---

### Step 3: Expired NBA Certificate & Contradictions (1:10 - 1:35)
1. Click **Visvesvaraya Institute of Technology & Research** (`APP-2026-003`):
   - Status chip: 🔴 **Expired** (`STATUS_EXPIRED`).
   - Plain reason: Accreditation certificate expired (`valid_upto: 2024-06-30`).
   - Check #1 is saved with 1 critical issue.
2. Click **Dr. A.P.J. Abdul Kalam Technical University Campus** (`APP-2026-004`):
   - Status chip: 🟡 **Needs review** (`STATUS_NEEDS_REVIEW`).
   - Click the **Cross-checks** tab:
     - Review the table: *Document A says (Lease Deed: Sector 62) vs Document B says (Affidavit: Sector 12) -> ✗ Conflict*.
     - Click **Show Interactive Graph** to see the Cytoscape visualization with red dashed conflict edge and plain explanation panel on click.

---

### Step 3b: Live Document Replacement & "What Changed" Comparison (1:35 - 2:05)
1. Switch role to **College (applicant)** via the header role selector.
2. In the sidebar, click **Self-check**:
   - In the "Replace or upload corrected document" section, select **Visvesvaraya Institute of Technology & Research (`APP-2026-003`)**.
   - Select document type: **Accreditation Certificate**.
   - Upload the valid replacement file: `backend/synth/samples/corrected_accreditation_certificate.pdf`.
   - Click **Replace & Version Document**.
3. **What to Observe on the College View**:
   - Friendly post-replacement result panel displays:
     - 🟢 **Fixed (1):** Accreditation certificate was replaced and is now valid.
     - Remaining items to resolve: 0.
     - Note: Only plain-language content checks are shown; internal scores, forensics, and hashes are completely redacted for the college.
4. Switch role back to **AICTE Scrutiny Officer** and open `APP-2026-003`:
   - Status chip updates to: 🟢 **Verified**.
   - **Summary tab:** Slim banner displays: *"Since the last check: 1 fixed, 0 new, 0 still open. See what changed →"*.
   - Click the banner (or open the **History tab**):
     - Top card **"What changed since the last check"** shows 3 filter tiles: **Fixed: 1**, **New: 0**, **Still open: 0**.
     - Plain explanation sentence: *"Since Check #1: Accreditation certificate was replaced (v1 to v2). 1 issue fixed, 0 new, 0 still open."*
     - Fixed findings appear in a collapsed group: *"✓ Fixed in this check (1)"*.
     - Technical details toggle reveals: Document version history, Rules version SHA-256, and comparison selector.
     - Checks list displays **Check #2** (Document replaced, verified) followed by **Check #1** (Seed, flagged).
5. Click **⚡ Run checks** again:
   - A toast immediately informs: *"Nothing has changed since Check #2"*. Snapshot idempotency avoids redundant validations.

---

### Step 4: Duplicate Document Reused Across Colleges (2:05 - 2:25)
1. In the sidebar under **Insights**, click **Duplicate document check**.
2. **What to Observe**:
   - TruthTrace displays cross-college document collisions.
   - See the paired colleges: **Aryabhata Institute** (`APP-2026-001`) and **Bhabha Atomic Engineering** (`APP-2026-005`) reusing the exact same Sub-Registrar lease registration number `SUBREG-NOIDA-2021-1029`.
   - Click **Inspect App 5** to view details.

---

### Step 5: Fraud Detection Test (Benchmark & Sandbox) (2:25 - 2:50)
1. In the sidebar under **Insights**, click **Fraud detection test**.
2. Note the two-button mode switcher: **[ Benchmark | Try an attack yourself ]**.
3. Under **Benchmark**:
   - Click **⚡ Run Test**:
   - Executes benchmark simulation across 10 deliberate tampering attack variants.
   - Headline displays: **"Caught 10 of 10 test forgeries when all three checks are combined"**.
   - Heatmap table compares Document Check vs Tamper Check vs Issuer Check.
   - Honest note on single check limitations: *Pixel forensics alone misses clean lossless text edits, but Ed25519 issuer checks and cross-checks eliminate the blind spots.*

---

### Step 6: Officer Legal Decision & Audit Trail Integrity (2:50 - 3:15)
1. Open **Dr. A.P.J. Abdul Kalam Technical University Campus** (`APP-2026-004`).
2. Click **⚖️ Record my decision**:
   - Modal highlights: *"Automated checks only advise. The decision is yours."*
   - Select: **Ask college for clarification**.
   - Type written reason (min 10 chars): *"Address discrepancy between lease deed and affidavit; please provide municipal certificate."*
   - Click **Confirm & Sign Order**. Toast confirms order signed and hash-chained.
3. In sidebar, click **Activity log**:
   - See the permanent chronological entry with SHA-256 digest.
   - Click **🛡️ Verify Log Integrity**: Green banner confirms hash-chain is 100% intact.
   - (Optional Demo): Click **⚡ Pretend database was altered (Demo)** then verify again to demonstrate tamper detection.
4. **Demo Controls & Reset**:
   - Click the ⚙️ gear icon in top bar.
   - Toggle **Pretend the issuer server is down** to demonstrate graceful `Waiting for issuer` handling.
   - Click **Reset demo data** anytime to cleanly restore the 5 canonical applications and fresh seed checks.

---

### Step 7: Adversarial Test Lab & Attack Wizard (Interactive Bonus)
1. Under **Insights** > **Fraud detection test**, click **Try an attack yourself**.
2. Click **🧙 Attack Wizard** to open guided scenarios:
   - Select **Deepfake Signatory Face Swap**: applies GAN sinusoidal perturbation to the Chairman's verified portrait.
   - Or select **Forged Cryptographic Seal**: corrupts the Ed25519 digital signature bytes.
3. Click **⚡ Run Verification Pipeline**:
   - Observe live canvas preview with spliced anomalies.
   - View the **Triangulation Decision Scorecard** (Suspicion vs Assurance).
   - Review the **8-probe anomaly detector matrix**: note red **FLAGGED** badges with plain-language explanations and green **PASSED** badges with counterfactual hardening hints.
   - *Honesty Note: The lab's synthetic attacks are generated by this project, so the results demonstrate the pipeline, not generalisation to real AI-generated forgeries.*
4. Click **📄 Export Report** to view and print the simulation audit report, verified and linked to the cryptographic audit log.
