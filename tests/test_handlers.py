"""Tests for Telegram command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.audit_log import AuditLog
from src.handlers import create_handlers
from src.shell_session import CommandResult


@pytest.fixture
def handlers(mock_state, mock_shell) -> dict:
    return create_handlers(
        state=mock_state,
        shell=mock_shell,
        authorized_chat_id=12345,
        command_timeout=30,
    )


@pytest.fixture
def handlers_with_audit(mock_state, mock_shell, tmp_path) -> tuple[dict, AuditLog]:
    audit = AuditLog(log_dir=tmp_path)
    h = create_handlers(
        state=mock_state,
        shell=mock_shell,
        authorized_chat_id=12345,
        command_timeout=30,
        audit_log=audit,
    )
    return h, audit


class TestAuthorization:
    """Authorization decorator blocks unauthorized access."""

    @pytest.mark.asyncio
    async def test_unauthorized_chat_is_rejected(self, handlers, mock_update, mock_context) -> None:
        mock_update.effective_chat.id = 99999
        await handlers["help"](mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_authorized_chat_is_allowed(self, handlers, mock_update, mock_context) -> None:
        mock_update.effective_chat.id = 12345
        await handlers["help"](mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_effective_chat_is_rejected(self, handlers, mock_update, mock_context) -> None:
        mock_update.effective_chat = None
        await handlers["help"](mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_private_chat_is_rejected(self, handlers, mock_update, mock_context) -> None:
        mock_update.effective_chat.type = "group"
        await handlers["help"](mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()


class TestActivate:
    """The /activate command switches active PC."""

    @pytest.mark.asyncio
    async def test_activate_valid_name(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_context.args = ["desktop"]
        await handlers["activate"](mock_update, mock_context)
        assert mock_state.active_pc == "desktop"
        mock_update.message.reply_text.assert_called_once_with("✅ PC attivo: desktop")

    @pytest.mark.asyncio
    async def test_activate_no_args_shows_usage(self, handlers, mock_update, mock_context) -> None:
        mock_context.args = []
        await handlers["activate"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Uso:" in reply

    @pytest.mark.asyncio
    async def test_activate_invalid_name_rejected(
        self, handlers, mock_update, mock_context
    ) -> None:
        mock_context.args = ["../../etc/passwd"]
        await handlers["activate"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "non valido" in reply

    @pytest.mark.asyncio
    async def test_activate_too_long_name_rejected(
        self, handlers, mock_update, mock_context
    ) -> None:
        mock_context.args = ["a" * 65]
        await handlers["activate"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "non valido" in reply

    @pytest.mark.asyncio
    async def test_activate_name_with_dash_and_underscore(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_context.args = ["my-desktop_01"]
        await handlers["activate"](mock_update, mock_context)
        assert mock_state.active_pc == "my-desktop_01"


class TestShellCommand:
    """Shell command execution handler."""

    @pytest.mark.asyncio
    async def test_no_active_pc_shows_warning(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        # No PC activated
        await handlers["shell_command"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Nessun PC selezionato" in reply

    @pytest.mark.asyncio
    async def test_inactive_machine_ignores_silently(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_state.activate("other-pc")
        await handlers["shell_command"](mock_update, mock_context)
        # Should not reply (not active machine)
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_command_on_active_machine(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="file.txt", exit_code=0)
        await handlers["shell_command"](mock_update, mock_context)
        mock_shell.execute.assert_called_once_with("ls -la")

    @pytest.mark.asyncio
    async def test_timeout_shows_message(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="", exit_code=-1, timed_out=True)
        await handlers["shell_command"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Timeout" in reply

    @pytest.mark.asyncio
    async def test_command_too_long_rejected(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_update.message.text = "x" * 2049
        await handlers["shell_command"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "troppo lungo" in reply
        mock_shell.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limiting_blocks_excess_commands(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="ok", exit_code=0)

        # Send 30 commands (should all pass)
        for _ in range(30):
            mock_update.message.reply_text.reset_mock()
            await handlers["shell_command"](mock_update, mock_context)

        # 31st should be rate limited
        mock_update.message.reply_text.reset_mock()
        await handlers["shell_command"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Rate limit" in reply


class TestCancel:
    """The /cancel command sends SIGINT."""

    @pytest.mark.asyncio
    async def test_cancel_on_active_pc(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.cancel.return_value = True
        await handlers["cancel"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "terminato" in reply

    @pytest.mark.asyncio
    async def test_cancel_no_process(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.cancel.return_value = False
        await handlers["cancel"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Nessun processo" in reply


class TestList:
    """The /list command shows online peers."""

    @pytest.mark.asyncio
    async def test_list_shows_peers(self, handlers, mock_update, mock_context, mock_state) -> None:
        mock_state.register_heartbeat("desktop")
        mock_state.register_heartbeat("laptop")
        await handlers["list"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "desktop" in reply
        assert "laptop" in reply


class TestStatus:
    """The /status command shows current state."""

    @pytest.mark.asyncio
    async def test_status_no_active_pc(self, handlers, mock_update, mock_context) -> None:
        await handlers["status"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "Nessun PC selezionato" in reply

    @pytest.mark.asyncio
    async def test_status_with_active_pc(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_state.activate("test-pc")
        await handlers["status"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "test-pc" in reply


class TestHeartbeat:
    """The heartbeat handler processes peer announcements."""

    @pytest.mark.asyncio
    async def test_valid_heartbeat_registers_peer(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = "__HB__desktop-01__"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        peer_names = [p.name for p in mock_state.get_online_peers()]
        assert "desktop-01" in peer_names

    @pytest.mark.asyncio
    async def test_heartbeat_deletes_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message.text = "__HB__laptop__"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_invalid_name_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = "__HB__../../etc__"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        peer_names = [p.name for p in mock_state.get_online_peers()]
        assert "../../etc" not in peer_names
        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_empty_name_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = "__HB____"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_too_long_name_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = f"__HB__{'a' * 65}__"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_unauthorized_chat_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.effective_chat.id = 99999
        mock_update.message.text = "__HB__laptop__"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        peer_names = [p.name for p in mock_state.get_online_peers()]
        assert "laptop" not in peer_names

    @pytest.mark.asyncio
    async def test_heartbeat_delete_failure_handled_gracefully(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = "__HB__server__"
        mock_update.message.delete = AsyncMock(side_effect=Exception("Forbidden"))
        await handlers["heartbeat"](mock_update, mock_context)
        # Should still register the heartbeat despite delete failure
        peer_names = [p.name for p in mock_state.get_online_peers()]
        assert "server" in peer_names

    @pytest.mark.asyncio
    async def test_heartbeat_without_text_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = None
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_with_wrong_suffix_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        # Missing trailing "__" — must be rejected to avoid spoofing
        mock_update.message.text = "__HB__desktop"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_not_called()
        assert "desktop" not in [p.name for p in mock_state.get_online_peers()]


class TestMissingMessageGuards:
    """Each handler must return silently when update.message is None.

    These early-returns prevent AttributeError on edge updates
    (e.g. edited messages, callback queries reaching wrong handler).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "handler_name",
        ["activate", "list", "status", "cancel", "help", "shell_command", "heartbeat"],
    )
    async def test_handler_without_message_does_not_crash(
        self, handlers, mock_update, mock_context, handler_name
    ) -> None:
        mock_update.message = None
        # Must not raise — the early `if not update.message: return` triggers
        await handlers[handler_name](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_shell_command_without_text_returns_silently(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_update.message.text = None
        await handlers["shell_command"](mock_update, mock_context)
        mock_shell.execute.assert_not_called()


class TestCancelEdgeCases:
    """The /cancel command's silent path on inactive PC."""

    @pytest.mark.asyncio
    async def test_cancel_silent_when_not_active_machine(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        # State has another PC active — cancel must not respond nor invoke shell
        mock_state.activate("other-pc")
        await handlers["cancel"](mock_update, mock_context)
        mock_shell.cancel.assert_not_called()
        mock_update.message.reply_text.assert_not_called()


class TestRateLimitEviction:
    """Rate limiter evicts timestamps older than the 60s window."""

    @pytest.mark.asyncio
    async def test_old_timestamps_are_evicted_allowing_new_commands(
        self, handlers, mock_update, mock_context, mock_state, mock_shell, monkeypatch
    ) -> None:
        from src import handlers as handlers_mod

        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="ok", exit_code=0)

        # Freeze "now" at t=0 for the first 30 commands
        current_time = [0.0]
        monkeypatch.setattr(handlers_mod.time, "monotonic", lambda: current_time[0])

        for _ in range(30):
            await handlers["shell_command"](mock_update, mock_context)

        # Advance time past 60s window — old timestamps must be evicted
        current_time[0] = 120.0

        mock_update.message.reply_text.reset_mock()
        await handlers["shell_command"](mock_update, mock_context)

        # Command should execute, not get rate-limited
        last_reply = mock_update.message.reply_text.call_args[0][0]
        assert "Rate limit" not in last_reply


class TestAuditLogIntegration:
    """The shell_command handler must record audit entries when audit_log is provided."""

    @pytest.mark.asyncio
    async def test_successful_command_writes_audit_entry(
        self, handlers_with_audit, mock_update, mock_context, mock_state, mock_shell, tmp_path
    ) -> None:
        handlers, audit = handlers_with_audit
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="hi", exit_code=0)

        await handlers["shell_command"](mock_update, mock_context)

        import json

        entries = (tmp_path / "audit.jsonl").read_text().strip().split("\n")
        assert len(entries) == 1
        entry = json.loads(entries[0])
        assert entry["command"] == "ls -la"
        assert entry["exit_code"] == 0
        assert entry["timed_out"] is False
        assert entry["machine"] == "test-pc"
        assert entry["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_timed_out_command_writes_audit_entry_with_timed_out_true(
        self, handlers_with_audit, mock_update, mock_context, mock_state, mock_shell, tmp_path
    ) -> None:
        handlers, audit = handlers_with_audit
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="", exit_code=-1, timed_out=True)

        await handlers["shell_command"](mock_update, mock_context)

        import json

        entry = json.loads((tmp_path / "audit.jsonl").read_text().strip())
        assert entry["timed_out"] is True
        assert entry["exit_code"] == -1


class TestStatusActiveCwd:
    """The /status command shows the shell's current working directory."""

    @pytest.mark.asyncio
    async def test_status_displays_shell_cwd(
        self, handlers, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        mock_state.activate("test-pc")
        mock_shell.cwd = "/opt/projects"
        await handlers["status"](mock_update, mock_context)
        reply = mock_update.message.reply_text.call_args[0][0]
        assert "/opt/projects" in reply
        assert "test-pc" in reply
