import io
import sys
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app
from backend.synth.generate_docs import DocumentGenerator
from backend.app.infra.vision import InfraVisionInspector

def test_infra_vision_lab_inspection():
    client = TestClient(app)

    # 1. Generate clean lab photo
    lab_bytes = DocumentGenerator.generate_lab_photo(
        inst_name="Aryabhata Institute of Engineering & Technology",
        pid="1-1029384751"
    )

    # 2. Direct unit test of InfraVisionInspector
    res = InfraVisionInspector.inspect_lab_photo(lab_bytes)
    assert "status" in res
    assert "advisory" in res
    assert "counts" in res
    assert res["status"] in ["verified", "manual_review_required"]
    print(f"Direct inspection result: status={res['status']}, advisory='{res['advisory']}'")

    # 3. Test API endpoint POST /infra/inspect-lab
    files = {"file": ("lab_inspection.jpg", io.BytesIO(lab_bytes), "image/jpeg")}
    r_api = client.post("/infra/inspect-lab", files=files)
    assert r_api.status_code == 200
    api_data = r_api.json()
    assert "advisory" in api_data

    # 4. Critical requirement: Corrupt / garbage input must NEVER crash the app, returns manual_review_required
    corrupt_bytes = b"NOT_A_VALID_IMAGE_PAYLOAD_GARBAGE"
    corrupt_res = InfraVisionInspector.inspect_lab_photo(corrupt_bytes)
    assert corrupt_res["status"] == "manual_review_required"
    assert "recommend physical inspection" in corrupt_res["advisory"]

    print("Stage 10 (AICTE Infrastructure Vision Assist) passed successfully!")

if __name__ == "__main__":
    test_infra_vision_lab_inspection()
