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
