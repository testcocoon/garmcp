"""Journalisation optionnelle de garmcp : stderr ou syslog selon la config.

Configuration via variables d'environnement :
- GARMCP_LOG : destination, "stderr" (défaut) ou "syslog"
- GARMCP_LOG_LEVEL : DEBUG, INFO, WARNING (défaut), ERROR
- GARMCP_VERBOSE : si définie (non vide), force le niveau DEBUG
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

LOGGERS: dict[str, logging.Logger] = {}

VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
VALID_DESTINATIONS = ("stderr", "syslog")


def _resolve_level() -> int:
    if os.environ.get("GARMCP_VERBOSE", "").strip():
        return logging.DEBUG
    level = os.environ.get("GARMCP_LOG_LEVEL", "WARNING").upper()
    return getattr(logging, level, logging.WARNING) if level in VALID_LEVELS else logging.WARNING


def _build_handler(destination: str) -> logging.Handler:
    if destination == "syslog":
        return logging.handlers.SysLogHandler(address="/dev/log")
    return logging.StreamHandler(sys.stderr)


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
        logger.addHandler(handler)
        logger.setLevel(_resolve_level())
        logger._garmcp_dest = cache_key  # type: ignore[attr-defined]
        LOGGERS[name] = logger
        if destination == "syslog" and not os.path.exists("/dev/log"):
            logger.warning("syslog demandé mais /dev/log indisponible")
    return logger
