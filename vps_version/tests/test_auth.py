import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from auth import UserStore  # noqa: E402


def test_register_login_and_session(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.register("alice", "very-secret-password")
    assert store.public_user("alice")["status"] == "pending"
    try:
        store.login("alice", "very-secret-password")
    except ValueError as exc:
        assert "审批" in str(exc)
    else:
        raise AssertionError("pending user should not login")
    store.approve_user("alice")
    token = store.login("alice", "very-secret-password")
    assert store.user_for_token(token) == "alice"
    assert store.public_user("alice")["role"] == "user"
    assert store.public_user("alice")["status"] == "approved"
    store.logout(token)
    assert store.user_for_token(token) is None


def test_default_admin_requires_password_change(tmp_path):
    store = UserStore(tmp_path / "users.json")
    token = store.login("poly", "123456")
    assert store.user_for_token(token) == "poly"
    admin = store.public_user("poly")
    assert admin["role"] == "admin"
    assert admin["password_change_required"] is True
    store.change_password("poly", "123456", "abcdef")
    assert store.public_user("poly")["password_change_required"] is False


def test_reject_duplicate_user(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.register("bob", "very-secret-password")
    try:
        store.register("bob", "very-secret-password")
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("duplicate user should fail")
