import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app

def test_forgery_drill_run_and_results():
    client = TestClient(app)
    
    # Test POST /drill/run
    response = client.post("/drill/run", headers={"X-Role": "Officer"})
    assert response.status_code == 200, f"Drill run failed: {response.text}"
    data = response.json()
    assert "heatmap" in data
    assert len(data["heatmap"]) == 10
    assert data["overall_detection_rate"] >= 0.90
    assert "metrics_by_lane" in data
    
    # Test GET /drill/results
    res_get = client.get("/drill/results", headers={"X-Role": "Officer"})
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["total_variants"] == 10
    print(f"Drill test passed! Overall detection rate: {data_get['overall_detection_rate'] * 100}%")

if __name__ == "__main__":
    test_forgery_drill_run_and_results()
