import json
import os
import stat

import pytest

from garmcp.users import UserError, UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(path=tmp_path / "users.json", data_dir=tmp_path / "users")


def test_create_and_verify(store):
    store.create("alice", "motdepasse123")
    assert store.verify("alice", "motdepasse123")
    assert not store.verify("alice", "mauvais-mot-de-passe")
    assert not store.verify("bob", "motdepasse123")


def test_create_duplicate_raises(store):
    store.create("alice", "motdepasse123")
    with pytest.raises(UserError):
        store.create("alice", "autre-mot-de-passe")


@pytest.mark.parametrize("username", ["", "a/b", "../evil", "x" * 65, "espace ici", None])
def test_create_invalid_username_raises(store, username):
    with pytest.raises(UserError):
        store.create(username, "motdepasse123")


@pytest.mark.parametrize("password", ["", "court", None])
def test_create_short_password_raises(store, password):
    with pytest.raises(UserError):
        store.create("alice", password)


def test_password_not_stored_in_plaintext(store):
    store.create("alice", "motdepasse123")
    raw = store.path.read_text(encoding="utf-8")
    assert "motdepasse123" not in raw
    data = json.loads(raw)
    assert data["users"]["alice"]["password"].startswith("pbkdf2_sha256$")


def test_users_file_permissions(store):
    store.create("alice", "motdepasse123")
    mode = stat.S_IMODE(os.stat(store.path).st_mode)
    assert mode == 0o600
    dir_mode = stat.S_IMODE(os.stat(store.path.parent).st_mode)
    assert dir_mode == 0o700


def test_persistence_across_instances(tmp_path):
    store = UserStore(path=tmp_path / "users.json", data_dir=tmp_path / "users")
    store.create("alice", "motdepasse123")
    token = store.create_session("alice")
    reloaded = UserStore(path=tmp_path / "users.json", data_dir=tmp_path / "users")
    assert reloaded.verify("alice", "motdepasse123")
    assert reloaded.resolve_session(token) == "alice"
    assert reloaded.list_users() == ["alice"]


def test_sessions(store):
    store.create("alice", "motdepasse123")
    store.create("bob", "motdepasse456")
    token_a = store.create_session("alice")
    token_b = store.create_session("bob")
    assert store.resolve_session(token_a) == "alice"
    assert store.resolve_session(token_b) == "bob"
    assert store.resolve_session("inconnu") is None
    assert store.resolve_session("") is None
    assert store.session_count("alice") == 1
    assert store.revoke_session(token_a)
    assert not store.revoke_session(token_a)
    assert store.resolve_session(token_a) is None
    assert store.resolve_session(token_b) == "bob"
    store.revoke_user_sessions("bob")
    assert store.resolve_session(token_b) is None
    assert store.session_count("bob") == 0


def test_create_session_unknown_user_raises(store):
    with pytest.raises(UserError):
        store.create_session("inconnu")


def test_delete_removes_account_sessions_and_garmin_dir(store):
    store.create("alice", "motdepasse123")
    token = store.create_session("alice")
    garmin_dir = store.data_dir / "alice"
    garmin_dir.mkdir(parents=True)
    (garmin_dir / "garmin_tokens.json").write_text("{}")
    assert store.garmin_connected("alice")
    store.delete("alice")
    assert not store.exists("alice")
    assert store.resolve_session(token) is None
    assert not garmin_dir.exists()
    assert not store.garmin_connected("alice")
    with pytest.raises(UserError):
        store.delete("alice")


def test_token_store_for_is_per_user(store):
    store.create("alice", "motdepasse123")
    store.create("bob", "motdepasse456")
    store_a = store.token_store_for("alice")
    store_b = store.token_store_for("bob")
    assert store_a.token_path != store_b.token_path
    assert store_a.token_path.parent == store.data_dir / "alice"
    assert store_b.token_path.parent == store.data_dir / "bob"
    assert not store.garmin_connected("alice")
    store_a.ensure_dir()
    store_a.token_path.write_text("{}")
    assert store.garmin_connected("alice")
    assert not store.garmin_connected("bob")


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMCP_TOKEN_DIR", str(tmp_path / "root"))
    monkeypatch.setenv("GARMCP_USERS_FILE", str(tmp_path / "custom" / "accounts.json"))
    monkeypatch.setenv("GARMCP_USERS_DIR", str(tmp_path / "custom" / "per-user"))
    store = UserStore()
    assert store.path == tmp_path / "custom" / "accounts.json"
    assert store.data_dir == tmp_path / "custom" / "per-user"


def test_env_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMCP_TOKEN_DIR", str(tmp_path / "root"))
    monkeypatch.delenv("GARMCP_USERS_FILE", raising=False)
    monkeypatch.delenv("GARMCP_USERS_DIR", raising=False)
    store = UserStore()
    assert store.path == tmp_path / "root" / "users.json"
    assert store.data_dir == tmp_path / "root" / "users"


def test_corrupted_file_resets(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("pas du json{")
    store = UserStore(path=path, data_dir=tmp_path / "users")
    assert store.list_users() == []
    store.create("alice", "motdepasse123")
    assert store.verify("alice", "motdepasse123")
