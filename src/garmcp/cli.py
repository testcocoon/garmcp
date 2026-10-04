"""CLI de garmcp : login interactif avec 2FA et stockage du token.

Utilisation :
    garmcp --login [EMAIL]

Sans --login, le serveur MCP démarre normalement (stdio).
Avec --login, le flux interactif de connexion s'exécute dans le terminal :
email, mot de passe, code 2FA reçu par email ; le token OAuth est ensuite
stocké localement (~/.garmcp/garmin_tokens.json) pour les connexions
suivantes, qui n'exigeront plus la 2FA.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from .auth import GarminAuthError, TokenStore, login, login_mfa_step2
from .logging import get_logger

logger = get_logger(__name__)


def _prompt_email() -> str:
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    if not email:
        try:
            email = input("Email Garmin : ").strip()
        except EOFError:
            print("\nAucun email fourni.", file=sys.stderr)
            raise SystemExit(1) from None
    else:
        print(f"Email (GARMIN_EMAIL) : {email}")
    return email


def _prompt_password() -> str:
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not password:
        try:
            password = getpass.getpass("Mot de passe Garmin : ")
        except EOFError:
            print("\nAucun mot de passe fourni.", file=sys.stderr)
            raise SystemExit(1) from None
    return password


def run_login() -> int:
    """Connexion interactive avec support 2FA, puis stockage du token.

    Retourne 0 en cas de succès, 1 en cas d'échec.
    """
    email = _prompt_email()
    password = _prompt_password()
    mfa_sessions: dict[str, object] = {}

    print("Connexion à Garmin Connect...")
    try:
        result = login(email, password, mfa_sessions=mfa_sessions)
    except GarminAuthError as exc:
        print(f"Échec de connexion : {exc}", file=sys.stderr)
        return 1

    if isinstance(result, str):
        print("Un code à 6 chiffres a été envoyé par email par Garmin.")
        code = getpass.getpass("Code 2FA : ").strip()
        try:
            login_mfa_step2(result, code, mfa_sessions)
        except GarminAuthError as exc:
            print(f"Échec de la vérification 2FA : {exc}", file=sys.stderr)
            return 1

    store = TokenStore()
    if store.exists():
        print(f"Token de connexion stocké : {store.token_path}")
        print("Les prochaines connexions utiliseront ce token sans 2FA.")
    else:
        print("Connecté, mais le token n'a pas été trouvé sur le disque.")
        return 1
    logger.debug("CLI --login : connexion établie, token stocké")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="garmcp",
        description="Connecteur MCP Garmin Connect. Sans option, démarre le serveur MCP (stdio).",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="connexion interactive (avec 2FA si requise) puis stockage du token, puis quitte",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="démarre le serveur MCP en HTTP streamable (pour connecteur Mistral Chat)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("GARMCP_HOST", "127.0.0.1"),
        help="adresse d'écoute HTTP (défaut : 127.0.0.1, ou GARMCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("GARMCP_PORT", "8000")),
        help="port d'écoute HTTP (défaut : 8000, ou GARMCP_PORT)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.login:
        return run_login()
    if args.http:
        from .server import mcp

        mcp.run(
            "streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path="/mcp",
        )
        return 0
    from .server import main as serve

    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
