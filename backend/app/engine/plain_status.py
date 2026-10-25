"""
Unified Plain Language Status and Next-Action Resolver for TruthTrace.
Ensures card verdicts, header chips, and 'What to do next' banners derive
from a single deterministic function.
"""

from typing import Dict, Any, List, Optional
from backend.app.models import StatusEnum


def compute_plain_status(
    raw_status: str,
    unique_findings: Optional[List[Dict[str, Any]]] = None,
    claims: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    Computes human-friendly plain language status, official code, color category,
    icon, plain reason, and actionable next steps.
    
    Colour semantics:
      - green = good
      - amber = needs a human look
      - red = problem
      - blue = waiting
      - grey = unavailable
    """
    findings = unique_findings or []
    status_lower = (raw_status or "").lower()

    # Check finding contents for specific triggers
    has_signature_mismatch = any(
        "SIGNATURE" in f.get("reason_code", "") or "TAMPER" in f.get("reason_code", "")
        for f in findings
    )
    has_expired = (
        status_lower == StatusEnum.EXPIRED or
        any("EXPIRED" in f.get("reason_code", "") for f in findings)
    )
    has_unreachable = (
        status_lower == StatusEnum.SOURCE_UNAVAILABLE or
        any("UNREACHABLE" in f.get("reason_code", "") or "TIMEOUT" in f.get("reason_code", "") for f in findings)
    )
    has_contradiction = any(
        "CONTRADICTION" in f.get("reason_code", "") or "DIVERGENCE" in f.get("reason_code", "")
        or "CONFLICT" in f.get("reason_code", "") or "DISCREPANCY" in f.get("reason_code", "")
        for f in findings
    )
    has_reuse = any(
        "REUSE" in f.get("reason_code", "") or "DUPLICATE" in f.get("reason_code", "")
        or "COLLISION" in f.get("reason_code", "")
        for f in findings
    )

    issue_count = len(findings)

    # 1. Red: Problem (Tampering, Signature Mismatch, Direct Fraud)
    if has_signature_mismatch or (status_lower == StatusEnum.MISMATCH_DETECTED and not has_contradiction and not has_reuse):
        return {
            "plain_status": "Mismatch found",
            "official_code": "STATUS_MISMATCH_DETECTED",
            "color": "red",
            "icon": "✕",
            "issue_count": issue_count,
            "reason": "Cryptographic signature or document content mismatch detected.",
            "what_to_do_next": f"{max(1, issue_count)} document(s) failed the issuer / tamper check. Review highlighted discrepancies in Documents tab, then record your decision."
        }

    # 2. Red/Amber: Expired Document
    if has_expired:
        return {
            "plain_status": "Expired",
            "official_code": "STATUS_EXPIRED",
            "color": "red",
            "icon": "⏱",
            "issue_count": issue_count,
            "reason": "One or more submitted documents or statutory clearances have expired.",
            "what_to_do_next": "A submitted document or accreditation has expired. Verify the expiration date, then request an updated copy from the college or record an inspection referral."
        }

    # 3. Amber: Needs human review (Contradictions, Cross-college reuse, Anomaly without proof)
    if has_reuse:
        return {
            "plain_status": "Needs review",
            "official_code": "STATUS_NEEDS_REVIEW_DUPLICATE",
            "color": "amber",
            "icon": "⚠",
            "issue_count": issue_count,
            "reason": "Document registration number reused across colleges.",
            "what_to_do_next": "The same document number is claimed by another college. Open Insights > Duplicate document check to inspect both applications, then request clarification."
        }

    if has_contradiction or status_lower in ["needs_review", "manual_review_required"]:
        return {
            "plain_status": "Needs review",
            "official_code": "STATUS_NEEDS_REVIEW_CONTRADICTION",
            "color": "amber",
            "icon": "⚠",
            "issue_count": issue_count,
            "reason": "Information contradicts across documents (e.g. address or date difference).",
            "what_to_do_next": "Contradictory information found across submitted documents. Check the Cross-checks tab, then ask the college for clarification."
        }

    # 4. Grey / Blue: Issuer server unreachable or waiting
    if has_unreachable or status_lower == StatusEnum.SOURCE_UNAVAILABLE:
        return {
            "plain_status": "Issuer unavailable",
            "official_code": "STATUS_SOURCE_UNAVAILABLE",
            "color": "grey",
            "icon": "⏸",
            "issue_count": issue_count,
            "reason": "Issuer server did not respond, confirm manually.",
            "what_to_do_next": "The issuing authority's server is unreachable. You can manually inspect the seal, retry later, or request offline confirmation."
        }

    if status_lower == StatusEnum.VERIFICATION_PENDING:
        return {
            "plain_status": "Waiting for issuer",
            "official_code": "STATUS_WAITING_FOR_ISSUER",
            "color": "blue",
            "icon": "⏳",
            "issue_count": 0,
            "reason": "Verification has not yet been executed for this application.",
            "what_to_do_next": "Automated checks are ready to run. Click 'Run checks' to start reading documents and authenticating credentials."
        }

    # 5. Green: Verified (Everything clean)
    return {
        "plain_status": "Verified",
        "official_code": "STATUS_VERIFIED",
        "color": "green",
        "icon": "✓",
        "issue_count": 0,
        "reason": "All automated document, tamper, and issuer checks passed successfully.",
        "what_to_do_next": "All checks are clear. Review the summary cards and proceed to record your approval order."
    }
