"""Serveur MCP exposant les outils de connexion et données Garmin Connect.

Support multi-utilisateur : des comptes garmcp locaux (outils user_*) sont
connectés chacun à un compte Garmin (garmin_login / garmin_mfa_verify) ;
les requêtes MCP sont alors servies avec le compte Garmin de l'utilisateur
courant. En transport HTTP, l'utilisateur est identifié par le bearer token
de session (Authorization: Bearer <token de user_login>) ; en stdio, par
l'utilisateur actif (dernier user_login réussi). Sans compte utilisateur,
le serveur retombe sur le mode historique à compte unique
(GARMIN_EMAIL/GARMIN_PASSWORD ou ~/.garmcp/garmin_tokens.json).
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from datetime import date, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from .auth import GarminAuthError, TokenStore, login, login_mfa_step2, logout
from .client import GarminClient
from .logging import get_logger
from .users import UserError, UserStore

mcp = MCPServer(name="garmcp", description="Connecteur Garmin Connect")

logger = get_logger(__name__)

user_store = UserStore()

_client: GarminClient | None = None
_clients: dict[str, GarminClient] = {}
_active_user: str | None = None

# Sessions MFA en attente : étape 1 terminée, en attente du code.
# Une sous-dict par utilisateur (clé = nom d'utilisateur, "" = compte unique
# historique) ; l'état MFA vit sur l'instance Garmin (mémoire du processus).
_mfa_sessions: dict[str, dict[str, Any]] = {}

# Contexte de la requête en cours : (bearer token, utilisateur) résolu depuis
# les en-têtes HTTP, renseigné par le middleware ci-dessous. En stdio, aucun
# en-tête : le middleware laisse None et on retombe sur _active_user.
_current_session_var: ContextVar[tuple[str | None, str | None] | None] = ContextVar(
    "garmcp_current_session", default=None
)
_http_request_var: ContextVar[bool] = ContextVar("garmcp_http_request", default=False)


async def _user_context_middleware(ctx: Any, call_next: Any) -> Any:
    """Résout l'utilisateur courant depuis le bearer token de la requête HTTP."""
    request = getattr(ctx, "request", None)
    headers = getattr(request, "headers", None)
    is_http = headers is not None
    token = None
    if is_http:
        auth_header = headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    username = user_store.resolve_session(token) if token else None
    reset_session = _current_session_var.set((token, username) if is_http else None)
    reset_http = _http_request_var.set(is_http)
    try:
        return await call_next(ctx)
    finally:
        _current_session_var.reset(reset_session)
        _http_request_var.reset(reset_http)


mcp.middleware.append(_user_context_middleware)


def _resolve_user() -> str | None:
    """Utilisateur garmcp courant : session HTTP (bearer token) puis actif stdio."""
    session = _current_session_var.get()
    if session is not None and session[1] is not None:
        return session[1]
    return _active_user


def _token_store_for(user: str | None) -> TokenStore:
    if user is None:
        return TokenStore()
    return user_store.token_store_for(user)


def _get_client_for(user: str | None) -> GarminClient:
    global _client
    if user is None:
        if _client is None:
            _client = GarminClient(login())
        return _client
    client = _clients.get(user)
    if client is None:
        client = GarminClient(login(token_store=user_store.token_store_for(user)))
        _clients[user] = client
    return client


def get_client() -> GarminClient:
    """Retourne le client Garmin de l'utilisateur courant (connexion paresseuse)."""
    return _get_client_for(_resolve_user())


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
def user_create(username: str, password: str) -> str:
    """Crée un compte utilisateur garmcp (stocké localement, mot de passe haché).

    Connectez ensuite ce compte à son compte Garmin avec garmin_login, puis
    authentifiez-vous avec user_login pour servir les requêtes MCP de cet
    utilisateur.

    Args:
        username: Nom d'utilisateur (1-64 caractères : lettres, chiffres, '.', '-', '_').
        password: Mot de passe du compte garmcp (minimum 8 caractères).
    """
    try:
        user_store.create(username, password)
    except UserError as exc:
        logger.debug("user_create a échoué : %s", exc)
        return f"Échec de création : {exc}"
    logger.debug("user_create : compte %s créé", username)
    return (
        f"Compte '{username}' créé. Connectez-le à Garmin avec "
        "garmin_login(email, password), puis authentifiez-vous avec "
        "user_login(username, password)."
    )


