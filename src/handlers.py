"""Telegram bot command and message handlers."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from src.utils import format_output, format_peer_list, format_timeout_message

if TYPE_CHECKING:
    from src.audit_log import AuditLog
    from src.shell_session import ShellSession
    from src.state_manager import StateManager

logger = logging.getLogger(__name__)

# Type alias for handler functions
HandlerFunc = Callable[
    [Update, ContextTypes.DEFAULT_TYPE],
    Coroutine[Any, Any, None],
]

_MAX_COMMANDS_PER_MINUTE = 30
_MAX_COMMAND_LENGTH = 2048
_HEARTBEAT_PREFIX = "__HB__"
_PC_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def create_handlers(
    state: StateManager,
    shell: ShellSession,
    authorized_chat_id: int,
    command_timeout: int,
    audit_log: AuditLog | None = None,
) -> dict[str, HandlerFunc]:
    """Create handler functions with injected dependencies.

    Parameters
    ----------
    state : StateManager
        Shared state manager instance.
    shell : ShellSession
        Persistent shell session instance.
    authorized_chat_id : int
        Telegram chat ID authorized to use the bot.
    command_timeout : int
        Command execution timeout in seconds.

    Returns
    -------
    dict[str, HandlerFunc]
        Mapping of handler names to async handler functions.
    """

    command_timestamps: deque[float] = deque()

    def _is_rate_limited() -> bool:
        """Check if command rate limit has been exceeded."""
        now = time.monotonic()
        while command_timestamps and now - command_timestamps[0] > 60:
            command_timestamps.popleft()
        if len(command_timestamps) >= _MAX_COMMANDS_PER_MINUTE:
            return True
        command_timestamps.append(now)
        return False

    def authorized(func: HandlerFunc) -> HandlerFunc:
        """Decorator to reject unauthorized chat IDs."""

        @wraps(func)
        async def wrapper(
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
        ) -> None:
            if not update.effective_chat:
                return
            if update.effective_chat.type != "private":
                return
            if update.effective_chat.id != authorized_chat_id:
                logger.warning(
                    "Unauthorized access attempt from chat_id: %d",
                    update.effective_chat.id,
                )
                return
            await func(update, context)

        return wrapper

    @authorized
    async def handle_activate(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /activate <pc_name> command."""
        if not update.message:
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Uso: /activate <nome_pc>",
            )
            return

        pc_name = context.args[0].strip().lower()
        if not pc_name or len(pc_name) > 64 or not _PC_NAME_PATTERN.match(pc_name):
            await update.message.reply_text(
                "⚠️ Nome PC non valido. Usa solo lettere, numeri, - e _ (max 64 caratteri).",
            )
            return
        state.activate(pc_name)
        await update.message.reply_text(f"✅ PC attivo: {pc_name}")
        logger.info("PC activated: %s (by chat %d)", pc_name, authorized_chat_id)

    @authorized
    async def handle_list(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /list command — show online PCs."""
        if not update.message:
            return

        peers = state.get_online_peers()
        await update.message.reply_text(format_peer_list(peers))

    @authorized
    async def handle_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /status command — show active PC and cwd."""
        if not update.message:
            return

        if not state.active_pc:
            await update.message.reply_text(
                "⚠️ Nessun PC selezionato. Usa /activate <nome_pc>",
            )
            return

        text = f"🖥️ PC attivo: {state.active_pc}\n📁 Directory corrente: {shell.cwd}"
        await update.message.reply_text(text)

    @authorized
    async def handle_cancel(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /cancel command — interrupt running command."""
        if not update.message:
            return

        if not state.is_active:
            return

        success = await shell.cancel()
        if success:
            await update.message.reply_text("🛑 Processo terminato")
        else:
            await update.message.reply_text("ℹ️ Nessun processo in esecuzione")

    @authorized
    async def handle_help(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /help command."""
        if not update.message:
            return

        help_text = (
            "🤖 *Telegram Terminal Bot*\n\n"
            "Comandi disponibili:\n"
            "• /activate <nome\\_pc> — Seleziona PC attivo\n"
            "• /list — Mostra PC online\n"
            "• /status — PC attivo e directory corrente\n"
            "• /cancel — Termina comando in esecuzione\n"
            "• /help — Questo messaggio\n\n"
            "Qualsiasi altro messaggio viene eseguito come comando shell sul PC attivo."
        )
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
        )

    @authorized
    async def handle_shell_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle arbitrary text as shell command."""
        if not update.message:
            return
        if not update.message.text:
            return

        if not state.active_pc:
            await update.message.reply_text(
                "⚠️ Nessun PC selezionato. Usa /activate <nome_pc>",
            )
            return

        if not state.is_active:
            # This machine is not the active one — ignore silently
            return

        command = update.message.text.strip()

        if len(command) > _MAX_COMMAND_LENGTH:
            await update.message.reply_text(
                f"⚠️ Comando troppo lungo (max {_MAX_COMMAND_LENGTH} caratteri).",
            )
            return

        if _is_rate_limited():
            await update.message.reply_text(
                "⚠️ Rate limit raggiunto (max 30 comandi/minuto). Riprova tra poco.",
            )
            return

        logger.info("Executing command (len=%d)", len(command))

        await update.message.chat.send_action(ChatAction.TYPING)
        start_time = time.monotonic()
        result = await shell.execute(command)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        if audit_log:
            audit_log.record(
                command=command,
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                machine_name=state.machine_name,
                duration_ms=duration_ms,
            )

        if result.timed_out:
            await update.message.reply_text(
                format_timeout_message(command_timeout),
            )
            return

        messages = format_output(result.output, result.exit_code)
        for msg in messages:
            await update.message.reply_text(msg)

    @authorized
    async def handle_heartbeat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process incoming heartbeat messages from peer bots."""
        if not update.message or not update.message.text:
            return
        text = update.message.text
        prefix = _HEARTBEAT_PREFIX
        if not (text.startswith(prefix) and text.endswith("__")):
            return
        pc_name = text[len(prefix) : -2]
        if not pc_name or len(pc_name) > 64 or not _PC_NAME_PATTERN.match(pc_name):
            return
        state.register_heartbeat(pc_name)
        try:
            await update.message.delete()
        except Exception:
            logger.debug("Failed to delete heartbeat message")

    return {
        "activate": handle_activate,
        "list": handle_list,
        "status": handle_status,
        "cancel": handle_cancel,
        "help": handle_help,
        "shell_command": handle_shell_command,
        "heartbeat": handle_heartbeat,
    }
