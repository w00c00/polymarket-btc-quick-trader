import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from vault import derive_key, VaultStore  # noqa: E402


def blob_for(password, payload):
    import base64
    import os

    salt = os.urandom(16)
    nonce = os.urandom(12)
    iterations = 1000
    key = derive_key(password, salt, iterations)
    ciphertext = AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), b"poly-vps-vault-v1")
    return {
        "version": 1,
        "kdf": "PBKDF2-SHA256",
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }


def test_vault_isolated_by_user(tmp_path, monkeypatch):
    monkeypatch.setenv("POLY_VPS_USERS_DIR", str(tmp_path / "users"))
    store = VaultStore(tmp_path / "legacy.json")
    store.save_encrypted_blob(blob_for("password-one", {"priv_key": "one"}), "alice")
    store.save_encrypted_blob(blob_for("password-two", {"priv_key": "two"}), "bob")

    store.unlock("password-one", "alice")
    store.unlock("password-two", "bob")

    assert store.credentials("alice")["priv_key"] == "one"
    assert store.credentials("bob")["priv_key"] == "two"
    assert store.status("alice")["unlocked"] is True
    store.lock("alice")
    assert store.status("alice")["unlocked"] is False
    assert store.status("bob")["unlocked"] is True
