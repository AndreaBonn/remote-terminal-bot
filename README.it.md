# Telegram Terminal Bot

> Controlla terminali remoti dal tuo smartphone via Telegram. Multi-PC, sessioni persistenti, zero infrastruttura.

[![CI](https://github.com/bonn/telegram-terminal-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/bonn/telegram-terminal-bot/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**[🇬🇧 Read in English](README.md)**

---

## Perché?

SSH dal telefono è scomodo. Le VPN richiedono infrastruttura. Questo bot ti dà una shell persistente completa su qualsiasi tua macchina — direttamente da Telegram.

**Differenziatore chiave:** Nessun server centrale. Telegram stesso funge da message bus. Più PC condividono lo stesso bot token, si coordinano via heartbeat broadcast, e tu passi da uno all'altro con un singolo comando.

## Architettura

```
┌─────────────┐     ┌─────────────┐
│ Tu (telefono)────▶│ Telegram API │
└─────────────┘     └──────┬──────┘
                           │ long polling
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Bot PC-1 │ │ Bot PC-2 │ │ Bot PC-N │
        │ (attivo) │ │ (standby)│ │ (standby)│
        └────┬─────┘ └──────────┘ └──────────┘
             │
        ┌────▼─────┐
        │  bash    │  ← sessione persistente
        │ subprocess│    (mantiene cwd, env)
        └──────────┘
```

Ogni PC esegue lo stesso bot token. Solo il PC **attivo** esegue comandi. Gli altri ascoltano silenziosamente e tracciano gli heartbeat per sapere chi è online.

## Funzionalità

- **Shell persistente** — directory di lavoro e ambiente sopravvivono tra i comandi
- **Switch multi-PC** — `/activate desktop`, `/activate laptop`, switch istantaneo
- **Scoperta peer** — automatica via heartbeat Telegram (no DNS, no porte, no VPN)
- **Protezione timeout** — comandi terminati dopo timeout configurabile, sessione auto-respawn
- **Rate limiting** — max 30 comandi/minuto, output limitato a 512KB
- **Sicurezza** — singolo chat ID autorizzato, no `shell=True`, systemd hardened
- **Zero dipendenze** oltre Python e Telegram

## Quick Start

### Prerequisiti

- Python 3.10+
- Un token bot Telegram (da [@BotFather](https://t.me/BotFather))
- Il tuo chat ID (da [@userinfobot](https://t.me/userinfobot))

### Installazione

```bash
# Clona
git clone https://github.com/bonn/telegram-terminal-bot.git
cd telegram-terminal-bot

# Installa (raccomandato: uv)
uv sync

# Oppure usa l'installer automatico
./scripts/install.sh
```

### Configurazione

```bash
cp .env.example .env
nano .env
```

```env
TELEGRAM_BOT_TOKEN=il_tuo_token_bot
AUTHORIZED_CHAT_ID=il_tuo_chat_id
MACHINE_NAME=il-mio-desktop
COMMAND_TIMEOUT=30
HEARTBEAT_INTERVAL=60
```

### Avvio

```bash
# Diretto
uv run python -m src.bot

# Oppure come servizio systemd (auto-start al boot)
sudo systemctl enable --now telegram-terminal-bot@$USER
```

## Utilizzo

| Comando | Descrizione |
|---------|-------------|
| `/activate <nome>` | Cambia PC attivo |
| `/list` | Mostra PC online con ultimo heartbeat |
| `/status` | PC corrente e directory di lavoro |
| `/cancel` | Invia SIGINT al comando in esecuzione |
| `/help` | Mostra comandi disponibili |
| *qualsiasi testo* | Esegui come comando shell sul PC attivo |

### Sessione di esempio

```
Tu: /activate desktop
Bot: ✅ PC attivo: desktop

Tu: pwd
Bot: /home/user

Tu: ls -la ~/projects
Bot: [output...]

Tu: /activate laptop
Bot: ✅ PC attivo: laptop

Tu: docker ps
Bot: [output dal laptop...]
```

## Modello di Sicurezza

| Layer | Protezione |
|-------|-----------|
| Autorizzazione | Singolo `AUTHORIZED_CHAT_ID` — solo la tua chat può eseguire comandi |
| Rate limiting | Max 30 comandi/minuto |
| Output cap | 512KB max per output comando (previene OOM) |
| Timeout | Timeout per-comando configurabile con escalation SIGKILL |
| Systemd | `NoNewPrivileges`, `ProtectSystem=strict`, protezione kernel tunable |
| Segreti | Bot token in `.env` con `chmod 600`, mai loggato |

> **Importante:** Questo bot fornisce accesso shell completo. Il perimetro di sicurezza è il tuo account Telegram. Abilita 2FA su Telegram e mantieni sicuro il file `.env`.

## Struttura Progetto

```
src/
├── bot.py              # Lifecycle applicazione, heartbeat, polling
├── config.py           # Settings immutabili da .env
├── handlers.py         # Handler comandi Telegram (DI via closure)
├── shell_session.py    # Gestione subprocess bash persistente
├── state_manager.py    # Coordinamento multi-PC
└── utils.py            # Formattazione messaggi e splitting
tests/                  # Test unitari e di integrazione
scripts/install.sh      # Installer automatico
systemd/                # Template servizio per deploy multi-utente
```

## Decisioni di Design

1. **DI via closure** — `create_handlers()` inietta dipendenze senza framework DI
2. **Telegram come message bus** — gli heartbeat sono messaggi normali, filtrati e cancellati. Zero infrastruttura.
3. **Pattern end marker** — i comandi sono delimitati da un marker crittografico (`secrets.token_hex(16)`) per parsare i confini dell'output in modo affidabile
4. **Scritture atomiche dello stato** — `state.json` usa write-tmp-then-rename per prevenire corruzione
5. **Isolamento process group** — `start_new_session=True` abilita SIGKILL pulito di interi alberi di processi al timeout

## Sviluppo

```bash
# Installa dipendenze dev
uv sync

# Esegui test
uv run pytest

# Test con coverage
uv run pytest --cov --cov-report=term-missing

# Lint
uv run ruff check .
uv run ruff format --check .
```

## Licenza

[MIT](LICENSE)
