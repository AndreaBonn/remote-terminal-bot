"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Raised when application configuration is invalid or missing."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Configuration error: {message}")


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    """Immutable application settings validated at startup."""

    bot_token: str
    authorized_chat_id: int
    machine_name: str
    command_timeout: int = 30
    heartbeat_enabled: bool = True
    heartbeat_interval: int = 60
    log_level: str = "INFO"

    def __repr__(self) -> str:
        return (
            f"Settings(machine_name={self.machine_name!r}, "
            f"authorized_chat_id={self.authorized_chat_id}, "
            f"bot_token=***REDACTED***)"
        )

    _MAX_COMMAND_TIMEOUT: int = 300
    _MAX_HEARTBEAT_INTERVAL: int = 3600

    _VALID_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def __post_init__(self) -> None:
        if not self.bot_token:
            _fatal("TELEGRAM_BOT_TOKEN is required")
        if self.authorized_chat_id <= 0:
            _fatal("AUTHORIZED_CHAT_ID must be a positive integer")
        if not self.machine_name:
            _fatal("MACHINE_NAME is required")
        if self.command_timeout <= 0:
            _fatal("COMMAND_TIMEOUT must be positive")
        if self.command_timeout > self._MAX_COMMAND_TIMEOUT:
            _fatal(f"COMMAND_TIMEOUT max allowed: {self._MAX_COMMAND_TIMEOUT}s")
        if self.heartbeat_enabled:
            if self.heartbeat_interval <= 0:
                _fatal("HEARTBEAT_INTERVAL must be positive")
            if self.heartbeat_interval > self._MAX_HEARTBEAT_INTERVAL:
                _fatal(f"HEARTBEAT_INTERVAL max allowed: {self._MAX_HEARTBEAT_INTERVAL}s")
        if self.log_level not in self._VALID_LOG_LEVELS:
            _fatal(f"LOG_LEVEL must be one of {self._VALID_LOG_LEVELS}, got: {self.log_level!r}")


def load_settings(env_path: Path | None = None) -> Settings:
    """Load and validate settings from .env file.

    Parameters
    ----------
    env_path : Path | None
        Explicit path to .env file. If None, searches current directory.

    Returns
    -------
    Settings
        Validated, immutable configuration object.
    """
    dotenv_path = env_path or Path.cwd() / ".env"
    if not dotenv_path.exists():
        _fatal(f".env file not found at {dotenv_path}")

    load_dotenv(dotenv_path)

    chat_id = _parse_int_env("AUTHORIZED_CHAT_ID", 0)
    command_timeout = _parse_int_env("COMMAND_TIMEOUT", 30)
    heartbeat_interval = _parse_int_env("HEARTBEAT_INTERVAL", 60)

    heartbeat_enabled = _parse_bool_env("HEARTBEAT_ENABLED", default=True)

    return Settings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        authorized_chat_id=chat_id,
        machine_name=os.getenv("MACHINE_NAME", "").strip().lower(),
        command_timeout=command_timeout,
        heartbeat_enabled=heartbeat_enabled,
        heartbeat_interval=heartbeat_interval,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )


def _parse_int_env(key: str, default: int) -> int:
    """Parse an integer environment variable, raising ConfigurationError on failure."""
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except ValueError:
        _fatal(f"{key} must be an integer, got: {raw!r}")
        return default  # pragma: no cover — unreachable, satisfies type checker


def _parse_bool_env(key: str, *, default: bool) -> bool:
    """Parse a boolean environment variable (true/false, yes/no, 1/0)."""
    raw = os.getenv(key, str(default)).strip().lower()
    if raw in ("true", "yes", "1"):
        return True
    if raw in ("false", "no", "0"):
        return False
    _fatal(f"{key} must be true/false, got: {raw!r}")
    return default  # pragma: no cover — unreachable, satisfies type checker


def _fatal(message: str) -> None:
    """Raise ConfigurationError for invalid settings."""
    raise ConfigurationError(message)
