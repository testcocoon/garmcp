"""Authentification du serveur HTTP garmcp par token statique (Bearer).

Configuration :
- GARMCP_TOKEN : le secret partagé exigé dans l'en-tête Authorization
  (« Bearer <token> ») pour les transports HTTP/SSE. Vide/absent : aucune
  authentification (usage local stdio).

Génération d'un token :
    python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

from __future__ import annotations

import hashlib
import hmac
import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

TOKEN_ENV = "GARMCP_TOKEN"


def get_token() -> str | None:
    """Retourne le token statique configuré, ou None si désactivé."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    return token or None


def _matches(received: str, expected_hash: str) -> bool:
    """Comparaison en temps constant de hachés pour éviter toute fuite."""
    received_hash = hashlib.sha256(received.encode()).hexdigest()
    return hmac.compare_digest(received_hash, expected_hash)


class TokenAuthMiddleware:
    """Middleware Starlette : rejette les requêtes sans Bearer token valide.

    Actif uniquement si GARMCP_TOKEN est défini. Comparaison en temps
    constant sur des hachés du secret pour éviter toute fuite par analyse
    temporelle.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        expected = get_token()
        if expected is not None:
            request = Request(scope)
            expected_hash = hashlib.sha256(expected.encode()).hexdigest()
            auth_header = request.headers.get("authorization", "")
            if not auth_header.lower().startswith("bearer "):
                response = JSONResponse(
                    {"error": "unauthorized", "detail": "Bearer token requis"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
            if not _matches(auth_header[7:].strip(), expected_hash):
                response = JSONResponse(
                    {"error": "unauthorized", "detail": "Token invalide"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
