"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import ConfigurationError, Settings, load_settings


class TestSettings:
    """Validation rules for Settings dataclass."""

    def test_valid_settings_creates_instance(self) -> None:
        settings = Settings(
            bot_token="123:ABC",
            authorized_chat_id=12345,
            machine_name="desktop",
        )
        assert settings.bot_token == "123:ABC"
        assert settings.machine_name == "desktop"
        assert settings.command_timeout == 30
        assert settings.heartbeat_interval == 60

    def test_empty_token_exits(self) -> None:
        with pytest.raises(ConfigurationError):
            Settings(bot_token="", authorized_chat_id=1, machine_name="pc")

    def test_zero_chat_id_exits(self) -> None:
        with pytest.raises(ConfigurationError):
            Settings(bot_token="tok", authorized_chat_id=0, machine_name="pc")

    def test_negative_chat_id_exits(self) -> None:
        with pytest.raises(ConfigurationError):
            Settings(bot_token="tok", authorized_chat_id=-1, machine_name="pc")

    def test_empty_machine_name_exits(self) -> None:
        with pytest.raises(ConfigurationError):
            Settings(bot_token="tok", authorized_chat_id=1, machine_name="")

    def test_zero_timeout_exits(self) -> None:
        with pytest.raises(ConfigurationError):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                command_timeout=0,
            )

    def test_timeout_exceeds_max_exits(self) -> None:
        with pytest.raises(ConfigurationError, match="max allowed"):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                command_timeout=600,
            )

    def test_heartbeat_exceeds_max_exits(self) -> None:
        with pytest.raises(ConfigurationError, match="max allowed"):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                heartbeat_interval=7200,
            )

    def test_valid_log_level_accepted(self) -> None:
        settings = Settings(
            bot_token="tok",
            authorized_chat_id=1,
            machine_name="pc",
            log_level="DEBUG",
        )
        assert settings.log_level == "DEBUG"

    def test_invalid_log_level_exits(self) -> None:
        with pytest.raises(ConfigurationError, match="LOG_LEVEL"):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                log_level="VERBOSE",
            )

    def test_settings_are_immutable(self) -> None:
        settings = Settings(
            bot_token="tok",
            authorized_chat_id=1,
            machine_name="pc",
        )
        with pytest.raises(AttributeError):
            settings.machine_name = "other"  # type: ignore[misc]

    def test_repr_redacts_bot_token(self) -> None:
        settings = Settings(
            bot_token="super-secret-token-12345",
            authorized_chat_id=42,
            machine_name="pc",
        )
        rendered = repr(settings)
        assert "super-secret-token-12345" not in rendered
        assert "***REDACTED***" in rendered
        assert "pc" in rendered
        assert "42" in rendered

    def test_audit_log_enabled_defaults_to_true(self) -> None:
        settings = Settings(
            bot_token="tok",
            authorized_chat_id=1,
            machine_name="pc",
        )
        assert settings.audit_log_enabled is True

    def test_audit_log_can_be_disabled(self) -> None:
        settings = Settings(
            bot_token="tok",
            authorized_chat_id=1,
            machine_name="pc",
            audit_log_enabled=False,
        )
        assert settings.audit_log_enabled is False

    def test_heartbeat_disabled_skips_interval_validation(self) -> None:
        settings = Settings(
            bot_token="tok",
            authorized_chat_id=1,
            machine_name="pc",
            heartbeat_enabled=False,
            heartbeat_interval=999999,
        )
        assert settings.heartbeat_enabled is False
        assert settings.heartbeat_interval == 999999

    def test_zero_heartbeat_interval_raises_when_enabled(self) -> None:
        with pytest.raises(ConfigurationError, match="HEARTBEAT_INTERVAL must be positive"):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                heartbeat_enabled=True,
                heartbeat_interval=0,
            )

    def test_negative_heartbeat_interval_raises_when_enabled(self) -> None:
        with pytest.raises(ConfigurationError, match="HEARTBEAT_INTERVAL must be positive"):
            Settings(
                bot_token="tok",
                authorized_chat_id=1,
                machine_name="pc",
                heartbeat_enabled=True,
                heartbeat_interval=-5,
            )


