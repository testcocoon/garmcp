# garmcp — Connecteur MCP Garmin

Serveur [Model Context Protocol](https://modelcontextprotocol.io) qui permet à un assistant IA de **se connecter à un compte Garmin Connect** et d'exposer ses données : activités, sommeil, pas, fréquence cardiaque, batterie corporelle, stress, poids, appareils.

## Installation

```bash
pip install garmcp
```

Ou depuis les sources :

```bash
pip install -e .
```

## Configuration

Le connecteur a besoin des identifiants Garmin, via variables d'environnement :

```bash
export GARMIN_EMAIL="vous@example.com"
export GARMIN_PASSWORD="votre-mot-de-passe"
```

Optionnel : répertoire de stockage des tokens OAuth (par défaut `~/.garmcp`) :

```bash
export GARMCP_TOKEN_DIR="/chemin/vers/tokens"
```

> Après la première connexion, les tokens OAuth sont sauvegardés localement : les appels suivants n'ont plus besoin de l'email/mot de passe et ne les stockent jamais sur disque.

## Utilisation

Lancement du serveur MCP (transport stdio) via le script d'installation et de démarrage :

```bash
./start.sh
```

Le script crée un environnement virtuel `.venv`, installe `garmcp` et ses dépendances, puis démarre le serveur. Le répertoire du venv est personnalisable via `GARMCP_VENV`.

Ou directement, si le paquet est déjà installé :

```bash
garmcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "garmcp": {
      "command": "garmcp",
      "env": {
        "GARMIN_EMAIL": "vous@example.com",
        "GARMIN_PASSWORD": "votre-mot-de-passe"
      }
    }
  }
}
```

### Outils exposés

| Outil | Description |
|---|---|
| `garmin_login` | Se connecte au compte Garmin ; si la 2FA est active, Garmin envoie un code par email |
| `garmin_mfa_verify` | Soumet le code 2FA reçu par email et termine la connexion |
| `garmin_logout` | Se déconnecte et supprime les tokens locaux |
| `garmin_status` | Vérifie l'état de la connexion |
| `garmin_daily_summary` | Résumé quotidien (steps, calories, FC, stress...) |
| `garmin_activities` | Dernières activités |
| `garmin_activity` | Détails d'une activité par ID |
| `garmin_sleep` | Données de sommeil |
| `garmin_steps` | Nombre de pas et objectif |
| `garmin_heart_rate` | Fréquence cardiaque |
| `garmin_body_battery` | Batterie corporelle |
| `garmin_stress` | Données de stress |
| `garmin_weight` | Mesures de poids |
| `garmin_devices` | Appareils enregistrés |

La plupart des outils acceptent `days_ago` (0 = aujourd'hui).

## Authentification à deux facteurs (2FA)

Si le compte Garmin est protégé par la 2FA, la connexion se fait naturellement en deux étapes :

1. `garmin_login(email, password)` — Garmin envoie un code à 6 chiffres **par email**. L'outil retourne un `session_id` et vous invite à consulter votre boîte mail.
2. `garmin_mfa_verify(session_id, mfa_code)` — le code reçu est vérifié, la connexion est établie et les tokens sont sauvegardés (les connexions suivantes n'exigeront plus la 2FA).

Exemple de dialogue :

```
> garmin_login(email="vous@example.com", password="...")
Code 2FA envoyé par email par Garmin. Session : a1b2c3d4...
> garmin_mfa_verify(session_id="a1b2c3d4...", mfa_code="123456")
Connecté au compte Garmin avec succès (MFA validée).
```

La session 2FA en attente vit en mémoire du serveur : si le code expire ou si le serveur redémarre, relancez `garmin_login`.

## Développement

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Avertissement

Ce projet utilise une bibliothèque non officielle pour Garmin Connect. Utilisez un mot de passe dédié à ce service.
