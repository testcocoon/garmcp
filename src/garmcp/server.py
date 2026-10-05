"""Serveur MCP exposant les outils de connexion et données Garmin Connect."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from .auth import GarminAuthError, login, logout
from .client import GarminClient

mcp = MCPServer(name="garmcp", description="Connecteur Garmin Connect")

_client: GarminClient | None = None


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
    sauvegardés. Une fois connecté, les tokens sont stockés localement
    pour les appels suivants.

    Args:
        email: Adresse email du compte Garmin (optionnel si env var définie).
        password: Mot de passe du compte Garmin (optionnel si env var définie).
    """
    global _client
    try:
        client = GarminClient(login(email, password))
        client.get_summary(date.today().isoformat())
    except GarminAuthError as exc:
        return f"Échec de connexion : {exc}"
    _client = client
    return "Connecté au compte Garmin avec succès."


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
def garmin_activities_between(start: str, end: str) -> str:
    """Liste les activit\u00e9s compl\u00e8tes entre deux dates (incluses).

    Les index de d\u00e9but et de fin dans la liste des activit\u00e9s sont
    d\u00e9termin\u00e9s par dichotomie, puis la liste compl\u00e8te est charg\u00e9e.

    Args:
        start: Date de d\u00e9but au format ISO (YYYY-MM-DD), incluse.
        end: Date de fin au format ISO (YYYY-MM-DD), incluse.
    """
    try:
        return _json(get_client().get_activities_between(start, end))
    except GarminAuthError as exc:
        return f"Erreur : {exc}"


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
