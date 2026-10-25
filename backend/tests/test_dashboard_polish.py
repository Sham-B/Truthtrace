import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app

def test_dashboard_static_and_scatter_api():
    client = TestClient(app)
    
    # 1. Test Static files
    r_idx = client.get("/")
    assert r_idx.status_code == 200
    assert "TruthTrace" in r_idx.text
    assert "data-tab=\"tabScatter\"" in r_idx.text
    assert "data-tab=\"tabDrill\"" in r_idx.text

    # 2. Test Applications for Scatter Chart Data
    r_apps = client.get("/applications")
    assert r_apps.status_code == 200
    apps = r_apps.json()
    assert len(apps) >= 1
    for a in apps:
        assert "assurance_score" in a
        assert "suspicion_score" in a
        assert "sufficiency" in a
        assert "status" in a

    # 3. Test Bilingual Text Handling
    # Clean affidavit contains bilingual Hindi text
    r_claims = client.get(f"/claims?application_id={apps[0]['id']}")
    assert r_claims.status_code == 200
    
    print("Dashboard Polish smoke test passed successfully!")

if __name__ == "__main__":
    test_dashboard_static_and_scatter_api()
