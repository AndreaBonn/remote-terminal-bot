# Contributing

**[🇮🇹 Leggi in italiano](CONTRIBUTING.it.md)**

Contributions are welcome! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/AndreaBonn/remote-terminal-bot.git
cd remote-terminal-bot
uv sync          # Install all dependencies including dev
```

## Running Tests

```bash
uv run pytest                          # Run all tests
uv run pytest --cov --cov-report=html  # With coverage report
uv run ruff check .                    # Lint
uv run ruff format .                   # Format
uv run mypy src/                       # Type check
```

## Pull Request Guidelines

1. Fork the repository and create a feature branch
2. Write tests for new functionality — the project ships at **100% line and branch coverage** and CI enforces it; any new code path must be exercised by a behavioral test before the PR can merge
3. Run the full test suite before submitting
4. Follow existing code style (enforced by ruff)
5. Keep commits atomic with descriptive messages: `type(scope): description`

## Commit Types

`feat` `fix` `chore` `docs` `refactor` `test` `perf` `ci`

## Linting Policy

The ruff configuration in `pyproject.toml` ignores two checks intentionally:

- **`S110`** (`try-except-pass`): the codebase has several shutdown and cleanup
  paths where swallowing an exception is the correct behavior — e.g. awaiting a
  cancelled `asyncio.Task` that we already requested to cancel, or sending an
  "offline" notification during shutdown when the network might already be gone.
  Enabling S110 would force `# noqa` comments at every such site without any
  safety benefit.
- **`SIM105`** (`use-contextlib-suppress`): stylistic preference — explicit
  `try/except/pass` reads more clearly than `with suppress(...)` in handlers
  that are already short.

Tests additionally ignore `S101` (asserts), `S105`/`S106` (hardcoded passwords),
and `S108` (hardcoded `/tmp` paths) because pytest needs all of them.

If a future contribution introduces a swallowed exception that hides a real
bug, the right fix is to log the error or re-raise — not to re-enable S110.