@mcp.tool()
def user_login(username: str, password: str) -> str:
    """Authentifie un compte utilisateur garmcp et retourne un token de session.

    En transport HTTP, transmettez ce token dans l'en-tête
    « Authorization: Bearer <token> » : les requêtes suivantes seront servies
    avec le compte Garmin de cet utilisateur. En stdio, ce compte devient
    l'utilisateur actif.

    Args:
        username: Nom d'utilisateur du compte garmcp.
        password: Mot de passe du compte garmcp.
    """
    global _active_user
    if not user_store.verify(username, password):
        logger.debug("user_login a échoué pour %s", username)
        return "Échec : nom d'utilisateur ou mot de passe invalide."
    token = user_store.create_session(username)
    if not _http_request_var.get():
        _active_user = username
    logger.debug("user_login : session créée pour %s", username)
    return (
        f"Connecté en tant que '{username}'. Token de session : {token}\n"
        "En transport HTTP, envoyez ce token dans l'en-tête "
        "« Authorization: Bearer <token> » ; en stdio, ce compte est désormais "
        "l'utilisateur actif. Connectez son compte Garmin avec "
        "garmin_login(email, password) si ce n'est pas déjà fait."
    )


@mcp.tool()
def user_logout() -> str:
    """Révoque la session utilisateur courante (compte garmcp, pas Garmin)."""
    global _active_user
    session = _current_session_var.get()
    if session is not None and session[0]:
        user_store.revoke_session(session[0])
        logger.debug("user_logout : session HTTP révoquée pour %s", session[1])
        return f"Session révoquée (utilisateur '{session[1]}')."
    if _active_user is not None:
        user = _active_user
        user_store.revoke_user_sessions(user)
        _clients.pop(user, None)
        _active_user = None
        logger.debug("user_logout : utilisateur actif %s déconnecté", user)
        return f"Déconnecté (utilisateur '{user}'), sessions révoquées."
    return "Aucune session active."


@mcp.tool()
def user_delete(username: str, password: str) -> str:
    """Supprime un compte utilisateur, ses sessions et ses tokens Garmin.

    Args:
        username: Nom d'utilisateur du compte à supprimer.
        password: Mot de passe du compte (vérifié avant suppression).
    """
    global _active_user
    if not user_store.verify(username, password):
        return "Échec : nom d'utilisateur ou mot de passe invalide."
    try:
        user_store.delete(username)
    except UserError as exc:
        return f"Échec : {exc}"
    _clients.pop(username, None)
    _mfa_sessions.pop(username, None)
    if _active_user == username:
        _active_user = None
    logger.debug("user_delete : compte %s supprimé", username)
    return f"Compte '{username}' supprimé (sessions et tokens Garmin inclus)."


@mcp.tool()
def users_list() -> str:
    """Liste les noms des comptes utilisateurs garmcp existants."""
    return _json(user_store.list_users())


@mcp.tool()
def user_status() -> str:
    """État du compte utilisateur courant et de sa connexion Garmin."""
    user = _resolve_user()
    if user is None:
        return _json({"user": None, "garmin_connected": TokenStore().exists()})
    return _json(
        {
            "user": user,
            "garmin_connected": user_store.garmin_connected(user),
            "sessions": user_store.session_count(user),
        }
    )


