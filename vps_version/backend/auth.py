import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path


DEFAULT_USERS_PATH = Path(os.environ.get("POLY_VPS_USERS_PATH", "data/users.json"))
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def password_hash(password: str, salt: bytes | None = None, iterations: int = 310000):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": iterations,
        "salt": b64(salt),
        "hash": b64(digest),
    }


def verify_password(password: str, stored: dict):
    if stored.get("algorithm") != "pbkdf2_sha256":
        return False
    candidate = password_hash(password, b64d(stored["salt"]), int(stored["iterations"]))
    return hmac.compare_digest(candidate["hash"], stored["hash"])


class UserStore:
    def __init__(self, path: Path = DEFAULT_USERS_PATH):
        self.path = path
        self.sessions = {}
        self.users = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self.users, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.path)

    def register(self, username: str, password: str):
        username = username.strip()
        if not USERNAME_PATTERN.match(username):
            raise ValueError("用户名只能使用 3-32 位字母、数字、下划线或横线。")
        if len(password) < 10:
            raise ValueError("密码至少 10 位。")
        if username in self.users:
            raise ValueError("用户名已存在。")
        self.users[username] = {
            "password": password_hash(password),
            "created_at": int(time.time()),
            "role": "admin" if not self.users else "user",
            "settings": {},
        }
        self._save()

    def login(self, username: str, password: str):
        user = self.users.get(username)
        if not user or not verify_password(password, user.get("password") or {}):
            raise ValueError("用户名或密码错误。")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {
            "username": username,
            "created_at": int(time.time()),
        }
        return token

    def logout(self, token: str):
        self.sessions.pop(token, None)

    def user_for_token(self, token: str | None):
        if not token:
            return None
        session = self.sessions.get(token)
        if not session:
            return None
        return session["username"]

    def list_users(self):
        return [
            {
                "username": username,
                "role": user.get("role", "user"),
                "created_at": user.get("created_at"),
                "settings": user.get("settings") or {},
            }
            for username, user in sorted(self.users.items())
        ]

    def is_admin(self, username: str):
        return (self.users.get(username) or {}).get("role") == "admin"

    def delete_user(self, username: str):
        if username not in self.users:
            raise ValueError("用户不存在。")
        if self.users[username].get("role") == "admin":
            admin_count = sum(1 for item in self.users.values() if item.get("role") == "admin")
            if admin_count <= 1:
                raise ValueError("不能删除最后一个管理员。")
        self.users.pop(username)
        for token, session in list(self.sessions.items()):
            if session.get("username") == username:
                self.sessions.pop(token, None)
        self._save()

    def update_settings(self, username: str, settings: dict):
        if username not in self.users:
            raise ValueError("用户不存在。")
        current = self.users[username].setdefault("settings", {})
        current.update(settings)
        self._save()
        return current

    def settings(self, username: str):
        return (self.users.get(username) or {}).get("settings") or {}
