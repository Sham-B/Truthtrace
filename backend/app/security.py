import base64
import json
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from fastapi import Header, HTTPException, status
from backend.app.config import settings, STORAGE_DIR

# ----------------- Fernet File Encryption at Rest -----------------
def get_fernet() -> Fernet:
    return Fernet(settings.SECRET_FERNET_KEY.encode())

def encrypt_bytes(data: bytes) -> bytes:
    return get_fernet().encrypt(data)

def decrypt_bytes(encrypted_data: bytes) -> bytes:
    return get_fernet().decrypt(encrypted_data)

def save_encrypted_file(data: bytes, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = encrypt_bytes(data)
    dest_path.write_bytes(encrypted)
    return dest_path

def load_decrypted_file(file_path: Path) -> bytes:
    if not file_path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {file_path}")
    encrypted = file_path.read_bytes()
    return decrypt_bytes(encrypted)


# ----------------- Role-Based Access Control -----------------
class Role:
    OFFICER = "Officer"
    INSTITUTION = "Institution"
    AUDITOR = "Auditor"

    ALL_ROLES = [OFFICER, INSTITUTION, AUDITOR]

def get_current_role(
    x_role: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None)
) -> str:
    """
    Role is passed via X-Role or x-user-role HTTP header (defaults to Officer for seamless demo interaction).
    Valid roles: Officer, Institution, Auditor.
    """
    effective_role = x_role or x_user_role or "Officer"
    role_normalized = effective_role.strip().capitalize()
    if role_normalized not in Role.ALL_ROLES:
        # Fallback check for exact case match
        for r in Role.ALL_ROLES:
            if r.lower() == effective_role.strip().lower():
                return r
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid role '{effective_role}'. Allowed roles: {', '.join(Role.ALL_ROLES)}"
        )
    return role_normalized

def require_officer(
    x_role: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None)
) -> str:
    current = get_current_role(x_role=x_role, x_user_role=x_user_role)
    if current != Role.OFFICER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Officer role required for this action."
        )
    return current


# ----------------- Ed25519 Cryptographic Signing & Verification -----------------
ISSUER_KEYS_DIR = STORAGE_DIR / "keys"
ISSUER_KEYS_DIR.mkdir(parents=True, exist_ok=True)

# Cache for issuer private/public key pairs in memory/disk
_ISSUER_KEYPAIRS: Dict[str, Dict[str, Any]] = {}

def get_or_create_issuer_keypair(issuer_id: str) -> Dict[str, Any]:
    """
    Load or generate persistent Ed25519 keypair for a mock issuer.
    """
    if issuer_id in _ISSUER_KEYPAIRS:
        return _ISSUER_KEYPAIRS[issuer_id]

    priv_file = ISSUER_KEYS_DIR / f"{issuer_id}_priv.pem"
    pub_file = ISSUER_KEYS_DIR / f"{issuer_id}_pub.pem"

    if priv_file.exists() and pub_file.exists():
        priv_key = serialization.load_pem_private_key(priv_file.read_bytes(), password=None)
        pub_key = serialization.load_pem_public_key(pub_file.read_bytes())
    else:
        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        priv_bytes = priv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        priv_file.write_bytes(priv_bytes)
        pub_file.write_bytes(pub_bytes)

    pub_b64 = base64.b64encode(
        pub_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    ).decode("ascii")

    _ISSUER_KEYPAIRS[issuer_id] = {
        "private_key": priv_key,
        "public_key": pub_key,
        "public_key_b64": pub_b64
    }
    return _ISSUER_KEYPAIRS[issuer_id]


def sign_issuer_payload(issuer_id: str, payload_dict: dict) -> str:
    """
    Sign canonical JSON string with Ed25519 and return base64 signature.
    """
    keypair = get_or_create_issuer_keypair(issuer_id)
    canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signature = keypair["private_key"].sign(canonical_json)
    return base64.b64encode(signature).decode('ascii')


def verify_issuer_signature(issuer_id: str, payload_dict: dict, signature_b64: str) -> bool:
    """
    Verify Ed25519 signature against issuer's public key.
    """
    try:
        keypair = get_or_create_issuer_keypair(issuer_id)
        pub_key: ed25519.Ed25519PublicKey = keypair["public_key"]
        canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
        signature_bytes = base64.b64decode(signature_b64)
        pub_key.verify(signature_bytes, canonical_json)
        return True
    except Exception:
        return False
