import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


DEFAULT_VAULT_PATH = Path(os.environ.get("POLY_VPS_VAULT_PATH", "data/encrypted_vault.json"))


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase.encode("utf-8"))


class VaultStore:
    def __init__(self, path: Path = DEFAULT_VAULT_PATH):
        self.path = path
        self.unlocked_credentials = None

    def status(self):
        return {
            "exists": self.path.exists(),
            "unlocked": self.unlocked_credentials is not None,
            "path": str(self.path),
        }

    def save_encrypted_blob(self, blob: dict):
        required = {"version", "kdf", "salt", "nonce", "ciphertext"}
        missing = required - set(blob)
        if missing:
            raise ValueError(f"加密凭证缺少字段: {', '.join(sorted(missing))}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.path)

    def load_encrypted_blob(self):
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def unlock(self, passphrase: str):
        blob = self.load_encrypted_blob()
        if not blob:
            raise ValueError("VPS 上还没有加密凭证。")
        iterations = int(blob.get("iterations") or 250000)
        key = derive_key(passphrase, b64d(blob["salt"]), iterations)
        plaintext = AESGCM(key).decrypt(b64d(blob["nonce"]), b64d(blob["ciphertext"]), b"poly-vps-vault-v1")
        credentials = json.loads(plaintext.decode("utf-8"))
        self.unlocked_credentials = credentials
        return {key: bool(credentials.get(key)) for key in credentials}

    def lock(self):
        self.unlocked_credentials = None

    def credentials(self):
        if not self.unlocked_credentials:
            raise ValueError("凭证未解锁。")
        return self.unlocked_credentials
