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

Lancement du serveur MCP (transport stdio) :

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
| `garmin_login` | Se connecte au compte Garmin (email/mot de passe ou tokens) |
| `garmin_logout` | Se déconnecte et supprime les tokens locaux |
| `garmin_status` | Vérifie l'état de la connexion |
| `garmin_daily_summary` | Résumé quotidien (steps, calories, FC, stress...) |
| `garmin_activities` | Dernières activités |
| `garmin_activities_between` | Activités complètes entre deux dates (incluses), index de début/fin déterminés par dichotomie |
| `garmin_activity` | Détails d'une activité par ID |
| `garmin_sleep` | Données de sommeil |
| `garmin_steps` | Nombre de pas et objectif |
| `garmin_heart_rate` | Fréquence cardiaque |
| `garmin_body_battery` | Batterie corporelle |
| `garmin_stress` | Données de stress |
| `garmin_weight` | Mesures de poids |
| `garmin_devices` | Appareils enregistrés |

La plupart des outils acceptent `days_ago` (0 = aujourd'hui).

## Développement

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Avertissement

Ce projet utilise une bibliothèque non officielle pour Garmin Connect. L'authentification multi-facteurs (MFA) n'est pas supportée par ce connecteur. Utilisez un mot de passe dédié à ce service.
