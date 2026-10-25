import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app
from backend.app.db import get_session
from backend.app.models import Application, Claim, Document, LaneVoteEnum, StatusEnum

def test_reuse_ring_detection():
    client = TestClient(app)

    # 1. Insert a deliberate cross-application document registration collision
    # Using existing seeded apps
    with next(get_session()) as session:
        apps = session.query(Application).limit(2).all()
        assert len(apps) >= 2
        app1_id = apps[0].id
        app2_id = apps[1].id

        collision_doc_no = "COLLISION-REG-2026-9999"

        # Check if already present or add
        c1 = session.query(Claim).filter(Claim.application_id == app1_id, Claim.field == "registered_doc_no").first()
        if c1:
            c1.normalized_value = collision_doc_no
            session.add(c1)
        else:
            c1 = Claim(
                id="claim-reuse-01",
                application_id=app1_id,
                doc_id="doc-test-1",
                field="registered_doc_no",
                value=collision_doc_no,
                normalized_value=collision_doc_no
            )
            session.add(c1)

        c2 = session.query(Claim).filter(Claim.application_id == app2_id, Claim.field == "registered_doc_no").first()
        if c2:
            c2.normalized_value = collision_doc_no
            session.add(c2)
        else:
            c2 = Claim(
                id="claim-reuse-02",
                application_id=app2_id,
                doc_id="doc-test-2",
                field="registered_doc_no",
                value=collision_doc_no,
                normalized_value=collision_doc_no
            )
            session.add(c2)

        session.commit()

    # 2. Query GET /reuse-ring
    response = client.get("/reuse-ring", headers={"X-Role": "Officer"})
    assert response.status_code == 200
    data = response.json()
    assert "clusters" in data
    assert data["total_clusters"] >= 1

    # Check that collision cluster was identified
    matched_cluster = None
    for cl in data["clusters"]:
        if cl["shared_value"] == collision_doc_no:
            matched_cluster = cl
            break

    assert matched_cluster is not None, "Failed to identify registered_doc_no collision cluster"
    assert app1_id in matched_cluster["applications"]
    assert app2_id in matched_cluster["applications"]

    # 3. Verify high priority alert was generated
    r_alerts = client.get("/alerts", headers={"X-Role": "Officer"})
    assert r_alerts.status_code == 200
    alerts = r_alerts.json()
    assert any(a["alert_type"] == "reuse" for a in alerts)

    print("Stage 9 (Reuse Ring Multi-Application Collusion) passed successfully!")

if __name__ == "__main__":
    test_reuse_ring_detection()
