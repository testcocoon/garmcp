"""Journalisation optionnelle de garmcp : stderr ou syslog selon la config.

Configuration via variables d'environnement :
- GARMCP_LOG : destination, "stderr" (défaut) ou "syslog"
- GARMCP_LOG_LEVEL : DEBUG, INFO, WARNING (défaut), ERROR
- GARMCP_VERBOSE : si définie (non vide), force le niveau DEBUG

En mode debug, les requêtes HTTP de connexion émises par garminconnect/garth
sont journalisées intégralement (méthode, URL, en-têtes) via les loggers des
bibliothèques, avec rédaction des en-têtes sensibles (Authorization, Cookie).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys

VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
VALID_DESTINATIONS = ("stderr", "syslog")

# Loggers des bibliothèques émettant les requêtes HTTP de connexion.
DEPENDENCY_LOGGERS = ("garminconnect", "garth", "urllib3", "requests")

# En-têtes sensibles à masquer dans les logs de requêtes : le nom est
# conservé, la valeur est intégralement remplacée jusqu'au prochain
# séparateur (virgule, point-virgule, fin de ligne).
_SENSITIVE_HEADERS = re.compile(
    r"(?i)(authorization|cookie|set-cookie|x-csrf-token|mfaverificationcode)"
    r"\s*[:=][^,;\n]*"
)


class SensitiveDataFilter(logging.Filter):
    """Masque les en-têtes et valeurs sensibles dans chaque message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE_HEADERS.sub(r"\1=<REDACTÉ>", record.msg)
        if record.args:
            record.args = tuple(
                _SENSITIVE_HEADERS.sub(r"\1=<REDACTÉ>", arg)
                if isinstance(arg, str)
                else arg
                for arg in record.args
            )
        return True


def _resolve_level() -> int:
    if os.environ.get("GARMCP_VERBOSE", "").strip():
        return logging.DEBUG
    level = os.environ.get("GARMCP_LOG_LEVEL", "WARNING").upper()
    return getattr(logging, level, logging.WARNING) if level in VALID_LEVELS else logging.WARNING


class _StderrHandler(logging.StreamHandler):
    """StreamHandler qui résout sys.stderr à chaque émission (compat pytest/capsys)."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, value) -> None:
        pass


def _build_handler(destination: str) -> logging.Handler:
    if destination == "syslog":
        return logging.handlers.SysLogHandler(address="/dev/log")
    return _StderrHandler()


def _attach_dependency_logging(handler: logging.Handler) -> None:
    """En mode debug, trace les requêtes HTTP des bibliothèques de connexion."""
    for name in DEPENDENCY_LOGGERS:
        dep = logging.getLogger(name)
        dep.setLevel(logging.DEBUG)
        if not any(
            getattr(h, "_garmcp_dependency", False) for h in dep.handlers
        ):
            handler_copy = type(handler)(**_handler_kwargs(handler))
            handler_copy.setFormatter(handler.formatter)
            handler_copy._garmcp_dependency = True  # type: ignore[attr-defined]
            handler_copy.addFilter(SensitiveDataFilter())
            dep.addHandler(handler_copy)


def _handler_kwargs(handler: logging.Handler) -> dict:
    if isinstance(handler, logging.handlers.SysLogHandler):
        return {"address": handler.address}
    return {}


def get_logger(name: str = "garmcp") -> logging.Logger:
    """Retourne un logger garmcp configuré une seule fois par nom.

    La configuration est lue au premier appel (ou si GARMCP_LOG a changé),
    ce qui permet de recharger la destination sans redémarrer les tests.
    """
    logger = logging.getLogger(name)
    destination = os.environ.get("GARMCP_LOG", "stderr").strip().lower()
    if destination not in VALID_DESTINATIONS:
        destination = "stderr"

    cache_key = f"{name}:{destination}"
    if LOGGERS.get(name) is not logger or getattr(logger, "_garmcp_dest", None) != cache_key:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        handler = _build_handler(destination)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
        level = _resolve_level()
        logger.setLevel(level)
        logger._garmcp_dest = cache_key  # type: ignore[attr-defined]
        LOGGERS[name] = logger
        if destination == "syslog" and not os.path.exists("/dev/log"):
            logger.warning("syslog demandé mais /dev/log indisponible")
        if level <= logging.DEBUG:
            _attach_dependency_logging(handler)
            logger.debug(
                "Mode debug : requêtes de connexion tracées (%s)",
                ", ".join(DEPENDENCY_LOGGERS),
            )
    return logger


LOGGERS: dict[str, logging.Logger] = {}
