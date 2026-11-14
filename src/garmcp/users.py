"""Comptes utilisateurs locaux de garmcp (support multi-utilisateur).

Chaque compte garmcp est stocké dans un fichier JSON local (par défaut
~/.garmcp/users.json, permissions 0600) avec un mot de passe haché
(PBKDF2-SHA256, sel aléatoire). À chaque compte est associé un répertoire
de tokens Garmin dédié (~/.garmcp/users/<username>/garmin_tokens.json) :
la connexion Garmin d'un utilisateur ne touche jamais aux tokens des autres.

Les sessions (tokens renvoyés par l'outil user_login, à présenter en
Bearer sur les transports HTTP) sont persistées dans le même fichier :
elles survivent au redémarrage du serveur.

Configuration via variables d'environnement :
- GARMCP_TOKEN_DIR : racine de stockage (défaut ~/.garmcp)
- GARMCP_USERS_FILE : chemin du fichier des comptes (défaut <racine>/users.json)
- GARMCP_USERS_DIR : répertoire des tokens Garmin par utilisateur
  (défaut <racine>/users)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .auth import TokenStore
from .logging import get_logger

logger = get_logger(__name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MIN_PASSWORD_LENGTH = 8
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16

TOKEN_DIR_ENV = "GARMCP_TOKEN_DIR"
USERS_FILE_ENV = "GARMCP_USERS_FILE"
USERS_DIR_ENV = "GARMCP_USERS_DIR"


class UserError(Exception):
    """Erreur de gestion des comptes utilisateurs."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


class UserStore:
    """Stockage des comptes utilisateurs, de leurs sessions et de leurs tokens Garmin."""

    def __init__(self, path: Path | None = None, data_dir: Path | None = None) -> None:
        root = Path(os.environ.get(TOKEN_DIR_ENV, Path.home() / ".garmcp"))
        if path is not None:
            self.path = Path(path)
        else:
            self.path = Path(os.environ.get(USERS_FILE_ENV, root / "users.json"))
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.environ.get(USERS_DIR_ENV, root / "users"))
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Fichier utilisateurs illisible, réinitialisé : %s", self.path)
            return {"version": 1, "users": {}}
        if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
            return {"version": 1, "users": {}}
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def exists(self, username: str) -> bool:
        with self._lock:
            return username in self._load()["users"]

    def list_users(self) -> list[str]:
        with self._lock:
            return sorted(self._load()["users"].keys())

    def create(self, username: str, password: str) -> None:
        """Crée un compte. Lève UserError si le nom est invalide ou déjà pris."""
        if not isinstance(username, str) or not USERNAME_RE.match(username):
            raise UserError(
                "Nom d'utilisateur invalide : 1 à 64 caractères parmi "
                "lettres, chiffres, '.', '-' et '_'."
            )
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise UserError(
                f"Mot de passe trop court (minimum {MIN_PASSWORD_LENGTH} caractères)."
            )
        with self._lock:
            data = self._load()
            if username in data["users"]:
                raise UserError(f"Le compte '{username}' existe déjà.")
            data["users"][username] = {
                "password": _hash_password(password, secrets.token_bytes(SALT_BYTES)),
                "created_at": _utcnow(),
                "sessions": {},
            }
            self._save(data)
        logger.debug("Compte utilisateur créé : %s", username)

    def verify(self, username: str, password: str) -> bool:
        """Vérifie le couple identifiant/mot de passe d'un compte."""
        with self._lock:
            record = self._load()["users"].get(username)
        if not isinstance(record, dict):
            return False
        stored = record.get("password", "")
        if not isinstance(stored, str):
            return False
        return _verify_password(password or "", stored)

    def delete(self, username: str) -> None:
        """Supprime un compte, ses sessions et son répertoire de tokens Garmin."""
        with self._lock:
            data = self._load()
            if username not in data["users"]:
                raise UserError(f"Le compte '{username}' n'existe pas.")
            del data["users"][username]
            self._save(data)
        shutil.rmtree(self.data_dir / username, ignore_errors=True)
        logger.debug("Compte utilisateur supprimé : %s", username)

    def create_session(self, username: str) -> str:
        """Crée une session persistante pour un compte et retourne son token."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            data = self._load()
            record = data["users"].get(username)
            if record is None:
                raise UserError(f"Le compte '{username}' n'existe pas.")
            record.setdefault("sessions", {})[token] = _utcnow()
            self._save(data)
        logger.debug("Session créée pour %s", username)
        return token

    def resolve_session(self, token: str) -> str | None:
        """Retourne le nom d'utilisateur propriétaire du token de session, ou None."""
        if not token:
            return None
        with self._lock:
            for username, record in self._load()["users"].items():
                if isinstance(record, dict) and token in record.get("sessions", {}):
                    return username
        return None

    def revoke_session(self, token: str) -> bool:
        """Révoque un token de session. Retourne True s'il existait."""
        with self._lock:
            data = self._load()
            for record in data["users"].values():
                if isinstance(record, dict) and record.get("sessions", {}).pop(token, None):
                    self._save(data)
                    return True
        return False

    def revoke_user_sessions(self, username: str) -> None:
        """Révoque toutes les sessions d'un compte."""
        with self._lock:
            data = self._load()
            record = data["users"].get(username)
            if isinstance(record, dict) and record.get("sessions"):
                record["sessions"] = {}
                self._save(data)

    def session_count(self, username: str) -> int:
        with self._lock:
            record = self._load()["users"].get(username)
        if not isinstance(record, dict):
            return 0
        return len(record.get("sessions", {}))

    def token_store_for(self, username: str) -> TokenStore:
        """TokenStore Garmin dédié à un utilisateur (jamais partagé)."""
        return TokenStore(self.data_dir / username)

    def garmin_connected(self, username: str) -> bool:
        """True si des tokens Garmin sont stockés pour cet utilisateur."""
        return self.token_store_for(username).exists()
