import json
from pathlib import Path

import pytest

from garmcp.auth import GarminAuthError, TokenStore, login


def test_login_without_credentials_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    with pytest.raises(GarminAuthError):
        login(token_store=TokenStore(tmp_path))


def test_token_store_paths(tmp_path):
    store = TokenStore(tmp_path)
    assert not store.exists()
    store.ensure_dir()
    store.token_path.write_text(json.dumps({"token": "abc"}))
    assert store.exists()
    assert store.token_path.parent == Path(tmp_path)


def test_login_uses_email_password_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    monkeypatch.setenv("GARMCP_TOKEN_DIR", str(tmp_path / "tokens"))

    class FakeGarmin:
        def __init__(self, email=None, password=None):
            self.username = email
            self.password = password
            self.token_path = None

        def login(self, tokenstore=None):
            self.token_path = tokenstore
            return None, None

    from garmcp import auth

    original = auth.Garmin
    auth.Garmin = FakeGarmin
    try:
        client = login(token_store=TokenStore(tmp_path / "store"))
        assert client.username == "user@example.com"
        assert client.token_path == str(TokenStore(tmp_path / "store").token_path)
    finally:
        auth.Garmin = original


def test_mfa_step1_requires_credentials(monkeypatch, tmp_path):
    from garmcp import auth

    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    with pytest.raises(GarminAuthError):
        auth.login_mfa_step1(None, None, {})


def test_mfa_step1_returns_session_id(monkeypatch):
    from garmcp import auth

    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")

    class FakeGarmin:
        def __init__(self, email=None, password=None, return_on_mfa=False):
            self.return_on_mfa = return_on_mfa

        def login(self, tokenstore=None):
            if self.return_on_mfa:
                return "needs_mfa", None
            return None, None

    original = auth.Garmin
    auth.Garmin = FakeGarmin
    try:
        sessions = {}
        session_id = auth.login_mfa_step1(None, None, sessions)
        assert session_id in sessions
    finally:
        auth.Garmin = original


def test_mfa_step2_unknown_session():
    from garmcp import auth

    with pytest.raises(GarminAuthError):
        auth.login_mfa_step2("inexistant", "123456", {})


def test_mfa_step2_empty_code():
    from garmcp import auth

    class FakeClient:
        pass

    with pytest.raises(GarminAuthError):
        auth.login_mfa_step2("sess", "  ", {"sess": FakeClient()})
