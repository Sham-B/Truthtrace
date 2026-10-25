import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.models import Claim
from backend.app.engine.temporal import TemporalEngine

def test_temporal_and_identity_graph():
    # 1. Test chronological violation: Lease start (2026-04-01) AFTER affidavit (2026-02-15)
    c1 = Claim(
        id="c-lease-start",
        application_id="app-test",
        doc_id="doc-lease",
        field="lease_start_date",
        value="01-Apr-2026",
        normalized_value="2026-04-01"
    )
    c2 = Claim(
        id="c-affidavit-date",
        application_id="app-test",
        doc_id="doc-aff",
        field="affidavit_date",
        value="15-Feb-2026",
        normalized_value="2026-02-15"
    )
    # 2. Test PID mismatch across documents
    c3 = Claim(
        id="c-pid-aff",
        application_id="app-test",
        doc_id="doc-aff",
        field="pid",
        value="1-1029384751",
        normalized_value="1-1029384751"
    )
    c4 = Claim(
        id="c-pid-lease",
        application_id="app-test",
        doc_id="doc-lease",
        field="pid",
        value="1-9999999999",
        normalized_value="1-9999999999"
    )

    claims = [c1, c2, c3, c4]
    graph = TemporalEngine.evaluate_graph(claims, application_date_str="2026-03-01")

    assert len(graph["elements"]["nodes"]) == 4
    edges = graph["elements"]["edges"]
    assert len(edges) >= 2, f"Expected at least 2 contradiction edges, got {len(edges)}"

    edge_labels = [e["data"]["label"] for e in edges]
    assert "TR_LEASE_BEFORE_AFFIDAVIT" in edge_labels
    assert "IR_PID_CROSS_DOC" in edge_labels

    # Verify benign hypotheses attached to contradictions
    for ct in graph["contradictions"]:
        assert "benign_explanations" in ct
        assert len(ct["benign_explanations"]) >= 1

    print("STAGE 3 CONTRADICTION GRAPH & TEMPORAL TESTS PASSED!")

if __name__ == "__main__":
    test_temporal_and_identity_graph()
