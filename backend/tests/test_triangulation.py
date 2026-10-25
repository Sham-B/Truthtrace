import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.models import LaneVoteEnum, StatusEnum, Claim
from backend.app.engine.triangulate import TriangulationEngine, BLIND_SPOT_DISCLOSURE

def test_triangulation_decision_table():
    # 1. Provenance mismatch => mismatch_detected regardless of pixels
    res1 = TriangulationEngine.triangulate_claim(
        content_vote=LaneVoteEnum.SUPPORT,
        forensic_vote=LaneVoteEnum.SUPPORT,
        provenance_vote=LaneVoteEnum.CONTRADICT,
        flags=[]
    )
    assert res1["status"] == StatusEnum.MISMATCH_DETECTED
    assert res1["suspicion_score"] >= 0.9

    # 2. Provenance verified + Content OK => verified
    res2 = TriangulationEngine.triangulate_claim(
        content_vote=LaneVoteEnum.SUPPORT,
        forensic_vote=LaneVoteEnum.SUPPORT,
        provenance_vote=LaneVoteEnum.SUPPORT,
        flags=[]
    )
    assert res2["status"] == StatusEnum.VERIFIED
    assert res2["assurance_score"] >= 0.95

    # 3. Forensic anomaly + Provenance unavailable => manual_review_required
    res3 = TriangulationEngine.triangulate_claim(
        content_vote=LaneVoteEnum.SUPPORT,
        forensic_vote=LaneVoteEnum.CONTRADICT,
        provenance_vote=LaneVoteEnum.NA,
        flags=[]
    )
    assert res3["status"] == StatusEnum.MANUAL_REVIEW_REQUIRED

    # 4. Zero sufficiency => cannot_assess (never safe)
    res4 = TriangulationEngine.triangulate_claim(
        content_vote=LaneVoteEnum.NA,
        forensic_vote=LaneVoteEnum.NA,
        provenance_vote=LaneVoteEnum.NA,
        flags=[]
    )
    assert res4["status"] == "cannot_assess"
    assert res4["sufficiency"] == 0

    # 5. Expired flag
    res5 = TriangulationEngine.triangulate_claim(
        content_vote=LaneVoteEnum.CONTRADICT,
        forensic_vote=LaneVoteEnum.NA,
        provenance_vote=LaneVoteEnum.SUPPORT,
        flags=[{"reason_code": "EXPIRED_DOCUMENT"}]
    )
    assert res5["status"] == StatusEnum.EXPIRED

    # 6. Check Blind-spot disclosure text
    app_t = TriangulationEngine.triangulate_application([])
    assert "pixel forensics" in app_t["blind_spot_disclosure"].lower()

    print("STAGE 2 TRIANGULATION TESTS PASSED!")

if __name__ == "__main__":
    test_triangulation_decision_table()
