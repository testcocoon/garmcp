import os

import pytest

from garmcp import token_auth as ta


def test_no_token_configured(monkeypatch):
    monkeypatch.delenv("GARMCP_TOKEN", raising=False)
    assert ta.get_token() is None


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("GARMCP_TOKEN", "mon-secret")
    assert ta.get_token() == "mon-secret"


def test_whitespace_token_treated_as_unset(monkeypatch):
    monkeypatch.setenv("GARMCP_TOKEN", "   ")
    assert ta.get_token() is None


@pytest.mark.asyncio
async def test_middleware_rejects_missing_token(monkeypatch):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")

    from starlette.testclient import TestClient

    class DummyApp:
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    app = ta.TokenAuthMiddleware(DummyApp())
    client = TestClient(app)
    r = client.post("/mcp")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_middleware_accepts_valid_token(monkeypatch):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")

    from starlette.testclient import TestClient

    class DummyApp:
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    app = ta.TokenAuthMiddleware(DummyApp())
    client = TestClient(app)
    r = client.post("/mcp", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


def test_middleware_rejects_wrong_token(monkeypatch):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")

    from starlette.testclient import TestClient

    class DummyApp:
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    app = ta.TokenAuthMiddleware(DummyApp())
    client = TestClient(app)
    r = client.post("/mcp", headers={"Authorization": "Bearer mauvais"})
    assert r.status_code == 401


def test_middleware_disabled_without_token(monkeypatch):
    pytest.importorskip("starlette")
    monkeypatch.delenv("GARMCP_TOKEN", raising=False)

    from starlette.testclient import TestClient

    class DummyApp:
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    app = ta.TokenAuthMiddleware(DummyApp())
    client = TestClient(app)
    r = client.post("/mcp")
    assert r.status_code == 200
    assert os.environ.get("GARMCP_TOKEN") is None


def _dummy_app():
    class DummyApp:
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    return DummyApp()


def _make_user_session(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMCP_TOKEN_DIR", str(tmp_path))
    monkeypatch.delenv("GARMCP_USERS_FILE", raising=False)
    monkeypatch.delenv("GARMCP_USERS_DIR", raising=False)
    from garmcp.users import UserStore

    store = UserStore()
    store.create("alice", "motdepasse123")
    return store.create_session("alice")


def test_middleware_accepts_user_session_token(monkeypatch, tmp_path):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")
    session_token = _make_user_session(monkeypatch, tmp_path)

    from starlette.testclient import TestClient

    app = ta.TokenAuthMiddleware(_dummy_app())
    client = TestClient(app)
    r = client.post("/mcp", headers={"Authorization": f"Bearer {session_token}"})
    assert r.status_code == 200


def test_middleware_rejects_unknown_token_when_users_exist(monkeypatch, tmp_path):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")
    _make_user_session(monkeypatch, tmp_path)

    from starlette.testclient import TestClient

    app = ta.TokenAuthMiddleware(_dummy_app())
    client = TestClient(app)
    r = client.post("/mcp", headers={"Authorization": "Bearer mauvais"})
    assert r.status_code == 401


def test_middleware_rejects_revoked_user_session(monkeypatch, tmp_path):
    pytest.importorskip("starlette")
    monkeypatch.setenv("GARMCP_TOKEN", "secret")
    session_token = _make_user_session(monkeypatch, tmp_path)

    from garmcp.users import UserStore

    UserStore().revoke_session(session_token)

    from starlette.testclient import TestClient

    app = ta.TokenAuthMiddleware(_dummy_app())
    client = TestClient(app)
    r = client.post("/mcp", headers={"Authorization": f"Bearer {session_token}"})
    assert r.status_code == 401


def test_is_authorized_static_token_still_works(monkeypatch, tmp_path):
    import hashlib

    monkeypatch.setenv("GARMCP_TOKEN", "secret")
    _make_user_session(monkeypatch, tmp_path)
    expected_hash = hashlib.sha256(b"secret").hexdigest()
    assert ta._is_authorized("secret", expected_hash)
    assert not ta._is_authorized("autre", expected_hash)