class TestLoadSettings:
    """Loading from .env files."""

    def test_missing_env_file_exits(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            load_settings(env_path=tmp_path / ".env")

    def test_loads_valid_env_file(self, tmp_path: Path, monkeypatch) -> None:
        # Clear env vars that may leak from other tests
        for key in ("TELEGRAM_BOT_TOKEN", "AUTHORIZED_CHAT_ID", "MACHINE_NAME", "COMMAND_TIMEOUT"):
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test-token\n"
            "AUTHORIZED_CHAT_ID=99999\n"
            "MACHINE_NAME=testpc\n"
            "COMMAND_TIMEOUT=45\n",
        )
        settings = load_settings(env_path=env_file)
        assert settings.bot_token == "test-token"
        assert settings.authorized_chat_id == 99999
        assert settings.machine_name == "testpc"
        assert settings.command_timeout == 45

    def test_non_integer_timeout_exits(self, tmp_path: Path, monkeypatch) -> None:
        for key in ("TELEGRAM_BOT_TOKEN", "AUTHORIZED_CHAT_ID", "MACHINE_NAME", "COMMAND_TIMEOUT"):
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test-token\n"
            "AUTHORIZED_CHAT_ID=99999\n"
            "MACHINE_NAME=testpc\n"
            "COMMAND_TIMEOUT=abc\n",
        )
        with pytest.raises(ConfigurationError, match="must be an integer"):
            load_settings(env_path=env_file)

    def test_machine_name_normalized_to_lowercase(self, tmp_path: Path, monkeypatch) -> None:
        for key in ("TELEGRAM_BOT_TOKEN", "AUTHORIZED_CHAT_ID", "MACHINE_NAME", "COMMAND_TIMEOUT"):
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test-token\nAUTHORIZED_CHAT_ID=99999\nMACHINE_NAME=MyDesktop\n",
        )
        settings = load_settings(env_path=env_file)
        assert settings.machine_name == "mydesktop"


class TestParseBoolEnv:
    """Boolean env parsing — covers HEARTBEAT_ENABLED and similar flags."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch, tmp_path: Path) -> Path:
        for key in (
            "TELEGRAM_BOT_TOKEN",
            "AUTHORIZED_CHAT_ID",
            "MACHINE_NAME",
            "HEARTBEAT_ENABLED",
            "HEARTBEAT_INTERVAL",
            "AUDIT_LOG_ENABLED",
            "COMMAND_TIMEOUT",
            "LOG_LEVEL",
        ):
            monkeypatch.delenv(key, raising=False)
        return tmp_path

    def _env_file(self, tmp_path: Path, extra: str) -> Path:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=tok\nAUTHORIZED_CHAT_ID=1\nMACHINE_NAME=pc\n" + extra,
        )
        return env_file

    @pytest.mark.parametrize("value", ["false", "FALSE", "no", "NO", "0"])
    def test_false_values_disable_heartbeat(self, tmp_path: Path, value: str) -> None:
        env_file = self._env_file(tmp_path, f"HEARTBEAT_ENABLED={value}\n")
        settings = load_settings(env_path=env_file)
        assert settings.heartbeat_enabled is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "yes", "YES", "1"])
    def test_true_values_enable_heartbeat(self, tmp_path: Path, value: str) -> None:
        env_file = self._env_file(tmp_path, f"HEARTBEAT_ENABLED={value}\n")
        settings = load_settings(env_path=env_file)
        assert settings.heartbeat_enabled is True

    def test_invalid_bool_value_raises_with_message(self, tmp_path: Path) -> None:
        env_file = self._env_file(tmp_path, "HEARTBEAT_ENABLED=maybe\n")
        with pytest.raises(ConfigurationError, match="HEARTBEAT_ENABLED.*must be true/false"):
            load_settings(env_path=env_file)

    def test_audit_log_enabled_false_via_env(self, tmp_path: Path) -> None:
        env_file = self._env_file(tmp_path, "AUDIT_LOG_ENABLED=false\n")
        settings = load_settings(env_path=env_file)
        assert settings.audit_log_enabled is False

    def test_audit_log_enabled_defaults_true_when_unset(self, tmp_path: Path) -> None:
        env_file = self._env_file(tmp_path, "")
        settings = load_settings(env_path=env_file)
        assert settings.audit_log_enabled is True
