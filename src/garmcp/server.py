"""Serveur MCP exposant les outils de connexion et données Garmin Connect."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from .auth import GarminAuthError, login, login_mfa_step2, logout
from .client import GarminClient

mcp = MCPServer(name="garmcp", description="Connecteur Garmin Connect")

_client: GarminClient | None = None

# Sessions MFA en attente : étape 1 terminée, en attente du code.
# L'état MFA vit sur l'instance Garmin (en mémoire du processus serveur).
_mfa_sessions: dict[str, Any] = {}


def get_client() -> GarminClient:
    """Retourne le client Garmin connecté (connexion paresseuse)."""
    global _client
    if _client is None:
        _client = GarminClient(login())
    return _client


def _json(data: Any) -> str:
    if data is None:
        return "{}"
    if isinstance(data, str):
        try:
            return json.dumps(json.loads(data), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return data
    return json.dumps(data, ensure_ascii=False, indent=2)


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


@mcp.tool()
def garmin_login(email: str | None = None, password: str | None = None) -> str:
    """Se connecte au compte Garmin Connect.

    Sans arguments, utilise GARMIN_EMAIL/GARMIN_PASSWORD ou les tokens
    sauvegardés. Si le compte est protégé par la 2FA, Garmin envoie un
    code par email : l'outil retourne alors un session_id et le code
    reçu doit être soumis via garmin_mfa_verify pour terminer la connexion.

    Args:
        email: Adresse email du compte Garmin (optionnel si env var définie).
        password: Mot de passe du compte Garmin (optionnel si env var définie).
    """
    global _client
    try:
        result = login(email, password, mfa_sessions=_mfa_sessions)
    except GarminAuthError as exc:
        return f"Échec de connexion : {exc}"
    if isinstance(result, str):
        return (
            f"Code 2FA envoyé par email par Garmin. Session : {result}. "
            "Consultez votre boîte mail et transmettez le code à 6 chiffres "
            f"avec garmin_mfa_verify(session_id={result!r}, mfa_code=...)."
        )
    try:
        client = GarminClient(result)
        client.get_summary(date.today().isoformat())
    except GarminAuthError as exc:
        return f"Échec de connexion : {exc}"
    _client = client
    return "Connecté au compte Garmin avec succès."


@mcp.tool()
def garmin_mfa_verify(session_id: str, mfa_code: str) -> str:
    """Vérifie le code 2FA reçu par email après garmin_login.

    Args:
        session_id: Identifiant de session retourné par garmin_login.
        mfa_code: Code à 6 chiffres reçu par email.
    """
    global _client
    try:
        client = login_mfa_step2(session_id, mfa_code, _mfa_sessions)
        wrapper = GarminClient(client)
        wrapper.get_summary(date.today().isoformat())
    except GarminAuthError as exc:
        return f"Échec : {exc}"
    _client = wrapper
    return "Connecté au compte Garmin avec succès (MFA validée)."


@mcp.tool()
def garmin_logout() -> str:
    """Se déconnecte et supprime les tokens sauvegardés."""
    global _client
    _client = None
    logout()
    return "Déconnecté, tokens supprimés."


@mcp.tool()
def garmin_status() -> str:
    """Vérifie l'état de la connexion au compte Garmin."""
    if _client is None:
        try:
            get_client()
        except GarminAuthError as exc:
            return f"Non connecté : {exc}"
    try:
        summary = get_client().get_summary(date.today().isoformat())
        full_name = summary.get("fullName", "inconnu")
        return f"Connecté en tant que {full_name}."
    except GarminAuthError as exc:
        return f"Session invalide : {exc}"


@mcp.tool()
def garmin_daily_summary(days_ago: int = 0) -> str:
    """Résumé quotidien (steps, calories, fréquence cardiaque, stress...).

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_summary(_days_ago(days_ago)))


@mcp.tool()
def garmin_activities(limit: int = 10) -> str:
    """Liste les dernières activités (course, vélo, natation...).

    Args:
        limit: Nombre maximum d'activités à retourner.
    """
    return _json(get_client().get_activities(limit))


@mcp.tool()
def garmin_activity(activity_id: str) -> str:
    """Détails d'une activité spécifique.

    Args:
        activity_id: Identifiant de l'activité Garmin.
    """
    return _json(get_client().get_activity(activity_id))


@mcp.tool()
def garmin_sleep(days_ago: int = 0) -> str:
    """Données de sommeil pour une nuit donnée.

    Args:
        days_ago: Nombre de jours en arrière (0 = dernière nuit).
    """
    return _json(get_client().get_sleep(_days_ago(days_ago)))


@mcp.tool()
def garmin_steps(days_ago: int = 0) -> str:
    """Nombre de pas pour une journée donnée.

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_steps(_days_ago(days_ago)))


@mcp.tool()
def garmin_heart_rate(days_ago: int = 0) -> str:
    """Fréquence cardiaque (repos, min/max) pour une journée.

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_heart_rate(_days_ago(days_ago)))


@mcp.tool()
def garmin_body_battery(days_ago: int = 0) -> str:
    """Niveau de batterie corporelle pour une journée.

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_body_battery(_days_ago(days_ago)))


@mcp.tool()
def garmin_stress(days_ago: int = 0) -> str:
    """Données de stress pour une journée.

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_stress(_days_ago(days_ago)))


@mcp.tool()
def garmin_weight() -> str:
    """Dernières mesures de poids."""
    return _json(get_client().get_body_weight())


@mcp.tool()
def garmin_devices() -> str:
    """Liste les appareils Garmin enregistrés sur le compte."""
    return _json(get_client().get_devices())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
