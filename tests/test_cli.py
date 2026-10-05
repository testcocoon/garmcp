
from garmcp import cli as garmcp_cli


def test_parser_login_flag():
    parser = garmcp_cli.build_parser()
    args = parser.parse_args(["--login"])
    assert args.login is True


def test_parser_default_no_login():
    parser = garmcp_cli.build_parser()
    args = parser.parse_args([])
    assert args.login is False


def test_main_login_dispatch(monkeypatch):
    called = {}
    monkeypatch.setattr(garmcp_cli, "run_login", lambda: called.setdefault("ok", 1))
    assert garmcp_cli.main(["--login"]) == 1
    assert called == {"ok": 1}


def test_main_without_login_starts_server(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "garmcp.server.main", lambda: called.setdefault("served", None)
    )
    garmcp_cli.main([])
    assert "served" in called


def test_run_login_failure_returns_1(monkeypatch, capsys):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")

    from garmcp import auth

    def fake_login(email=None, password=None, mfa_sessions=None):
        raise auth.GarminAuthError("identifiants invalides")

    monkeypatch.setattr(garmcp_cli, "login", fake_login, raising=False)
    assert garmcp_cli.run_login() == 1
    captured = capsys.readouterr()
    assert "Échec de connexion" in captured.err


def test_run_login_mfa_flow(monkeypatch, capsys):
    monkeypatch.setenv("GARMIN_EMAIL", "user@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")


    class FakeClient:
        pass

    def fake_login(email=None, password=None, mfa_sessions=None):
        return "sess123"

    def fake_step2(session_id, code, sessions):
        assert session_id == "sess123"
        assert code == "654321"
        return FakeClient()

    monkeypatch.setattr(garmcp_cli, "login", fake_login, raising=False)
    monkeypatch.setattr(garmcp_cli, "login_mfa_step2", fake_step2)

    class FakeStore:
        token_path = __import__("pathlib").Path("/tmp/fake-token.json")

        def exists(self):
            return True

    monkeypatch.setattr(garmcp_cli, "TokenStore", lambda: FakeStore())
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "654321")

    assert garmcp_cli.run_login() == 0
    captured = capsys.readouterr()
    assert "code à 6 chiffres" in captured.out
    assert "Token de connexion stocké" in captured.out


def test_parser_http_options():
    parser = garmcp_cli.build_parser()
    args = parser.parse_args(["--http", "--port", "9000", "--host", "0.0.0.0"])
    assert args.http is True
    assert args.port == 9000
    assert args.host == "0.0.0.0"


def test_parser_http_defaults(monkeypatch):
    monkeypatch.delenv("GARMCP_HOST", raising=False)
    monkeypatch.delenv("GARMCP_PORT", raising=False)
    parser = garmcp_cli.build_parser()
    args = parser.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_main_http_dispatch(monkeypatch):
    called = {}

    class FakeApp:
        def add_middleware(self, mw):
            called["middleware"] = mw

    class FakeMCP:
        def streamable_http_app(self, **kwargs):
            called.update(kwargs)
            return FakeApp()

    import garmcp.server as server_mod

    monkeypatch.setattr(server_mod, "mcp", FakeMCP())
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: called.update(kw))
    garmcp_cli.main(["--http", "--port", "8123"])
    assert called["streamable_http_path"] == "/mcp"
    assert called["port"] == 8123
    assert called["host"] == "127.0.0.1"


def test_parser_sse_flag():
    parser = garmcp_cli.build_parser()
    args = parser.parse_args(["--sse", "--port", "9001"])
    assert args.sse is True
    assert args.port == 9001


def test_main_sse_dispatch(monkeypatch):
    called = {}

    class FakeApp:
        def add_middleware(self, mw):
            called["middleware"] = mw

    class FakeMCP:
        def sse_app(self, **kwargs):
            called.update(kwargs)
            return FakeApp()

    import garmcp.server as server_mod

    monkeypatch.setattr(server_mod, "mcp", FakeMCP())
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: called.update(kw))
    garmcp_cli.main(["--sse", "--port", "9001"])
    assert called["sse_path"] == "/sse"
    assert called["message_path"] == "/messages/"
    assert called["port"] == 9001


def test_parser_base_url_default(monkeypatch):
    monkeypatch.delenv("GARMCP_BASE_URL", raising=False)
    parser = garmcp_cli.build_parser()
    args = parser.parse_args(["--http"])
    assert args.base_url == ""


def test_parser_base_url_from_env(monkeypatch):
    monkeypatch.setenv("GARMCP_BASE_URL", "baseurl")
    parser = garmcp_cli.build_parser()
    args = parser.parse_args(["--http"])
    assert args.base_url == "baseurl"


def test_main_http_base_url_prefix(monkeypatch):
    called = {}

    class FakeApp:
        def add_middleware(self, mw):
            pass

    class FakeMCP:
        def streamable_http_app(self, **kwargs):
            called.update(kwargs)
            return FakeApp()

    import garmcp.server as server_mod

    monkeypatch.setattr(server_mod, "mcp", FakeMCP())
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)
    garmcp_cli.main(["--http", "--base-url", "baseurl"])
    assert called["streamable_http_path"] == "/baseurl/mcp"


def test_main_sse_base_url_prefix(monkeypatch):
    called = {}

    class FakeApp:
        def add_middleware(self, mw):
            pass

    class FakeMCP:
        def sse_app(self, **kwargs):
            called.update(kwargs)
            return FakeApp()

    import garmcp.server as server_mod

    monkeypatch.setattr(server_mod, "mcp", FakeMCP())
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)
    garmcp_cli.main(["--sse", "--base-url", "/baseurl/"])
    assert called["sse_path"] == "/baseurl/sse"
    assert called["message_path"] == "/baseurl/messages/"
