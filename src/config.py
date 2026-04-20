"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    """Immutable application settings validated at startup."""

    bot_token: str
    authorized_chat_id: int
    machine_name: str
    command_timeout: int = 30
    heartbeat_interval: int = 60

    def __repr__(self) -> str:
        return (
            f"Settings(machine_name={self.machine_name!r}, "
            f"authorized_chat_id={self.authorized_chat_id}, "
            f"bot_token=***REDACTED***)"
        )

    def __post_init__(self) -> None:
        if not self.bot_token:
            _fatal("TELEGRAM_BOT_TOKEN is required")
        if self.authorized_chat_id <= 0:
            _fatal("AUTHORIZED_CHAT_ID must be a positive integer")
        if not self.machine_name:
            _fatal("MACHINE_NAME is required")
        if self.command_timeout <= 0:
            _fatal("COMMAND_TIMEOUT must be positive")
        if self.heartbeat_interval <= 0:
            _fatal("HEARTBEAT_INTERVAL must be positive")


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

    try:
        chat_id = int(os.getenv("AUTHORIZED_CHAT_ID", "0"))
    except ValueError:
        _fatal("AUTHORIZED_CHAT_ID must be an integer")
        chat_id = 0  # unreachable, satisfies type checker

    return Settings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        authorized_chat_id=chat_id,
        machine_name=os.getenv("MACHINE_NAME", ""),
        command_timeout=int(os.getenv("COMMAND_TIMEOUT", "30")),
        heartbeat_interval=int(os.getenv("HEARTBEAT_INTERVAL", "60")),
    )


def _fatal(message: str) -> None:
    """Print error and exit. Used only during startup validation."""
    print(f"[FATAL] Configuration error: {message}", file=sys.stderr)
    sys.exit(1)
