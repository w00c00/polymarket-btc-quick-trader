import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from auth import UserStore  # noqa: E402


def test_register_login_and_session(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.register("alice", "very-secret-password")
    token = store.login("alice", "very-secret-password")
    assert store.user_for_token(token) == "alice"
    store.logout(token)
    assert store.user_for_token(token) is None


def test_reject_duplicate_user(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.register("bob", "very-secret-password")
    try:
        store.register("bob", "very-secret-password")
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate user should fail")
