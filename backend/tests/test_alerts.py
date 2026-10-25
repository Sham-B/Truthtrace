import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.main import app
from backend.app.db import engine
from backend.app.engine.alerts import AlertEngine
from backend.synth.seed import seed_database

def test_alerts_engine():
    seed_database(force=False)
    client = TestClient(app)

    # 1. Test scanning alerts via API
    res = client.get("/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert isinstance(alerts, list)
    assert len(alerts) >= 1

    # Verify alert structure
    alert_types = set()
    severities = set()
    for a in alerts:
        assert "alert_type" in a
        assert "severity" in a
        assert "title" in a
        assert "message" in a
        alert_types.add(a["alert_type"])
        severities.add(a["severity"])

    assert severities.intersection({"critical", "warning", "info"})
    print("Detected alert types:", alert_types)
    print("STAGE 5 ALERTS ENGINE TESTS PASSED!")

if __name__ == "__main__":
    test_alerts_engine()
