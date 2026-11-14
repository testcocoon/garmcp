import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from garmcp import server
from garmcp.auth import TokenStore
from garmcp.users import UserStore


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "user_create",
        "user_login",
        "user_logout",
        "user_delete",
        "users_list",
        "user_status",
        "garmin_login",
        "garmin_mfa_verify",
        "garmin_logout",
        "garmin_status",
        "garmin_daily_summary",
        "garmin_activities",
        "garmin_activities_between",
        "garmin_activity",
        "garmin_sleep",
        "garmin_steps",
        "garmin_heart_rate",
        "garmin_body_battery",
        "garmin_stress",
        "garmin_hrv",
        "garmin_weight",
        "garmin_profile",
        "garmin_devices",
        "garmin_scheduled_workouts",
        "garmin_next_scheduled_workout",
        "garmin_scheduled_workout",
        "garmin_challenges",
        "garmin_badge_challenges",
        "garmin_available_badge_challenges",
        "garmin_non_completed_badge_challenges",
        "garmin_inprogress_virtual_challenges",
    }
    assert expected.issubset(names)


def test_json_serialization():
    assert server._json({"a": 1}) == json.dumps({"a": 1}, ensure_ascii=False, indent=2)
    assert server._json(None) == "{}"
    assert server._json("plain text") == "plain text"


