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

    def test_builds_with_audit_log_disabled_passes_none_to_handlers(
        self,
        tmp_path: Path,
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=123:FAKE\nAUTHORIZED_CHAT_ID=99999\n"
            "MACHINE_NAME=test-pc\nAUDIT_LOG_ENABLED=false\n",
        )
        from src.bot import build_application

        app = build_application(env_path=env_file)
        # With audit_log_enabled=False, build_application must not instantiate
        # AuditLog — no audit.jsonl file is created on disk for this run.
        assert app.bot_data["settings"].audit_log_enabled is False

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


class TestPostInitHeartbeatDisabled:
    """When heartbeat_enabled=False, no task is created."""

    @pytest.mark.asyncio
    async def test_post_init_skips_heartbeat_task_when_disabled(self) -> None:
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

        # No heartbeat task should have been registered
        assert "heartbeat_task" not in mock_app.bot_data

    @pytest.mark.asyncio
    async def test_post_init_cancels_pre_existing_heartbeat_task(self) -> None:
        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
            heartbeat_enabled=True,
        )
        mock_shell = MagicMock()
        mock_shell.start = AsyncMock()
        mock_state = MagicMock()

        async def _long_sleep():
            await asyncio.sleep(999)

        stale_task = asyncio.create_task(_long_sleep())

        mock_app = MagicMock()
        mock_app.bot_data = {
            "settings": settings,
            "shell": mock_shell,
            "state": mock_state,
            "heartbeat_task": stale_task,
        }
        mock_app.bot.send_message = AsyncMock()

        await post_init(mock_app)

        # Stale task must be cancelled, new one started
        assert stale_task.cancelled()
        new_task = mock_app.bot_data["heartbeat_task"]
        assert new_task is not stale_task
        # Cleanup
        new_task.cancel()
        try:
            await new_task
        except asyncio.CancelledError:
            pass


class TestBuildApplicationErrorHandler:
    """The global error_handler must log unhandled exceptions."""

    def test_error_handler_is_registered(self) -> None:
        from src.bot import build_application

        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        app = build_application(settings=settings)
        # ApplicationBuilder registers error handlers in error_handlers list
        assert len(app.error_handlers) > 0

    @pytest.mark.asyncio
    async def test_error_handler_logs_unhandled_exception(self, caplog) -> None:
        from src.bot import build_application

        settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="test-pc",
        )
        app = build_application(settings=settings)
        handler = next(iter(app.error_handlers))

        ctx = MagicMock()
        ctx.error = RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            await handler(update=MagicMock(), context=ctx)

        matching = [r for r in caplog.records if "Unhandled exception" in r.message]
        assert matching, "Expected error log with 'Unhandled exception'"
        assert any("boom" in str(r.exc_info[1]) for r in matching if r.exc_info)


class TestMain:
    """main() entry point — bootstrap with config + run_polling."""

    def test_main_exits_when_settings_load_fails(self, monkeypatch, caplog) -> None:
        from src import bot as bot_mod
        from src.config import ConfigurationError

        def _raise(*_a, **_kw):
            raise ConfigurationError("missing TOKEN")

        monkeypatch.setattr(bot_mod, "load_settings", _raise)

        with pytest.raises(SystemExit) as exc_info:
            bot_mod.main()
        assert exc_info.value.code == 1
        assert any("missing TOKEN" in r.message for r in caplog.records)

    def test_main_exits_when_build_application_fails(self, monkeypatch, caplog) -> None:
        from src import bot as bot_mod
        from src.config import ConfigurationError

        valid_settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="pc",
        )
        monkeypatch.setattr(bot_mod, "load_settings", lambda: valid_settings)

        def _build_fail(*_a, **_kw):
            raise ConfigurationError("broken")

        monkeypatch.setattr(bot_mod, "build_application", _build_fail)

        with pytest.raises(SystemExit) as exc_info:
            bot_mod.main()
        assert exc_info.value.code == 1
        assert any("broken" in r.message for r in caplog.records)

    def test_main_runs_polling_on_success(self, monkeypatch) -> None:
        from src import bot as bot_mod

        valid_settings = Settings(
            bot_token="123:FAKE",
            authorized_chat_id=99999,
            machine_name="pc",
        )
        monkeypatch.setattr(bot_mod, "load_settings", lambda: valid_settings)

        polling_called = {"value": False}

        class FakeApp:
            def run_polling(self, **kwargs) -> None:
                polling_called["value"] = True
                polling_called["kwargs"] = kwargs

        monkeypatch.setattr(bot_mod, "build_application", lambda settings: FakeApp())

        bot_mod.main()
        assert polling_called["value"] is True
        assert polling_called["kwargs"] == {"drop_pending_updates": True}
