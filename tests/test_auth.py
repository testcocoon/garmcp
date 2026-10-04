import json

import pytest

from garmcp import auth as garmcp_auth
from garmcp.auth import GarminAuthError, TokenStore, login


class FakeGarminNoMfa:
    """Client factice : connexion réussie sans 2FA."""

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.username = email
        self.password = password

    def login(self, tokenstore=None):
        return None, None


class FakeGarminMFA(FakeGarminNoMfa):
    """Client factice : Garmin exige un code 2FA envoyé par email."""

    def login(self, tokenstore=None):
        return "needs_mfa", None


def test_login_without_credentials_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    with pytest.raises(GarminAuthError):
        login(token_store=TokenStore(tmp_path))


def test_login_success_returns_client(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    original = garmcp_auth.Garmin
    garmcp_auth.Garmin = FakeGarminNoMfa
    try:
        result = login(token_store=TokenStore(tmp_path))
        assert isinstance(result, FakeGarminNoMfa)
    finally:
        garmcp_auth.Garmin = original


def test_login_mfa_pending_returns_session_id(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    original = garmcp_auth.Garmin
    garmcp_auth.Garmin = FakeGarminMFA
    try:
        sessions = {}
        result = login(
            token_store=TokenStore(tmp_path), mfa_sessions=sessions
        )
        assert isinstance(result, str)
        assert result in sessions
    finally:
        garmcp_auth.Garmin = original


def test_mfa_step2_unknown_session():
    with pytest.raises(GarminAuthError):
        garmcp_auth.login_mfa_step2("inexistant", "123456", {})


def test_mfa_step2_empty_code():
    class FakeClient:
        pass

    with pytest.raises(GarminAuthError):
        garmcp_auth.login_mfa_step2("sess", "  ", {"sess": FakeClient()})


def test_token_store_paths(tmp_path):
    store = TokenStore(tmp_path)
    assert not store.exists()
    store.ensure_dir()
    store.token_path.write_text(json.dumps({"token": "abc"}))
    assert store.exists()
    assert store.token_path.parent == tmp_path
