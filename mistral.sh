#!/usr/bin/env bash
# Démarre le serveur garmcp en HTTP streamable pour l'interfacer avec un
# connecteur personnalisé Mistral Chat (Vibe Work / Le Chat).
#
# Le serveur écoute en local ; l'URL à renseigner dans le connecteur
# Mistral Chat est affichée au démarrage.
#
# Variables d'environnement :
#   GARMCP_HOST          adresse d'écoute (défaut : 127.0.0.1)
#   GARMCP_PORT          port d'écoute     (défaut : 8000)
#   GARMIN_EMAIL         email du compte Garmin (optionnel si token déjà stocké)
#   GARMIN_PASSWORD      mot de passe       (optionnel si token déjà stocké)
#   GARMCP_VERBOSE       active les logs de debug (stderr)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${GARMCP_VENV:-$SCRIPT_DIR/.venv}"
[ ! -e $SCRIPT_DIR/garmin_user.env ] || source $SCRIPT_DIR/garmin_user.env 
HOST="${GARMCP_HOST:-127.0.0.1}"
PORT="${GARMCP_PORT:-8000}"

command -v python3 >/dev/null 2>&1 || {
    echo "Erreur : python3 n'est pas installé." >&2
    exit 1
}

# 1. Environnement virtuel + dépendances
if [ ! -d "$VENV_DIR" ]; then
    echo "Création de l'environnement virtuel dans $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet 2>/dev/null || true
echo "Installation des dépendances ..."
pip install --quiet --editable "$SCRIPT_DIR"

# 2. Vérifie l'existence d'un token ; sinon propose le --login interactif
TOKEN_FILE="${GARMCP_TOKEN_DIR:-$HOME/.garmcp}/garmin_tokens.json"
if [ ! -f "$TOKEN_FILE" ] && [ -z "${GARMIN_EMAIL:-}" ]; then
    echo "Aucun token trouvé ($TOKEN_FILE)." >&2
    echo "Lancez d'abord une connexion interactive pour stocker le token :" >&2
    echo "  garmcp --login" >&2
fi

# 3. Démarre le serveur HTTP streamable (premier plan)
echo ""
echo "=== Serveur MCP garmcp pour connecteur Mistral Chat ==="
echo "URL du connecteur : http://$HOST:$PORT/mcp"
echo "Dans Mistral Chat / Work : Connecteurs > + Ajouter un connecteur >"
echo "Connecteur MCP personnalisé, et renseignez l'URL ci-dessus."
echo "Arrêtez avec Ctrl+C."
echo ""
exec garmcp --http --host "$HOST" --port "$PORT"
