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
        self.unlocked_credentials = {}

    def _user_path(self, username: str | None):
        if not username:
            return self.path
        safe_username = "".join(ch for ch in username if ch.isalnum() or ch in {"_", "-"})
        return Path(os.environ.get("POLY_VPS_USERS_DIR", "data/users")) / safe_username / "encrypted_vault.json"

    def status(self, username: str | None = None):
        path = self._user_path(username)
        return {
            "exists": path.exists(),
            "unlocked": username in self.unlocked_credentials if username else bool(self.unlocked_credentials),
            "path": str(path),
        }

    def save_encrypted_blob(self, blob: dict, username: str | None = None):
        required = {"version", "kdf", "salt", "nonce", "ciphertext"}
        missing = required - set(blob)
        if missing:
            raise ValueError(f"加密凭证缺少字段: {', '.join(sorted(missing))}")
        path = self._user_path(username)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)

    def load_encrypted_blob(self, username: str | None = None):
        path = self._user_path(username)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def unlock(self, passphrase: str, username: str | None = None):
        blob = self.load_encrypted_blob(username)
        if not blob:
            raise ValueError("VPS 上还没有加密凭证。")
        iterations = int(blob.get("iterations") or 250000)
        key = derive_key(passphrase, b64d(blob["salt"]), iterations)
        plaintext = AESGCM(key).decrypt(b64d(blob["nonce"]), b64d(blob["ciphertext"]), b"poly-vps-vault-v1")
        credentials = json.loads(plaintext.decode("utf-8"))
        self.unlocked_credentials[username] = credentials
        return {key: bool(credentials.get(key)) for key in credentials}

    def lock(self, username: str | None = None):
        if username:
            self.unlocked_credentials.pop(username, None)
        else:
            self.unlocked_credentials.clear()

    def credentials(self, username: str | None = None):
        credentials = self.unlocked_credentials.get(username)
        if not credentials:
            raise ValueError("凭证未解锁。")
        return credentials
