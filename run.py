import sys
import webbrowser
import uvicorn
from pathlib import Path

# Add project root to Python sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.config import settings
from backend.app.db import init_db
from backend.synth.seed import seed_database

def main():
    print("=" * 70)
    print("TruthTrace • AICTE Regulatory Scrutiny & Document Verification")
    print("=" * 70)
    print(f"[*] Initializing SQLite Database & Tables...")
    init_db()

    print(f"[*] Checking synthetic seed data (5 canonical example applications)...")
    seed_database(force=False)

    url = f"http://{settings.HOST}:{settings.PORT}"
    print(f"[*] TruthTrace Dashboard starting at: {url}")
    print(f"[*] OpenAPI Interactive Docs: {url}/docs")
    print(f"[*] Role Header defaults to 'Officer' (Switch via UI dropdown or X-Role header)")
    print("=" * 70)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
