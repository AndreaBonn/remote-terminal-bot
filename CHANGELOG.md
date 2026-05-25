# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docs/SECURITY.md` Threat Model section: trust boundary, shared-token
  consequences across N PCs, manual token rotation procedure, out-of-scope
  risks.
- `CONTRIBUTING.md` Linting Policy section documenting why ruff `S110` and
  `SIM105` are intentionally disabled.

### Changed
- `README.md` "Why not Docker?" rewritten to address the privileged-container
  counter-argument and frame the choice as fit-for-purpose rather than
  container-escape avoidance.

### Fixed
- `src/bot.py`: removed stale `# noqa: F401` on `import re` — `re.escape()`
  is used explicitly in `filters.Regex`.
- `src/bot.py`: hoisted `AuditLog` import to module top; the previous
  function-local import had no documented cycle-avoidance reason.

### Internal
- `src/shell_session.py`: documented the 100 ms per-line stderr-drain timeout.
- `src/handlers.py`: documented the single-deque rate-limit design and the
  invariant it relies on.

## [1.0.0] — 2026-05-25

First stable release. Production-ready for personal multi-PC setups.

### Added
- Persistent bash subprocess with cwd preservation across commands
  (`src/shell_session.py`).
- Multi-PC coordination via Telegram broadcast — no central server, no
  open ports, no VPN (`src/state_manager.py`).
- Telegram command surface: `/activate`, `/list`, `/status`, `/cancel`,
  `/help`, plus free-form shell input (`src/handlers.py`).
- Append-only JSONL audit log at
  `~/.local/share/telegram-terminal-bot/audit.jsonl` (`src/audit_log.py`).
- Heartbeat broadcast with `HEARTBEAT_ENABLED` toggle for single-PC
  deployments.
- Configuration via `.env` parsed into an immutable frozen dataclass with
  `__post_init__` validation; token redacted in `__repr__`.
- systemd service template with kernel-level hardening
  (`NoNewPrivileges`, `ProtectSystem=strict`, `CapabilityBoundingSet=`,
  `SystemCallFilter=@system-service`, `RestrictNamespaces`, memory/CPU
  quotas) in `systemd/telegram-terminal-bot@.service`.
- Automated installer script (`scripts/install.sh`) with uv-based dependency
  resolution.
- Bilingual documentation: README, SECURITY, CONTRIBUTING, installation
  guide (English + Italian).
- Test suite: 166 tests, 100% line and branch coverage measured by
  `pytest-cov`.
- CI on GitHub Actions: ruff (lint + format), mypy `strict`, `pip-audit`,
  pytest with coverage upload to Codecov. Actions pinned by commit SHA.

### Security
- Single-`AUTHORIZED_CHAT_ID` authorization; unauthorized chats are
  silently rejected and logged.
- Private-chat-only enforcement: group messages are ignored.
- Rate limit of 30 commands/minute and per-command length cap of 2048
  characters.
- Output capped at 512 KB per command; commands killed with SIGTERM →
  SIGKILL after a configurable timeout (default 30 s, hard cap 300 s).
- Shell session reset after 30 minutes of inactivity.
- Subprocess spawned with `exec` argument lists only (no `shell=True`),
  `--norc --noprofile`, and `start_new_session=True` for process-group
  cleanup.
- Cryptographic per-command end markers via `secrets.token_hex(16)` to
  prevent marker-injection through user output.

[Unreleased]: https://github.com/AndreaBonn/remote-terminal-bot/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/AndreaBonn/remote-terminal-bot/releases/tag/v1.0.0
