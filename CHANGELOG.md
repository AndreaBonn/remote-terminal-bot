# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-04-20

### Added
- Rate limiting (max 30 commands/minute) to prevent abuse
- Output cap (512KB) to prevent memory exhaustion
- PC name validation in `/activate` command
- Global error handler for unhandled exceptions
- Systemd service hardening (kernel protection, address family restrictions)
- `ConfigurationError` custom exception for testable startup validation
- GitHub Actions CI pipeline (lint + test + coverage)
- `LOG_LEVEL` environment variable for configurable logging
- MIT License
- CHANGELOG.md

### Changed
- End marker entropy increased from 8 to 16 bytes (brute-force resistant)
- `state.json` writes are now atomic (write tmp + rename)
- `install.sh` uses `uv sync --frozen` when available, falls back to pinned pip
- Replaced `assert` statements with proper guard clauses
- Systemd service includes `StartLimitBurst`, `TimeoutStopSec`, and kernel hardening
- Improved log format (ISO timestamps, module name included)
- Command logging no longer exposes command content at INFO level

### Fixed
- Shell session respawn no longer crashes if process streams are unavailable

## [1.0.0] - 2026-04-19

### Added
- Initial release
- Multi-PC remote terminal control via Telegram
- Persistent bash session with working directory tracking
- Heartbeat-based peer discovery (no central server)
- Automatic timeout and session respawn
- Systemd service template for multi-user deployment
- Authorization via `AUTHORIZED_CHAT_ID`
