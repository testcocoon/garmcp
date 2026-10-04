
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
