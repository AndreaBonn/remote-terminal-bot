# Telegram Terminal Bot

## Progetto
Bot Telegram per controllare terminali remoti da smartphone. Multi-PC, sessione persistente.

## Stack
- Python 3.10+, async
- python-telegram-bot v20 (async)
- python-dotenv
- uv per dependency management

## Struttura
```
src/
├── bot.py            # Entry point, application setup
├── config.py         # Settings from .env (pydantic-like dataclass)
├── shell_session.py  # Persistent bash subprocess
├── state_manager.py  # Multi-PC state coordination
├── handlers.py       # Telegram command handlers
└── utils.py          # Message formatting, text splitting
tests/                # Mirror di src/
scripts/install.sh    # Installer automatico
systemd/              # Service unit file
```

## Comandi
```bash
uv sync                    # Installa dipendenze
uv run python -m src.bot   # Avvia il bot
uv run pytest              # Esegui test
uv run ruff check .        # Lint
```

## Convenzioni
- Configurazione SOLO via .env (mai hardcoded)
- Security: autorizzazione via CHAT_ID, no shell=True
- Handler pattern: dependency injection via create_handlers()
- Heartbeat via messaggi Telegram (broadcast implicito)
