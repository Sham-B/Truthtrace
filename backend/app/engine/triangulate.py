import numpy as np
from typing import Dict, Any, List, Optional
from backend.app.models import Claim, Document, LaneVoteEnum, StatusEnum
from backend.app.engine.llm import explain_finding_advisory

BLIND_SPOT_DISCLOSURE = (
    "Forensic Blind-Spot Disclosure: Classical pixel forensics may not detect generative AI-inpainted "
    "modifications or synthetic typography without verifiable Ed25519 cryptographic provenance or "
    "cross-document database concordance."
)

class TriangulationEngine:
    @staticmethod
    def triangulate_claim(
        content_vote: str,
        forensic_vote: str,
        provenance_vote: str,
        flags: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Dual-axis triangulation per claim:
        Outputs: ASSURANCE, SUSPICION, SUFFICIENCY, and DECISION_STATUS.
        """
        votes = [content_vote, forensic_vote, provenance_vote]
        speaking_lanes = [v for v in votes if v != LaneVoteEnum.NA]
        sufficiency = len(speaking_lanes)

        # 1. Calculate Assurance (Positive evidence weighted heavily toward cryptographic provenance)
        pos_points = 0.0
        max_possible_pos = 0.0

        if provenance_vote != LaneVoteEnum.NA:
            max_possible_pos += 0.65
            if provenance_vote == LaneVoteEnum.SUPPORT:
                pos_points += 0.65
            elif provenance_vote == LaneVoteEnum.WEAK:
                pos_points += 0.20

        if content_vote != LaneVoteEnum.NA:
            max_possible_pos += 0.35
            if content_vote == LaneVoteEnum.SUPPORT:
                pos_points += 0.35
            elif content_vote == LaneVoteEnum.WEAK:
                pos_points += 0.15

        assurance_score = round(pos_points / max_possible_pos, 2) if max_possible_pos > 0 else 0.0

        # 2. Calculate Suspicion (Anomaly and discrepancy index)
        suspicion_points = 0.0
        if provenance_vote == LaneVoteEnum.CONTRADICT:
            suspicion_points += 1.0  # Provenance contradiction is definitive
        if forensic_vote == LaneVoteEnum.CONTRADICT:
            suspicion_points += 0.60
        elif forensic_vote == LaneVoteEnum.WEAK:
            suspicion_points += 0.25
        if content_vote == LaneVoteEnum.CONTRADICT:
            suspicion_points += 0.70

        suspicion_score = min(1.0, round(suspicion_points, 2))

        # 3. Deterministic Decision Table
        # Rule 1: No lane able to speak => "cannot_assess" (never mark safe!)
        if sufficiency == 0:
            return {
                "assurance_score": 0.0,
                "suspicion_score": 0.0,
                "sufficiency": 0,
                "status": "cannot_assess",
                "decision_rule": "SUFFICIENCY_ZERO_CANNOT_ASSESS"
            }

        # Rule 2: Cryptographic Provenance mismatch => mismatch_detected regardless of visual pixels
        if provenance_vote == LaneVoteEnum.CONTRADICT:
            return {
                "assurance_score": assurance_score,
                "suspicion_score": max(0.9, suspicion_score),
                "sufficiency": sufficiency,
                "status": StatusEnum.MISMATCH_DETECTED,
                "decision_rule": "PROVENANCE_MISMATCH_DEFINITIVE"
            }

        # Rule 3: Expired document flag
        if any(f.get("reason_code") == "EXPIRED_DOCUMENT" for f in flags):
            return {
                "assurance_score": assurance_score,
                "suspicion_score": suspicion_score,
                "sufficiency": sufficiency,
                "status": StatusEnum.EXPIRED,
                "decision_rule": "DOCUMENT_EXPIRED"
            }

        # Rule 4: Issuer unreachable / Chaos Switch active
        if any(f.get("reason_code") == "ISSUER_UNREACHABLE" for f in flags) or provenance_vote == LaneVoteEnum.WEAK and not flags:
            if any(f.get("reason_code") == "ISSUER_UNREACHABLE" for f in flags):
                return {
                    "assurance_score": assurance_score,
                    "suspicion_score": suspicion_score,
                    "sufficiency": sufficiency,
                    "status": StatusEnum.SOURCE_UNAVAILABLE,
                    "decision_rule": "PROVENANCE_SOURCE_UNAVAILABLE"
                }

        # Rule 5: Forensic anomaly detected but provenance is unavailable => manual_review_required
        if forensic_vote == LaneVoteEnum.CONTRADICT and provenance_vote in [LaneVoteEnum.NA, LaneVoteEnum.WEAK]:
            return {
                "assurance_score": assurance_score,
                "suspicion_score": suspicion_score,
                "sufficiency": sufficiency,
                "status": StatusEnum.MANUAL_REVIEW_REQUIRED,
                "decision_rule": "FORENSIC_ANOMALY_PROVENANCE_UNAVAILABLE"
            }

        # Rule 6: Content mismatch detected
        if content_vote == LaneVoteEnum.CONTRADICT:
            return {
                "assurance_score": assurance_score,
                "suspicion_score": suspicion_score,
                "sufficiency": sufficiency,
                "status": StatusEnum.MISMATCH_DETECTED,
                "decision_rule": "CONTENT_DISCREPANCY_DETECTED"
            }

        # Rule 7: Provenance verified + Content OK => verified
        if (provenance_vote == LaneVoteEnum.SUPPORT or (provenance_vote == LaneVoteEnum.NA and content_vote == LaneVoteEnum.SUPPORT and forensic_vote != LaneVoteEnum.CONTRADICT)):
            return {
                "assurance_score": assurance_score,
                "suspicion_score": suspicion_score,
                "sufficiency": sufficiency,
                "status": StatusEnum.VERIFIED,
                "decision_rule": "TRIANGULATION_VERIFIED"
            }

        return {
            "assurance_score": assurance_score,
            "suspicion_score": suspicion_score,
            "sufficiency": sufficiency,
            "status": StatusEnum.VERIFICATION_PENDING,
            "decision_rule": "DEFAULT_PENDING"
        }

    @classmethod
    def triangulate_application(
        cls,
        claims: List[Claim]
    ) -> Dict[str, Any]:
        """
        Aggregates claim-level triangulations to application-level assurance, suspicion,
        and sufficiency, applying LLM advisory phrasing where appropriate.
        """
        if not claims:
            return {
                "assurance_score": 0.0,
                "suspicion_score": 0.0,
                "sufficiency": 0,
                "status": "cannot_assess",
                "blind_spot_disclosure": BLIND_SPOT_DISCLOSURE
            }

        all_assurances = []
        all_suspicions = []
        lane_speaking_counts = []
        any_mismatch = False
        any_expired = False
        any_manual_review = False
        any_source_unavailable = False

        for c in claims:
            t = cls.triangulate_claim(
                content_vote=c.content_vote,
                forensic_vote=c.forensic_vote,
                provenance_vote=c.provenance_vote,
                flags=c.flags or []
            )
            all_assurances.append(t["assurance_score"])
            all_suspicions.append(t["suspicion_score"])
            lane_speaking_counts.append(t["sufficiency"])

            if t["status"] == StatusEnum.MISMATCH_DETECTED:
                any_mismatch = True
            elif t["status"] == StatusEnum.EXPIRED:
                any_expired = True
            elif t["status"] == StatusEnum.MANUAL_REVIEW_REQUIRED:
                any_manual_review = True
            elif t["status"] == StatusEnum.SOURCE_UNAVAILABLE:
                any_source_unavailable = True

        avg_assurance = round(float(np.mean(all_assurances)), 2) if all_assurances else 0.0
        max_suspicion = round(float(np.max(all_suspicions)), 2) if all_suspicions else 0.0
        overall_sufficiency = int(round(float(np.mean(lane_speaking_counts)))) if lane_speaking_counts else 0

        # Overall Status
        if any_mismatch:
            overall_status = StatusEnum.MISMATCH_DETECTED
        elif any_expired:
            overall_status = StatusEnum.EXPIRED
        elif any_manual_review:
            overall_status = StatusEnum.MANUAL_REVIEW_REQUIRED
        elif any_source_unavailable:
            overall_status = StatusEnum.SOURCE_UNAVAILABLE
        else:
            overall_status = StatusEnum.VERIFIED

        return {
            "assurance_score": avg_assurance,
            "suspicion_score": max_suspicion,
            "sufficiency": overall_sufficiency,
            "status": overall_status,
            "blind_spot_disclosure": BLIND_SPOT_DISCLOSURE
        }
