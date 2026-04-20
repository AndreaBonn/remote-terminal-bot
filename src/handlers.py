"""Telegram bot command and message handlers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from src.utils import format_output, format_peer_list, format_timeout_message

if TYPE_CHECKING:
    from src.shell_session import ShellSession
    from src.state_manager import StateManager

logger = logging.getLogger(__name__)

# Type alias for handler functions
HandlerFunc = Callable[
    [Update, ContextTypes.DEFAULT_TYPE],
    Coroutine[Any, Any, None],
]


def create_handlers(
    state: StateManager,
    shell: ShellSession,
    authorized_chat_id: int,
    command_timeout: int,
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

    def authorized(func: HandlerFunc) -> HandlerFunc:
        """Decorator to reject unauthorized chat IDs."""

        @wraps(func)
        async def wrapper(
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
        ) -> None:
            if not update.effective_chat:
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
        assert update.message is not None

        if not context.args:
            await update.message.reply_text(
                "⚠️ Uso: /activate <nome_pc>",
            )
            return

        pc_name = context.args[0].strip().lower()
        state.activate(pc_name)
        await update.message.reply_text(f"✅ PC attivo: {pc_name}")
        logger.info("PC activated: %s (by chat %d)", pc_name, authorized_chat_id)

    @authorized
    async def handle_list(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /list command — show online PCs."""
        assert update.message is not None

        peers = state.get_online_peers()
        peer_dicts = [{"name": p.name, "last_heartbeat": p.last_heartbeat} for p in peers]
        await update.message.reply_text(format_peer_list(peer_dicts))

    @authorized
    async def handle_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /status command — show active PC and cwd."""
        assert update.message is not None

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
        assert update.message is not None

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
        assert update.message is not None

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
        assert update.message is not None
        assert update.message.text is not None

        if not state.active_pc:
            await update.message.reply_text(
                "⚠️ Nessun PC selezionato. Usa /activate <nome_pc>",
            )
            return

        if not state.is_active:
            # This machine is not the active one — ignore silently
            return

        command = update.message.text.strip()
        logger.info("Executing command: %s", command[:100])

        result = await shell.execute(command)

        if result.timed_out:
            await update.message.reply_text(
                format_timeout_message(command_timeout),
            )
            return

        messages = format_output(result.output, result.exit_code)
        for msg in messages:
            await update.message.reply_text(msg)

    return {
        "activate": handle_activate,
        "list": handle_list,
        "status": handle_status,
        "cancel": handle_cancel,
        "help": handle_help,
        "shell_command": handle_shell_command,
    }
