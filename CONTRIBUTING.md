# Contributing

Contributions are welcome! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/bonn/telegram-terminal-bot.git
cd telegram-terminal-bot
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
2. Write tests for new functionality (maintain >70% coverage)
3. Run the full test suite before submitting
4. Follow existing code style (enforced by ruff)
5. Keep commits atomic with descriptive messages: `type(scope): description`

## Commit Types

`feat` `fix` `chore` `docs` `refactor` `test` `perf` `ci`