@mcp.tool()
def garmin_login(email: str | None = None, password: str | None = None) -> str:
    """Connecte l'utilisateur courant à son compte Garmin Connect.

    Les tokens sont stockés dans le répertoire dédié à l'utilisateur courant
    (compte garmcp), ou dans ~/.garmcp/garmin_tokens.json en mode compte
    unique. Sans arguments, utilise GARMIN_EMAIL/GARMIN_PASSWORD ou les
    tokens sauvegardés. Si le compte est protégé par la 2FA, Garmin envoie un
    code par email : l'outil retourne alors un session_id et le code
    reçu doit être soumis via garmin_mfa_verify pour terminer la connexion.

    Args:
        email: Adresse email du compte Garmin (optionnel si env var définie).
        password: Mot de passe du compte Garmin (optionnel si env var définie).
    """
    global _client
    user = _resolve_user()
    store = _token_store_for(user)
    sessions = _mfa_sessions.setdefault(user or "", {})
    logger.debug(
        "garmin_login appelé (email fourni : %s, utilisateur : %s)", bool(email), user
    )
    try:
        result = login(email, password, token_store=store, mfa_sessions=sessions)
    except GarminAuthError as exc:
        logger.debug("garmin_login a échoué : %s", exc)
        return f"Échec de connexion : {exc}"
    if isinstance(result, str):
        logger.debug("2FA requise, session_id émis")
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
    if user is not None:
        _clients[user] = client
    else:
        _client = client
    logger.debug("garmin_login : connexion établie (utilisateur : %s)", user)
    suffix = f" (utilisateur '{user}')" if user else ""
    return f"Connecté au compte Garmin avec succès{suffix}."


@mcp.tool()
def garmin_mfa_verify(session_id: str, mfa_code: str) -> str:
    """Vérifie le code 2FA reçu par email après garmin_login.

    Args:
        session_id: Identifiant de session retourné par garmin_login.
        mfa_code: Code à 6 chiffres reçu par email.
    """
    global _client
    user = _resolve_user()
    store = _token_store_for(user)
    sessions = _mfa_sessions.get(user or "", {})
    logger.debug(
        "garmin_mfa_verify appelé pour session %s (utilisateur : %s)",
        session_id[:8],
        user,
    )
    try:
        client = login_mfa_step2(session_id, mfa_code, sessions, token_store=store)
        wrapper = GarminClient(client)
        wrapper.get_summary(date.today().isoformat())
    except GarminAuthError as exc:
        logger.debug("garmin_mfa_verify a échoué : %s", exc)
        return f"Échec : {exc}"
    if user is not None:
        _clients[user] = wrapper
    else:
        _client = wrapper
    suffix = f" (utilisateur '{user}')" if user else ""
    return f"Connecté au compte Garmin avec succès (MFA validée){suffix}."


@mcp.tool()
def garmin_logout() -> str:
    """Se déconnecte de Garmin et supprime les tokens de l'utilisateur courant."""
    global _client
    user = _resolve_user()
    if user is not None:
        _clients.pop(user, None)
        logout(token_store=user_store.token_store_for(user))
        logger.debug("garmin_logout : tokens supprimés pour %s", user)
        return f"Déconnecté de Garmin (utilisateur '{user}'), tokens supprimés."
    _client = None
    logout()
    logger.debug("garmin_logout : tokens supprimés")
    return "Déconnecté, tokens supprimés."


@mcp.tool()
def garmin_status() -> str:
    """Vérifie l'état de la connexion Garmin de l'utilisateur courant."""
    user = _resolve_user()
    try:
        summary = get_client().get_summary(date.today().isoformat())
        full_name = summary.get("fullName", "inconnu")
        if user is not None:
            return f"Connecté en tant que {full_name} (compte garmcp '{user}')."
        return f"Connecté en tant que {full_name}."
    except GarminAuthError as exc:
        if user is not None:
            return f"Non connecté (utilisateur '{user}') : {exc}"
        return f"Session invalide : {exc}"


