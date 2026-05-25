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

## Politica di Linting

La configurazione ruff in `pyproject.toml` ignora due check di proposito:

- **`S110`** (`try-except-pass`): il codice ha diversi percorsi di shutdown e
  cleanup in cui ingoiare un'eccezione è il comportamento corretto — es.
  attendere un `asyncio.Task` già cancellato di cui abbiamo richiesto la
  cancellazione, o inviare la notifica "offline" durante lo shutdown quando la
  rete potrebbe già non esserci. Abilitare S110 forzerebbe `# noqa` ovunque
  senza alcun beneficio di sicurezza.
- **`SIM105`** (`use-contextlib-suppress`): preferenza stilistica — un
  `try/except/pass` esplicito si legge meglio di `with suppress(...)` in
  handler già brevi.

I test ignorano in più `S101` (assert), `S105`/`S106` (password/token hardcoded)
e `S108` (path hardcoded a `/tmp`) perché pytest richiede tutti questi pattern.

Se un futuro contributo introduce un'eccezione ingoiata che nasconde un bug
reale, il fix corretto è loggare l'errore o rilanciare — non riabilitare S110.
