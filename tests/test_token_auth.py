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