def test_days_ago():
    assert server._days_ago(0) == date.today().isoformat()
    assert server._days_ago(1) == (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def user_store(tmp_path, monkeypatch):
    store = UserStore(path=tmp_path / "users.json", data_dir=tmp_path / "users")
    monkeypatch.setattr(server, "user_store", store)
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(server, "_clients", {})
    monkeypatch.setattr(server, "_active_user", None)
    monkeypatch.setattr(server, "_mfa_sessions", {})
    return store


@pytest.fixture
def http_session():
    """Simule une requête HTTP authentifiée par token de session utilisateur."""

    def _set(token, username):
        return server._current_session_var.set((token, username))

    return _set


def test_user_create(user_store):
    result = server.user_create("alice", "motdepasse123")
    assert "créé" in result
    assert user_store.exists("alice")
    assert "Échec" in server.user_create("alice", "motdepasse123")
    assert "Échec" in server.user_create("bad/name", "motdepasse123")
    assert "Échec" in server.user_create("bob", "court")


def test_user_login_wrong_password(user_store):
    user_store.create("alice", "motdepasse123")
    assert "Échec" in server.user_login("alice", "mauvais-mot-de-passe")
    assert "Échec" in server.user_login("inconnu", "motdepasse123")
    assert server._active_user is None


def test_user_login_stdio_sets_active_user(user_store):
    user_store.create("alice", "motdepasse123")
    result = server.user_login("alice", "motdepasse123")
    assert "Token de session" in result
    assert "alice" in result
    assert user_store.session_count("alice") == 1
    assert server._active_user == "alice"
    assert server._resolve_user() == "alice"


def test_user_login_http_does_not_set_active_user(user_store):
    user_store.create("alice", "motdepasse123")
    reset_http = server._http_request_var.set(True)
    reset_sess = server._current_session_var.set(("bootstrap", None))
    try:
        result = server.user_login("alice", "motdepasse123")
    finally:
        server._current_session_var.reset(reset_sess)
        server._http_request_var.reset(reset_http)
    assert "Token de session" in result
    assert server._active_user is None
    assert user_store.session_count("alice") == 1


def test_user_logout_stdio_revokes_active_user(user_store):
    user_store.create("alice", "motdepasse123")
    user_store.create_session("alice")
    server._active_user = "alice"
    server._clients["alice"] = object()
    result = server.user_logout()
    assert "alice" in result
    assert server._active_user is None
    assert "alice" not in server._clients
    assert user_store.session_count("alice") == 0


def test_user_logout_http_revokes_bearer_token(user_store, http_session):
    user_store.create("alice", "motdepasse123")
    token = user_store.create_session("alice")
    reset = http_session(token, "alice")
    try:
        result = server.user_logout()
    finally:
        server._current_session_var.reset(reset)
    assert "alice" in result
    assert user_store.resolve_session(token) is None


def test_user_logout_without_session(user_store):
    assert "Aucune session" in server.user_logout()


def test_user_delete(user_store):
    user_store.create("alice", "motdepasse123")
    user_store.create_session("alice")
    user_store.token_store_for("alice").ensure_dir()
    server._clients["alice"] = object()
    server._mfa_sessions["alice"] = {"s": object()}
    server._active_user = "alice"
    assert "Échec" in server.user_delete("alice", "mauvais-mot-de-passe")
    result = server.user_delete("alice", "motdepasse123")
    assert "supprimé" in result
    assert not user_store.exists("alice")
    assert "alice" not in server._clients
    assert "alice" not in server._mfa_sessions
    assert server._active_user is None
    assert not (user_store.data_dir / "alice").exists()


def test_users_list(user_store):
    user_store.create("bob", "motdepasse456")
    user_store.create("alice", "motdepasse123")
    assert json.loads(server.users_list()) == ["alice", "bob"]


def test_user_status_with_user(user_store, http_session):
    user_store.create("alice", "motdepasse123")
    user_store.create_session("alice")
    reset = http_session("tok", "alice")
    try:
        status = json.loads(server.user_status())
    finally:
        server._current_session_var.reset(reset)
    assert status == {"user": "alice", "garmin_connected": False, "sessions": 1}


def test_user_status_without_user(user_store, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "TokenStore", lambda: TokenStore(tmp_path))
    status = json.loads(server.user_status())
    assert status == {"user": None, "garmin_connected": False}


def test_get_client_per_user_uses_user_token_store(user_store, http_session, monkeypatch):
    user_store.create("alice", "motdepasse123")
    captured = {}

    class FakeGarmin:
        pass

    def fake_login(email=None, password=None, token_store=None, mfa_sessions=None):
        captured["token_store"] = token_store
        return FakeGarmin()

    monkeypatch.setattr(server, "login", fake_login)
    monkeypatch.setattr(server, "GarminClient", lambda c: c)
    reset = http_session("tok", "alice")
    try:
        client = server.get_client()
        assert server.get_client() is client
    finally:
        server._current_session_var.reset(reset)
    assert captured["token_store"].token_path == (
        user_store.data_dir / "alice" / "garmin_tokens.json"
    )
    assert "alice" in server._clients


def test_garmin_login_binds_user_token_store(user_store, http_session, monkeypatch):
    user_store.create("alice", "motdepasse123")
    captured = {}

    class FakeGarmin:
        def get_summary(self, day):
            return {"fullName": "Alice"}

    def fake_login(email=None, password=None, token_store=None, mfa_sessions=None):
        captured["token_store"] = token_store
        captured["mfa_sessions"] = mfa_sessions
        return FakeGarmin()

    monkeypatch.setattr(server, "login", fake_login)
    monkeypatch.setattr(server, "GarminClient", lambda c: c)
    reset = http_session("tok", "alice")
    try:
        result = server.garmin_login("alice@example.com", "secret-garmin")
    finally:
        server._current_session_var.reset(reset)
    assert "succès" in result and "alice" in result
    assert captured["token_store"].token_path == (
        user_store.data_dir / "alice" / "garmin_tokens.json"
    )
    assert captured["mfa_sessions"] is server._mfa_sessions["alice"]
    assert "alice" in server._clients


def test_garmin_login_mfa_pending_per_user(user_store, http_session, monkeypatch):
    user_store.create("alice", "motdepasse123")
    monkeypatch.setattr(server, "login", lambda *a, **k: "sess-123")
    reset = http_session("tok", "alice")
    try:
        result = server.garmin_login("alice@example.com", "secret-garmin")
    finally:
        server._current_session_var.reset(reset)
    assert "sess-123" in result
    assert "garmin_mfa_verify" in result


def test_garmin_mfa_verify_uses_user_store(user_store, http_session, monkeypatch):
    user_store.create("alice", "motdepasse123")
    captured = {}

    class FakeGarmin:
        def get_summary(self, day):
            return {"fullName": "Alice"}

    def fake_step2(session_id, code, sessions, token_store=None):
        captured["sessions"] = sessions
        captured["token_store"] = token_store
        return FakeGarmin()

    monkeypatch.setattr(server, "login_mfa_step2", fake_step2)
    monkeypatch.setattr(server, "GarminClient", lambda c: c)
    server._mfa_sessions["alice"] = {"sess1": object()}
    reset = http_session("tok", "alice")
    try:
        result = server.garmin_mfa_verify("sess1", "123456")
    finally:
        server._current_session_var.reset(reset)
    assert "MFA validée" in result
    assert captured["token_store"].token_path.parent == user_store.data_dir / "alice"
    assert captured["sessions"] is server._mfa_sessions["alice"]


def test_garmin_logout_per_user(user_store, http_session):
    user_store.create("alice", "motdepasse123")
    token_store = user_store.token_store_for("alice")
    token_store.ensure_dir()
    token_store.token_path.write_text("{}")
    server._clients["alice"] = object()
    reset = http_session("tok", "alice")
    try:
        result = server.garmin_logout()
    finally:
        server._current_session_var.reset(reset)
    assert "alice" in result
    assert "alice" not in server._clients
    assert not token_store.exists()


def test_garmin_status_per_user(user_store, http_session):
    user_store.create("alice", "motdepasse123")

    class FakeClient:
        def get_summary(self, day):
            return {"fullName": "Alice A."}

    server._clients["alice"] = FakeClient()
    reset = http_session("tok", "alice")
    try:
        result = server.garmin_status()
    finally:
        server._current_session_var.reset(reset)
    assert "Alice A." in result
    assert "alice" in result


@pytest.mark.asyncio
async def test_user_context_middleware_resolves_bearer_token(user_store):
    user_store.create("alice", "motdepasse123")
    token = user_store.create_session("alice")

    ctx = SimpleNamespace(
        request=SimpleNamespace(headers={"authorization": f"Bearer {token}"})
    )

    seen = {}

    async def call_next(ctx):
        seen["user"] = server._resolve_user()
        seen["http"] = server._http_request_var.get()
        return "ok"

    result = await server._user_context_middleware(ctx, call_next)
    assert result == "ok"
    assert seen == {"user": "alice", "http": True}
    assert server._current_session_var.get() is None
    assert server._resolve_user() is None


@pytest.mark.asyncio
async def test_user_context_middleware_unknown_token(user_store):
    ctx = SimpleNamespace(
        request=SimpleNamespace(headers={"authorization": "Bearer inconnu"})
    )

    async def call_next(ctx):
        return server._resolve_user()

    assert await server._user_context_middleware(ctx, call_next) is None


@pytest.mark.asyncio
async def test_user_context_middleware_stdio(user_store):
    ctx = SimpleNamespace(request=None)

    async def call_next(ctx):
        return (server._resolve_user(), server._http_request_var.get())

    assert await server._user_context_middleware(ctx, call_next) == (None, False)
