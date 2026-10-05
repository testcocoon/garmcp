#!/usr/bin/env bash
# Installe l'environnement Python et démarre le serveur MCP Garmin (garmcp).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${GARMCP_VENV:-$SCRIPT_DIR/.venv}"

[ ! -e $SCRIPT_DIR/garmin_user.env ] || source $SCRIPT_DIR/garmin_user.env 

command -v python3 >/dev/null 2>&1 || {
    echo "Erreur : python3 n'est pas installé." >&2
    exit 1
}

# 1. Création de l'environnement virtuel
if [ ! -d "$VENV_DIR" ]; then
    echo "Création de l'environnement virtuel dans $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 2. Mise à jour de pip (silencieuse, non bloquante)
pip install --upgrade pip --quiet 2>/dev/null || true

# 3. Installation du paquet garmcp (et de ses dépendances)
echo "Installation des dépendances ..."
pip install --quiet --editable "$SCRIPT_DIR"

# 4. Vérification des identifiants (optionnels si tokens déjà présents)
if [ -z "${GARMIN_EMAIL:-}" ] || [ -z "${GARMIN_PASSWORD:-}" ]; then
    if [ ! -f "${GARMCP_TOKEN_DIR:-$HOME/.garmcp}/garmin_tokens.json" ]; then
        echo "Avertissement : GARMIN_EMAIL et GARMIN_PASSWORD ne sont pas définis" >&2
        echo "et aucun token sauvegardé n'a été trouvé." >&2
        echo "Définissez-les avant la première connexion, par exemple :" >&2
        echo '  export GARMIN_EMAIL="vous@example.com"' >&2
        echo '  export GARMIN_PASSWORD="votre-mot-de-passe"' >&2
    fi
fi

# 5. Démarrage du serveur MCP (transport stdio)
echo "Démarrage du serveur MCP garmcp (stdio) ..."
exec garmcp
#exec garmcp --login
