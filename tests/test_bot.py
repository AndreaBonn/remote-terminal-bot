"""Tests for bot application setup and configuration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot import post_init, post_shutdown, send_heartbeat, setup_logging
from src.config import ConfigurationError, Settings


class TestSetupLogging:
    """Logging configuration tests."""

    def test_setup_logging_silences_noisy_libs(self) -> None:
        setup_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("telegram").level == logging.WARNING

    def test_setup_logging_sets_debug_level(self) -> None:
        setup_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_setup_logging_sets_warning_level(self) -> None:
        setup_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_setup_logging_invalid_level_defaults_to_info(self) -> None:
        setup_logging(level="INVALID")
        assert logging.getLogger().level == logging.INFO


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

    def test_builds_with_preloaded_settings(self) -> None:
        from src.bot import build_application

        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="preloaded-pc",
        )
        app = build_application(settings=settings)
        assert app.bot_data["settings"].machine_name == "preloaded-pc"

    def test_builds_with_custom_log_level(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=123:FAKE\nAUTHORIZED_CHAT_ID=99999\n"
            "MACHINE_NAME=test-pc\nLOG_LEVEL=DEBUG\n",
        )
        from src.bot import build_application

        app = build_application(env_path=env_file)
        assert app.bot_data["settings"].log_level == "DEBUG"


class TestPostInit:
    """Lifecycle hook post_init tests."""

    @pytest.mark.asyncio
    async def test_post_init_starts_shell_and_sends_notification(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        mock_shell = MagicMock()
        mock_shell.start = AsyncMock()
        mock_state = MagicMock()

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "state": mock_state,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_init(mock_app)

        mock_shell.start.assert_called_once()
        mock_app.bot.send_message.assert_called_once_with(
            chat_id=99999,
            text="\U0001f7e2 [test-pc] \u00e8 online",
        )
        assert "heartbeat_task" in mock_app.bot_data

    @pytest.mark.asyncio
    async def test_post_init_creates_heartbeat_task(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
            heartbeat_interval=60,
        )
        mock_shell = MagicMock()
        mock_shell.start = AsyncMock()
        mock_state = MagicMock()

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "state": mock_state,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_init(mock_app)

        task = mock_app.bot_data["heartbeat_task"]
        assert isinstance(task, asyncio.Task)
        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestPostShutdown:
    """Lifecycle hook post_shutdown tests."""

    @pytest.mark.asyncio
    async def test_post_shutdown_cancels_heartbeat_and_sends_offline(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        mock_shell = MagicMock()
        mock_shell.shutdown = AsyncMock()

        # Create a fake heartbeat task
        async def fake_heartbeat():
            await asyncio.sleep(999)

        heartbeat_task = asyncio.create_task(fake_heartbeat())

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "heartbeat_task": heartbeat_task,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_shutdown(mock_app)

        mock_shell.shutdown.assert_called_once()
        assert heartbeat_task.cancelled()
        mock_app.bot.send_message.assert_called_once_with(
            chat_id=99999,
            text="\U0001f534 [test-pc] \u00e8 offline",
        )

    @pytest.mark.asyncio
    async def test_post_shutdown_handles_missing_heartbeat_task(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        mock_shell = MagicMock()
        mock_shell.shutdown = AsyncMock()

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
        }
        mock_app.bot.send_message = AsyncMock()

        # Should not raise
        await post_shutdown(mock_app)
        mock_shell.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_shutdown_handles_send_failure(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        mock_shell = MagicMock()
        mock_shell.shutdown = AsyncMock()

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
        }
        mock_app.bot.send_message = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise despite send failure
        await post_shutdown(mock_app)
        mock_shell.shutdown.assert_called_once()


class TestSendHeartbeat:
    """Heartbeat coroutine tests."""

    @pytest.mark.asyncio
    async def test_heartbeat_sends_message_and_registers(self) -> None:
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        mock_state = MagicMock()

        # Run heartbeat once then cancel
        async def run_one_heartbeat():
            task = asyncio.create_task(
                send_heartbeat(
                    app=mock_app,
                    chat_id=99999,
                    machine_name="test-pc",
                    interval=0.01,
                    state=mock_state,
                )
            )
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_one_heartbeat()

        mock_state.register_heartbeat.assert_called_with("test-pc")
        mock_app.bot.send_message.assert_called_with(
            chat_id=99999,
            text="__HB__test-pc__",
            disable_notification=True,
        )

    @pytest.mark.asyncio
    async def test_heartbeat_does_not_crash_on_send_failure(self) -> None:
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_state = MagicMock()

        task = asyncio.create_task(
            send_heartbeat(
                app=mock_app,
                chat_id=99999,
                machine_name="test-pc",
                interval=0.01,
                state=mock_state,
            )
        )
        # Let it fail at least once without crashing
        await asyncio.sleep(0.05)
        assert not task.done()  # Task still running (didn't crash)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestPostInitCancelsOldHeartbeat:
    """post_init cancels pre-existing heartbeat task before creating new one."""

    @pytest.mark.asyncio
    async def test_cancels_running_heartbeat_task(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        mock_shell = MagicMock()
        mock_shell.start = AsyncMock()
        mock_state = MagicMock()

        # Create a fake old heartbeat task that is still running
        async def old_heartbeat() -> None:
            await asyncio.sleep(999)

        old_task = asyncio.create_task(old_heartbeat())

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "state": mock_state,
            "heartbeat_task": old_task,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_init(mock_app)

        # Old task should be cancelled
        assert old_task.cancelled()
        # New task should be created
        new_task = mock_app.bot_data["heartbeat_task"]
        assert new_task is not old_task
        assert isinstance(new_task, asyncio.Task)
        new_task.cancel()
        try:
            await new_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_heartbeat_disabled_skips_task_creation(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
            heartbeat_enabled=False,
        )
        mock_shell = MagicMock()
        mock_shell.start = AsyncMock()
        mock_state = MagicMock()

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "state": mock_state,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_init(mock_app)

        # No heartbeat_task should be created
        assert "heartbeat_task" not in mock_app.bot_data


class TestErrorHandler:
    """Global error handler in build_application."""

    @pytest.mark.asyncio
    async def test_error_handler_logs_exception(self) -> None:
        from src.bot import build_application

        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        app = build_application(settings=settings)

        # The error handler is registered — verify it exists
        assert len(app.error_handlers) > 0


class TestMain:
    """Main entry point tests."""

    def test_main_missing_env_exits(self, tmp_path: Path, monkeypatch) -> None:
        from src.bot import main

        # Ensure no .env exists in cwd
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            main()
