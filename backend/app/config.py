import os
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings

# Thread limits for low memory / free tier hosting
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RULES_DIR = BASE_DIR / "backend" / "rules"
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
ENCRYPTED_DOCS_DIR = STORAGE_DIR / "encrypted"
RENDER_CACHE_DIR = STORAGE_DIR / "renders"

for d in [DATA_DIR, STORAGE_DIR, ENCRYPTED_DOCS_DIR, RENDER_CACHE_DIR, STORAGE_DIR / "keys", STORAGE_DIR / "simulations"]:
    d.mkdir(parents=True, exist_ok=True)


def derive_fernet_key(secret: str) -> str:
    """Derive a valid 32-byte urlsafe base64 Fernet key from an arbitrary SECRET_KEY."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


class Settings(BaseSettings):
    APP_NAME: str = "TruthTrace"
    APP_ENV: str = "development"
    HOST: str = "0.0.0.0" if os.getenv("RENDER") or os.getenv("PORT") else "127.0.0.1"
    PORT: int = int(os.getenv("PORT", "8000"))
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'truthtrace.db'}"
    SECRET_KEY: str = ""
    FERNET_KEY: str = ""
    SECRET_FERNET_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000,https://sham-b.github.io"
    DEMO_MODE: bool = False
    LOW_MEMORY: bool = False
    DISABLE_OCR: bool = False
    LLM_PROVIDER: str = "none" if os.getenv("DEMO_MODE") in ("1", "true", "True") else "ollama"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_URL: str = "http://localhost:11434"
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Resolve valid Fernet key
resolved_fernet_key: str = ""
candidate_key = settings.FERNET_KEY or settings.SECRET_FERNET_KEY

if candidate_key:
    try:
        Fernet(candidate_key.encode("utf-8"))
        resolved_fernet_key = candidate_key
    except Exception:
        resolved_fernet_key = ""

if not resolved_fernet_key:
    if settings.SECRET_KEY:
        # Derive valid key from SECRET_KEY (e.g. Render-provided generateValue)
        resolved_fernet_key = derive_fernet_key(settings.SECRET_KEY)
    else:
        # Local development fallback
        new_key = Fernet.generate_key().decode()
        resolved_fernet_key = new_key
        # Only write to local .env in local dev mode when DEMO_MODE is not set
        if not settings.DEMO_MODE:
            try:
                env_path = BASE_DIR / ".env"
                existing_content = ""
                if env_path.exists():
                    existing_content = env_path.read_text(encoding="utf-8")
                if "SECRET_FERNET_KEY" not in existing_content:
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\nSECRET_FERNET_KEY={new_key}\n")
                else:
                    lines = existing_content.splitlines()
                    updated = []
                    for line in lines:
                        if line.startswith("SECRET_FERNET_KEY="):
                            updated.append(f"SECRET_FERNET_KEY={new_key}")
                        else:
                            updated.append(line)
                    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
            except Exception as e:
                print(f"[Config] Notice: unable to write .env ({e})")

settings.SECRET_FERNET_KEY = resolved_fernet_key
settings.FERNET_KEY = resolved_fernet_key

