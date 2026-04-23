"""Tests for Telegram command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
    async def test_heartbeat_no_message_ignored(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["heartbeat"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_heartbeat_no_text_ignored(self, handlers, mock_update, mock_context) -> None:
        mock_update.message.text = None
        await handlers["heartbeat"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_heartbeat_wrong_format_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_update.message.text = "__HB__notrailing"
        mock_update.message.delete = AsyncMock()
        await handlers["heartbeat"](mock_update, mock_context)
        mock_update.message.delete.assert_not_called()


class TestHandlerNullMessageGuards:
    """Handlers return early when update.message is None."""

    @pytest.mark.asyncio
    async def test_activate_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["activate"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_list_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["list"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_status_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["status"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_cancel_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["cancel"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_help_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["help"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_shell_command_no_message(self, handlers, mock_update, mock_context) -> None:
        mock_update.message = None
        await handlers["shell_command"](mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_shell_command_no_text(self, handlers, mock_update, mock_context) -> None:
        mock_update.message.text = None
        await handlers["shell_command"](mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()


class TestCancelInactive:
    """Cancel on inactive machine returns silently."""

    @pytest.mark.asyncio
    async def test_cancel_on_inactive_pc_ignored(
        self, handlers, mock_update, mock_context, mock_state
    ) -> None:
        mock_state.activate("other-pc")
        await handlers["cancel"](mock_update, mock_context)
        mock_update.message.reply_text.assert_not_called()


class TestShellCommandWithAuditLog:
    """Shell command handler records to audit log."""

    @pytest.mark.asyncio
    async def test_audit_log_records_command(
        self, mock_update, mock_context, mock_state, mock_shell
    ) -> None:
        from unittest.mock import MagicMock

        mock_audit = MagicMock()
        handlers = create_handlers(
            state=mock_state,
            shell=mock_shell,
            authorized_chat_id=12345,
            command_timeout=30,
            audit_log=mock_audit,
        )
        mock_state.activate("test-pc")
        mock_shell.execute.return_value = CommandResult(output="ok", exit_code=0)

        await handlers["shell_command"](mock_update, mock_context)

        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args
        assert call_kwargs[1]["command"] == "ls -la" or call_kwargs.kwargs["command"] == "ls -la"