@mcp.tool()
def garmin_daily_summary(days_ago: int = 0) -> str:
    """Résumé quotidien (steps, calories, fréquence cardiaque, stress...).

    logger.debug("garmin_daily_summary appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_summary(_days_ago(days_ago)))


@mcp.tool()
def garmin_activities(start: int = 0, limit: int = 10) -> str:
    """Liste les activités à partir de l'index `start` (course, vélo, natation...).

    Interroge l'API Garmin avec ?start=<start>&limit=<limit>.
    Au-delà de 100 activités, la pagination est automatique
    (requêtes successives de 100 depuis `start`).

    Args:
        start: Index de la première activité (0 = plus récente).
        limit: Nombre maximum d'activités à retourner.
    """
    logger.debug("garmin_activities appelé (start=%s, limit=%s)", start, limit)
    return _json(get_client().get_activities(start, limit))


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
def garmin_all_activities(max_activities: int | None = None) -> str:
    """Télécharge toutes les activités en paginant (requêtes de 100).

    Équivalent à garmin_activities avec un limit élevé, mais plus
    explicite : interroge le service d'activités avec start=0, 100,
    200, ... et limit=100 jusqu'à récupérer tout l'historique.

    Args:
        max_activities: Nombre maximum d'activités à télécharger
            (None = tout l'historique).
    """
    logger.debug(
        "garmin_all_activities appelé (max=%s)", max_activities or "tout"
    )
    return _json(get_client().get_all_activities(max_activities))


@mcp.tool()
def garmin_sleep(days_ago: int = 0) -> str:
    """Données de sommeil pour une nuit donnée.

    logger.debug("garmin_sleep appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = dernière nuit).
    """
    return _json(get_client().get_sleep(_days_ago(days_ago)))


@mcp.tool()
def garmin_steps(days_ago: int = 0) -> str:
    """Nombre de pas pour une journée donnée.

    logger.debug("garmin_steps appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_steps(_days_ago(days_ago)))


@mcp.tool()
def garmin_heart_rate(days_ago: int = 0) -> str:
    """Fréquence cardiaque (repos, min/max) pour une journée.

    logger.debug("garmin_heart_rate appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_heart_rate(_days_ago(days_ago)))


@mcp.tool()
def garmin_body_battery(days_ago: int = 0) -> str:
    """Niveau de batterie corporelle pour une journée.

    logger.debug("garmin_body_battery appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_body_battery(_days_ago(days_ago)))


@mcp.tool()
def garmin_stress(days_ago: int = 0) -> str:
    """Données de stress pour une journée.

    logger.debug("garmin_stress appelé (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    return _json(get_client().get_stress(_days_ago(days_ago)))


@mcp.tool()
def garmin_hrv(days_ago: int = 0) -> str:
    """Variabilit\u00e9 de la fr\u00e9quence cardiaque (HRV, baseline et statut) pour une journ\u00e9e.

    logger.debug("garmin_hrv appel\u00e9 (days_ago=%s)", days_ago)
    Args:
        days_ago: Nombre de jours en arri\u00e8re (0 = aujourd'hui).
    """
    return _json(get_client().get_hrv(_days_ago(days_ago)))


@mcp.tool()
def garmin_weight(days_ago: int = 0) -> str:
    """Dernière mesure de poids (et composition corporelle) pour une journée.

    Retourne le poids, l'IMC, la masse grasse/musculaire et la date de
    la dernière mesure du jour demandé.

    Args:
        days_ago: Nombre de jours en arrière (0 = aujourd'hui).
    """
    logger.debug("garmin_weight appelé (days_ago=%s)", days_ago)
    return _json(get_client().get_body_weight_for_day(_days_ago(days_ago)))


@mcp.tool()
def garmin_weight_history(days: int = 7) -> str:
    """Historique du poids sur plusieurs jours.

    Args:
        days: Nombre de jours d'historique (défaut : 7, max 365).
    """
    days = max(1, min(days, 365))
    logger.debug("garmin_weight_history appelé (days=%s)", days)
    start = _days_ago(days)
    end = _days_ago(0)
    return _json(get_client().get_body_composition(start, end))


@mcp.tool()
def garmin_devices() -> str:
    """Liste les appareils Garmin enregistrés sur le compte."""
    return _json(get_client().get_devices())

@mcp.tool()
def garmin_profile() -> str:
    """Données du profil Garmin Connect de l'utilisateur connecté.

    Retourne les informations du profil : nom complet, âge, taille,
    poids, sexe, VO2 max, zones de fréquence cardiaque, objectifs, etc.
    """
    logger.debug("garmin_profile appelé")
    return _json(get_client().get_user_profile())

@mcp.tool()
def garmin_scheduled_workouts(year: int, month: int) -> str:
    """Liste les entraînements planifiés pour un mois donné.

    Interroge le calendrier d'entraînement Garmin Connect et retourne
    les séances planifiées (type workout) du mois demandé.

    Args:
        year: Année (ex. 2025).
        month: Mois de 1 à 12.
    """
    logger.debug("garmin_scheduled_workouts appelé (%s/%s)", month, year)
    return _json(get_client().get_scheduled_workouts(year, month))


@mcp.tool()
def garmin_next_scheduled_workout() -> str:
    """Retourne le prochain entraînement planifié (aujourd'hui ou plus tard).

    Vérifie le mois courant puis le suivant ; retourne {} si aucune
    séance n'est planifiée.
    """
    logger.debug("garmin_next_scheduled_workout appelé")
    return _json(get_client().get_next_scheduled_workout())


@mcp.tool()
def garmin_scheduled_workout(workout_id: str) -> str:
    """Détails d'un entraînement planifié par son identifiant.

    Args:
        workout_id: Identifiant de l'entraînement planifié (issu de
            garmin_scheduled_workouts ou garmin_next_scheduled_workout).
    """
    logger.debug("garmin_scheduled_workout appelé (id=%s)", workout_id)
    return _json(get_client().get_scheduled_workout_by_id(workout_id))


@mcp.tool()
def garmin_challenges(start: int = 0, limit: int = 100) -> str:
    """Défis adhoc de l'utilisateur (défis quotidiens/hebdomadaires, statut inclus).

    Args:
        start: Index du premier défi (0 = plus récent).
        limit: Nombre maximum de défis à retourner.
    """
    logger.debug("garmin_challenges appelé (start=%s, limit=%s)", start, limit)
    return _json(get_client().get_adhoc_challenges(start, limit))


@mcp.tool()
def garmin_badge_challenges(start: int = 1, limit: int = 100) -> str:
    """Défis badge de l'utilisateur, avec leur statut (terminés et en cours).

    Args:
        start: Index du premier défi (1 = plus récent).
        limit: Nombre maximum de défis à retourner.
    """
    logger.debug("garmin_badge_challenges appelé (start=%s, limit=%s)", start, limit)
    return _json(get_client().get_badge_challenges(start, limit))


@mcp.tool()
def garmin_available_badge_challenges(start: int = 0, limit: int = 100) -> str:
    """Défis badge disponibles (non encore rejoints).

    Args:
        start: Index du premier défi (0 = plus récent).
        limit: Nombre maximum de défis à retourner.
    """
    logger.debug("garmin_available_badge_challenges appelé (start=%s, limit=%s)", start, limit)
    return _json(get_client().get_available_badge_challenges(start, limit))

@mcp.tool()
def garmin_non_completed_badge_challenges(start: int = 1, limit: int = 100) -> str:
    """Défis badge non terminés de l'utilisateur (statut en cours).

    Args:
        start: Index du premier défi (1 = plus récent).
        limit: Nombre maximum de défis à retourner.
    """
    logger.debug(
        "garmin_non_completed_badge_challenges appelé (start=%s, limit=%s)", start, limit
    )
    return _json(get_client().get_non_completed_badge_challenges(start, limit))


@mcp.tool()
def garmin_inprogress_virtual_challenges(start: int = 0, limit: int = 100) -> str:
    """Défis virtuels en cours (courses/marches cumulatives, progression incluse).

    Args:
        start: Index du premier défi (0 = plus récent).
        limit: Nombre maximum de défis à retourner.
    """
    logger.debug(
        "garmin_inprogress_virtual_challenges appelé (start=%s, limit=%s)", start, limit
    )
    return _json(get_client().get_inprogress_virtual_challenges(start, limit))


def main() -> None:
    logger.debug("Démarrage du serveur MCP garmcp (log=%s)", os.environ.get("GARMCP_LOG", "stderr"))
    mcp.run()


if __name__ == "__main__":
    main()
