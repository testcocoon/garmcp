"""Authentification au compte Garmin Connect."""

from __future__ import annotations

import os
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = Path(os.environ.get("GARMCP_TOKEN_DIR", Path.home() / ".garmcp"))
TOKEN_STORE_FILENAME = "garmin_tokens.json"


class GarminAuthError(Exception):
    """Erreur d'authentification ou de connexion au compte Garmin."""


class TokenStore:
    """Emplacement de stockage local des tokens OAuth Garmin."""

    def __init__(self, token_dir: Path | None = None) -> None:
        self.token_dir = Path(token_dir) if token_dir else TOKEN_DIR
        self.token_path = self.token_dir / TOKEN_STORE_FILENAME

    def exists(self) -> bool:
        return self.token_path.exists()

    def ensure_dir(self) -> None:
        self.token_dir.mkdir(parents=True, exist_ok=True)


def login(
    email: str | None = None,
    password: str | None = None,
    token_store: TokenStore | None = None,
) -> Garmin:
    """Se connecte au compte Garmin Connect.

    Utilise les tokens OAuth sauvegardés s'ils existent et sont valides ;
    sinon se connecte avec email/mot de passe puis sauvegarde les tokens.
    Les identifiants peuvent venir des arguments ou des variables
    d'environnement GARMIN_EMAIL / GARMIN_PASSWORD.
    """
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")
    store = token_store or TokenStore()

    if not store.exists() and (not email or not password):
        raise GarminAuthError(
            "Aucun token sauvegardé et aucun identifiant fourni. "
            "Définissez GARMIN_EMAIL/GARMIN_PASSWORD ou transmettez "
            "email et mot de passe à l'outil garmin_login."
        )

    store.ensure_dir()
    client = Garmin(email, password)
    try:
        mfa_status, _ = client.login(str(store.token_path))
    except (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    ) as exc:
        raise GarminAuthError(f"Échec de connexion Garmin : {exc}") from exc

    if mfa_status:
        raise GarminAuthError(
            "Garmin exige une authentification multi-facteurs (MFA), "
            "non supportée par ce connecteur. Désactivez la MFA ou "
            "utilisez un mot de passe dédié sans MFA."
        )

    return client


def logout(token_store: TokenStore | None = None) -> None:
    """Supprime les tokens sauvegardés."""
    store = token_store or TokenStore()
    if store.token_path.exists():
        store.token_path.unlink()
