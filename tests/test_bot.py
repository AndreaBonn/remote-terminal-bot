"""Tests for bot application setup and configuration."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.bot import setup_logging
from src.config import ConfigurationError


class TestSetupLogging:
    """Logging configuration tests."""

    def test_setup_logging_silences_noisy_libs(self) -> None:
        setup_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("telegram").level == logging.WARNING


class TestBuildApplication:
    """Application build tests."""

    def test_missing_env_raises_configuration_error(self, tmp_path: Path) -> None:
        from src.bot import build_application

        with pytest.raises(ConfigurationError):
            build_application(env_path=tmp_path / ".env")

    def test_builds_with_valid_env(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=123:FAKE\nAUTHORIZED_CHAT_ID=99999\nMACHINE_NAME=test-pc\n",
        )
        from src.bot import build_application

        app = build_application(env_path=env_file)
        assert app.bot_data["settings"].machine_name == "test-pc"
        assert app.bot_data["shell"] is not None
        assert app.bot_data["state"] is not None
