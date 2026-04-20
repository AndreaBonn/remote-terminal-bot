# Come Contribuire

**[🇬🇧 Read in English](CONTRIBUTING.md)**

I contributi sono benvenuti! Ecco come iniziare.

## Setup di Sviluppo

```bash
git clone https://github.com/AndreaBonn/remote-terminal-bot.git
cd remote-terminal-bot
uv sync          # Installa tutte le dipendenze incluse quelle dev
```

## Eseguire i Test

```bash
uv run pytest                          # Esegui tutti i test
uv run pytest --cov --cov-report=html  # Con report di copertura
uv run ruff check .                    # Lint
uv run ruff format .                   # Formattazione
uv run mypy src/                       # Type check
```

## Linee Guida per le Pull Request

1. Fai un fork del repository e crea un branch per la feature
2. Scrivi test per le nuove funzionalità (mantieni >70% di copertura)
3. Esegui l'intera suite di test prima di inviare
4. Segui lo stile di codice esistente (enforced da ruff)
5. Mantieni i commit atomici con messaggi descrittivi: `tipo(scope): descrizione`

## Tipi di Commit

`feat` `fix` `chore` `docs` `refactor` `test` `perf` `ci`
