#!/usr/bin/env bash
set -euo pipefail

# Telegram Terminal Bot — Installation Script
# Supports Ubuntu/Xubuntu with Python 3.10+

INSTALL_DIR="${HOME}/telegram-terminal-bot"
VENV_DIR="${INSTALL_DIR}/.venv"
SERVICE_NAME="telegram-terminal-bot@${USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1" >&2; exit 1; }

# --- Pre-flight checks ---

echo "═════════════════════════��═════════════════════"
echo "  Telegram Terminal Bot — Installer"
echo "══════════════════════════════════���════════════"
echo ""

# Check Python version
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python 3.10+ non trovato. Installa con: sudo apt install python3.10"
fi
info "Python trovato: $PYTHON_CMD ($($PYTHON_CMD --version))"

# --- Installation ---

# Create install directory (sync project files, remove stale)
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    rsync -a --delete "$SCRIPT_DIR"/src/ "$INSTALL_DIR/src/"
    rsync -a "$SCRIPT_DIR"/pyproject.toml "$INSTALL_DIR/"
    rsync -a "$SCRIPT_DIR"/uv.lock "$INSTALL_DIR/" 2>/dev/null || true
    mkdir -p "$INSTALL_DIR/systemd"
    rsync -a "$SCRIPT_DIR"/systemd/*.service "$INSTALL_DIR/systemd/" 2>/dev/null || true
    info "File progetto sincronizzati in $INSTALL_DIR"
else
    info "Esecuzione dalla directory di installazione"
fi

# Install dependencies — require uv for deterministic builds
if command -v uv &>/dev/null; then
    cd "$INSTALL_DIR"
    uv sync --frozen --no-dev
    info "Dipendenze installate (uv sync)"
else
    warn "uv non trovato — installazione automatica..."
    curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
    chmod +x /tmp/uv-install.sh
    sh /tmp/uv-install.sh
    rm -f /tmp/uv-install.sh
    export PATH="$HOME/.local/bin:$PATH"
    if command -v uv &>/dev/null; then
        cd "$INSTALL_DIR"
        uv sync --frozen --no-dev
        info "uv installato e dipendenze sincronizzate"
    else
        error "Impossibile installare uv. Installa manualmente: https://docs.astral.sh/uv/getting-started/installation/"
    fi
fi

# Create .env if not exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    warn "File .env creato — CONFIGURALO prima di avviare il bot"
else
    info "File .env esistente (non sovrascritto)"
fi

# Install systemd service
SERVICE_FILE="/etc/systemd/system/telegram-terminal-bot@.service"
if [ -f "$SCRIPT_DIR/systemd/telegram-terminal-bot@.service" ]; then
    if sudo cp "$SCRIPT_DIR/systemd/telegram-terminal-bot@.service" "$SERVICE_FILE"; then
        sudo systemctl daemon-reload
        info "Servizio systemd installato"
    else
        warn "Impossibile installare servizio systemd (serve sudo)"
    fi
fi

# --- Post-install instructions ---

echo ""
echo "════════════════════════════════���══════════════"
echo "  Installazione completata!"
echo "═════════════════════════════���═════════════════"
echo ""
echo "Prossimi passi:"
echo ""
echo "  1. Configura il file .env:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Inserisci:"
echo "     - TELEGRAM_BOT_TOKEN (da @BotFather)"
echo "     - AUTHORIZED_CHAT_ID (da @userinfobot)"
echo "     - MACHINE_NAME (nome univoco per questo PC)"
echo ""
echo "  3. Avvia il bot:"
echo "     sudo systemctl enable --now ${SERVICE_NAME}"
echo ""
echo "  4. Verifica:"
echo "     sudo systemctl status ${SERVICE_NAME}"
echo "     journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "  Per eseguire manualmente:"
echo "     cd $INSTALL_DIR && .venv/bin/python -m src.bot"
echo ""
