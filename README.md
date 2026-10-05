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

### Mode verbose (journalisation de débogage)

Par défaut, garmcp est silencieux (niveau WARNING). Un mode verbose optionnel écrit des informations de débogage (appels d'outils, flux de connexion, 2FA, sauvegarde des tokens...) **sur stderr** ou **vers syslog**, selon la configuration :

```bash
export GARMCP_VERBOSE=1        # active le mode debug
export GARMCP_LOG=syslog       # destination : "stderr" (défaut) ou "syslog"
export GARMCP_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING (défaut), ERROR
```

| Variable | Valeurs | Effet |
|---|---|---|
| `GARMCP_VERBOSE` | non vide | Force le niveau DEBUG (prioritaire sur `GARMCP_LOG_LEVEL`) |
| `GARMCP_LOG` | `stderr` (défaut), `syslog` | Destination des logs ; syslog utilise `/dev/log` |
| `GARMCP_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Niveau de log si `GARMCP_VERBOSE` est vide |

Les logs vont sur stderr, jamais sur stdout, afin de ne pas perturber le protocole MCP (stdio). Sous Mistral Vibe, ajoutez ces variables dans le bloc `env` du serveur MCP. Les valeurs invalides retombent silencieusement sur les défauts (`stderr`, `WARNING`).

En mode debug, les **requêtes de connexion** émises par `garminconnect`/`garth` sont également journalisées intégralement : stratégie de login essayée (`mobile+cffi`, `portal+requests`...), chargement des tokens, erreurs HTTP (429, 401...). Les en-têtes et valeurs sensibles (`Authorization`, `Cookie`, `mfaVerificationCode`, jetons CSRF) sont **automatiquement rédigés** (`<REDACTÉ>`) : aucun secret ne peut fuiter dans les logs.

> Après la première connexion, les tokens OAuth sont sauvegardés localement : les appels suivants n'ont plus besoin de l'email/mot de passe et ne les stockent jamais sur disque.

## Connexion initiale avec `--login`

Avant de démarrer le serveur, connectez-vous une fois en ligne de commande — le flux 2FA est interactif dans le terminal :

```bash
garmcp --login
```

```
Email Garmin : vous@example.com
Mot de passe Garmin : ********
Connexion à Garmin Connect...
Un code à 6 chiffres a été envoyé par email par Garmin.
Code 2FA : 123456
Token de connexion stocké : ~/.garmcp/garmin_tokens.json
Les prochaines connexions utiliseront ce token sans 2FA.
```

Le token OAuth est stocké localement (permissions 0600) : les connexions suivantes — y compris celles du serveur MCP — l'utilisent automatiquement, sans redemander email, mot de passe ni code 2FA.

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

### Mistral Vibe (CLI)

Le CLI Vibe Code se configure via `config.toml` ([documentation MCP servers](https://docs.mistral.ai/vibe/code/cli/mcp-servers)).

1. Installez le serveur localement :

```bash
git clone https://github.com/testcocoon/garmcp.git
cd garmcp
./start.sh   # crée .venv, installe les dépendances, démarre le serveur (Ctrl+C pour quitter)
```

2. Ouvrez votre configuration Vibe (`~/.vibe/config.toml` au niveau utilisateur, ou `./.vibe/config.toml` au niveau projet) et ajoutez :

```toml
[[mcp_servers]]
name = "garmcp"
transport = "stdio"
command = "/chemin/absolu/vers/garmcp/.venv/bin/garmcp"
env = { GARMIN_EMAIL = "vous@example.com", GARMIN_PASSWORD = "votre-mot-de-passe" }
```

> Alternativement, `command = "/chemin/absolu/vers/garmcp/start.sh"` fonctionne directement (le script crée le venv s'il n'existe pas encore).

3. Démarrez (ou redémarrez) Vibe, puis vérifiez que le serveur est bien chargé :

```
/mcp garmcp
```

Les outils sont exposés sous la forme `garmcp_<outil>` (ex. `garmcp_garmin_login`, `garmcp_garmin_activities`). Le flux 2FA fonctionne dans la session : appelez `garmin_login`, Garmin envoie le code par email, puis transmettez-le avec `garmin_mfa_verify`.

### Mistral Chat / Vibe Work (connecteur personnalisé)

Mistral Chat et Vibe Work peuvent se connecter à n'importe quel serveur MCP via un **connecteur personnalisé** ([documentation](https://docs.mistral.ai/vibe/work/connectors/mcp-connectors)). Le script `mistral.sh` démarre garmcp en serveur HTTP streamable et affiche l'URL à renseigner :

```bash
./mistral.sh
```

```
=== Serveur MCP garmcp pour connecteur Mistral Chat ===
URL du connecteur : http://127.0.0.1:8000/mcp
```

Dans Mistral Chat / Work : **Connecteurs > + Ajouter un connecteur > Connecteur MCP personnalisé**, puis renseignez l'URL affichée (`http://127.0.0.1:8000/mcp` par défaut).

Configuration :

| Variable | Défaut | Rôle |
|---|---|---|
| `GARMCP_HOST` | `127.0.0.1` | Adresse d'écoute |
| `GARMCP_PORT` | `8000` | Port d'écoute |

> **Si Mistral Chat refuse un `http://localhost`/`127.0.0.1`** : les connecteurs personnalisés exigent généralement une URL **publique en HTTPS**. Utilisez le reverse proxy Apache2 ci-dessous. Si le connecteur ne supporte pas `streamable-http`, le serveur gère aussi l'ancien transport SSE (`garmcp --sse` : `/sse` + `/messages/`), également proxyfié par la configuration Apache2.

## Intégration Apache2 (reverse proxy HTTPS pour Mistral Chat)

Mistral Chat n'accepte pas toujours une URL locale (`http://127.0.0.1:8000/mcp`), même accessible. La solution : exposer garmcp derrière Apache2 en HTTPS avec un nom de domaine, puis déclarer cette URL publique dans le connecteur.

Le dépôt fournit deux fichiers d'exemple :

- [`garmcp-apache.conf`](garmcp-apache.conf) — vhost Apache2 (reverse proxy HTTPS, proxyfie `/mcp` en streamable-http **et** `/sse`+`/messages/` en SSE, avec les réglages anti-buffering et timeouts longs requis par les sessions MCP)
- [`garmcp.service`](garmcp.service) — service systemd qui fait tourner `garmcp --http` en local

### Mise en place

```bash
# 1. Installer garmcp sur le serveur et faire un premier login (stocke le token)
sudo mkdir -p /opt/garmcp && sudo chown $USER /opt/garmcp
git clone https://github.com/testcocoon/garmcp.git /opt/garmcp
cd /opt/garmcp && ./start.sh   # prépare le venv, Ctrl+C après installation
garmcp --login                 # connexion 2FA, stocke le token

# 2. Service systemd
sudo cp garmcp.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now garmcp

# 3. Apache2 : modules + vhost
sudo a2enmod proxy proxy_http ssl headers
sudo cp garmcp-apache.conf /etc/apache2/sites-available/garmcp.conf
# éditer ServerName et les chemins de certificats (ex. Let's Encrypt)
sudo a2ensite garmcp
sudo apache2ctl configtest && sudo systemctl reload apache2
```

### Déclaration dans Mistral Chat

Connecteurs > **+ Ajouter un connecteur** > **Connecteur MCP personnalisé** :

- URL : `https://garmcp.example.com/mcp` (transport streamable-http, recommandé)
- Si le connecteur utilise l'ancien transport SSE : `https://garmcp.example.com/sse`

### Points importants de la configuration Apache2

| Réglage | Raison |
|---|---|
| HTTPS + certificat valide | Mistral Chat exige une URL publique sécurisée |
| `ProxyPreserveHost On` | Le serveur génère des URLs de callback correctes |
| `ProxyTimeout 3600` | Les sessions MCP restent ouvertes longtemps |
| `SetEnv proxy-sendchunked` | Évite le buffering des réponses SSE/streaming |
| `RequestHeader unset Accept-Encoding` (sur `/sse`) | La compression casserait le flux SSE |

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
