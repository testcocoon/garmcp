import logging

from garmcp import logging as garmcp_logging


def test_defaults_to_stderr_warning(monkeypatch):
    monkeypatch.delenv("GARMCP_LOG", raising=False)
    monkeypatch.delenv("GARMCP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("GARMCP_VERBOSE", raising=False)
    logger = garmcp_logging.get_logger("test.stderr")
    assert logger.level == logging.WARNING
    assert any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers
    )


def test_verbose_forces_debug(monkeypatch):
    monkeypatch.setenv("GARMCP_VERBOSE", "1")
    logger = garmcp_logging.get_logger("test.verbose")
    assert logger.level == logging.DEBUG


def test_log_level_env(monkeypatch):
    monkeypatch.setenv("GARMCP_LOG_LEVEL", "INFO")
    monkeypatch.delenv("GARMCP_VERBOSE", raising=False)
    logger = garmcp_logging.get_logger("test.level")
    assert logger.level == logging.INFO


def test_invalid_level_falls_back_to_warning(monkeypatch):
    monkeypatch.setenv("GARMCP_LOG_LEVEL", "PAS_UN_NIVEAU")
    monkeypatch.delenv("GARMCP_VERBOSE", raising=False)
    logger = garmcp_logging.get_logger("test.invalid")
    assert logger.level == logging.WARNING


def test_invalid_destination_falls_back_to_stderr(monkeypatch):
    monkeypatch.setenv("GARMCP_LOG", "nulle_part")
    logger = garmcp_logging.get_logger("test.destination")
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_debug_writes_to_stderr(monkeypatch, capsys):
    monkeypatch.setenv("GARMCP_VERBOSE", "1")
    logger = garmcp_logging.get_logger("test.write")
    logger.debug("message de test %s", 42)
    captured = capsys.readouterr()
    assert "message de test 42" in captured.err


def test_syslog_handler_selected(monkeypatch):
    monkeypatch.setenv("GARMCP_LOG", "syslog")
    import logging.handlers

    logger = garmcp_logging.get_logger("test.syslog")
    has_syslog = any(
        isinstance(h, logging.handlers.SysLogHandler) for h in logger.handlers
    )
    assert has_syslog or not __import__("os").path.exists("/dev/log")


def _reset_dependency_loggers():
    import logging as _logging

    for name in ("garminconnect", "garth", "urllib3", "requests"):
        dep = _logging.getLogger(name)
        for h in list(dep.handlers):
            if getattr(h, "_garmcp_dependency", False):
                dep.removeHandler(h)
        dep.setLevel(_logging.NOTSET)
    garmcp_logging.LOGGERS.clear()
    for name in list(garmcp_logging.LOGGERS):
        _logging.getLogger(name).handlers.clear()


def test_debug_traces_connection_requests(monkeypatch):
    _reset_dependency_loggers()
    monkeypatch.setenv("GARMCP_VERBOSE", "1")
    garmcp_logging.get_logger("garmcp")
    for name in ("garminconnect", "garth", "urllib3", "requests"):
        dep = logging.getLogger(name)
        assert dep.level == logging.DEBUG, f"{name} doit être en DEBUG"
        assert any(
            getattr(h, "_garmcp_dependency", False) for h in dep.handlers
        ), f"{name} doit avoir un handler garmcp"


def test_sensitive_headers_redacted(monkeypatch, capsys):
    _reset_dependency_loggers()
    monkeypatch.setenv("GARMCP_VERBOSE", "1")
    garmcp_logging.get_logger("garmcp")
    requests_log = logging.getLogger("requests")
    requests_log.debug(
        "POST /login Authorization: Bearer super-secret Cookie: SESSIONID=xyz123"
    )
    captured = capsys.readouterr()
    assert "super-secret" not in captured.err
    assert "xyz123" not in captured.err
    assert "<REDACTÉ>" in captured.err


def test_mfa_code_redacted(monkeypatch, capsys):
    _reset_dependency_loggers()
    monkeypatch.setenv("GARMCP_VERBOSE", "1")
    garmcp_logging.get_logger("garmcp")
    requests_log = logging.getLogger("requests")
    requests_log.debug("POST /mfa/verify mfaVerificationCode=987654")
    captured = capsys.readouterr()
    assert "987654" not in captured.err


def test_no_dependency_logging_when_not_debug(monkeypatch):
    _reset_dependency_loggers()
    monkeypatch.delenv("GARMCP_VERBOSE", raising=False)
    monkeypatch.setenv("GARMCP_LOG_LEVEL", "WARNING")
    garmcp_logging.get_logger("garmcp.quiet")
    dep = logging.getLogger("garminconnect")
    handlers = [h for h in dep.handlers if getattr(h, "_garmcp_dependency", False)]
    assert not handlers
