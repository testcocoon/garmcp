"""Authentification au compte Garmin Connect (avec support MFA)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .logging import get_logger

logger = get_logger(__name__)

TOKEN_DIR = Path(os.environ.get("GARMCP_TOKEN_DIR", Path.home() / ".garmcp"))
TOKEN_STORE_FILENAME = "garmin_tokens.json"


class GarminAuthError(Exception):
    """Erreur d'authentification ou de connexion au compte Garmin."""


class TokenStore:
    """Stockage local des tokens OAuth Garmin."""

    def __init__(self, token_dir: Path | None = None) -> None:
        self.token_dir = Path(token_dir) if token_dir else TOKEN_DIR
        self.token_path = self.token_dir / TOKEN_STORE_FILENAME

    def exists(self) -> bool:
        return self.token_path.exists()

    def ensure_dir(self) -> None:
        self.token_dir.mkdir(parents=True, exist_ok=True)


def _persist_tokens(client: Garmin, store: TokenStore) -> None:
    """Sauvegarde les tokens OAuth via le client interne (perms 0600)."""
    store.ensure_dir()
    client.client.dump(str(store.token_path))


def login(
    email: str | None = None,
    password: str | None = None,
    token_store: TokenStore | None = None,
    mfa_sessions: dict[str, Garmin] | None = None,
) -> Garmin | str:
    """Se connecte au compte Garmin Connect.

    Utilise les tokens OAuth sauvegardés s'ils existent et sont valides ;
    sinon se connecte avec email/mot de passe.

    Si Garmin exige un code 2FA (envoyé par email), la session est mise
    en attente et un identifiant de session (str) est retourné : le code
    reçu doit ensuite être soumis via login_mfa_step2.
    Sinon, retourne le client connecté (tokens sauvegardés).
    """
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")
    store = token_store or TokenStore()
    sessions = mfa_sessions if mfa_sessions is not None else {}

    if not store.exists() and (not email or not password):
        raise GarminAuthError(
            "Aucun token sauvegardé et aucun identifiant fourni. "
            "Définissez GARMIN_EMAIL/GARMIN_PASSWORD ou transmettez "
            "email et mot de passe à l'outil garmin_login."
        )

    store.ensure_dir()
    if store.exists():
        logger.debug("Tokens existants trouvés : %s", store.token_path)
    else:
        logger.debug(
            "Aucun token, connexion avec identifiants (email=%s)",
            email if email else "env GARMIN_EMAIL",
        )
    client = Garmin(email, password, return_on_mfa=True)
    try:
        mfa_status, _ = client.login(str(store.token_path))
    except (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    ) as exc:
        raise GarminAuthError(f"Échec de connexion Garmin : {exc}") from exc

    if mfa_status == "needs_mfa":
        logger.debug("Garmin exige un code 2FA, session mise en attente")
        session_id = uuid.uuid4().hex
        sessions[session_id] = client
        return session_id

    logger.debug("Connexion Garmin réussie sans 2FA")
    return client


def login_mfa_step2(
    session_id: str,
    mfa_code: str,
    mfa_sessions: dict[str, Garmin],
    token_store: TokenStore | None = None,
) -> Garmin:
    """Étape 2 de la connexion MFA : soumet le code à 6 chiffres.

    Consomme la session MFA en attente correspondant à session_id,
    complète la connexion et sauvegarde les tokens OAuth pour les
    appels suivants.
    """
    store = token_store or TokenStore()
    logger.debug("Vérification du code 2FA pour la session %s", session_id[:8])
    client = mfa_sessions.pop(session_id, None)
    if client is None:
        logger.debug("Session MFA introuvable : %s", session_id)
        raise GarminAuthError(
            "Session MFA introuvable ou expirée. "
            "Relancez garmin_login pour recevoir un nouveau code."
        )

    if not isinstance(mfa_code, str) or not mfa_code.strip():
        raise GarminAuthError("Le code MFA doit être une chaîne non vide.")

    try:
        client.resume_login(None, mfa_code.strip())
    except (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    ) as exc:
        raise GarminAuthError(f"Échec de la vérification du code MFA : {exc}") from exc
    except Exception as exc:
        raise GarminAuthError(f"Erreur pendant la connexion MFA : {exc}") from exc

    try:
        _persist_tokens(client, store)
    except Exception as exc:
        raise GarminAuthError(f"Impossible de sauvegarder les tokens : {exc}") from exc

    logger.debug("Code 2FA validé, tokens sauvegardés dans %s", store.token_path)
    return client


def logout(token_store: TokenStore | None = None) -> None:
    """Supprime les tokens sauvegardés."""
    store = token_store or TokenStore()
    if store.token_path.exists():
        store.token_path.unlink()
