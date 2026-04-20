"""Entry point — Telegram Terminal Bot."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.config import load_settings
from src.handlers import create_handlers
from src.shell_session import ShellSession
from src.state_manager import StateManager

logger = logging.getLogger(__name__)

_HEARTBEAT_PREFIX = "__HB__"


def setup_logging() -> None:
    """Configure structured logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


async def send_heartbeat(
    app: Application,
    chat_id: int,
    machine_name: str,
    interval: int,
    state: StateManager,
) -> None:
    """Periodically send heartbeat messages.

    Parameters
    ----------
    app : Application
        Telegram bot application.
    chat_id : int
        Authorized chat ID.
    machine_name : str
        This machine's identifier.
    interval : int
        Seconds between heartbeats.
    state : StateManager
        State manager to update self heartbeat.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            state.register_heartbeat(machine_name)
            # Send silent heartbeat (will be filtered by other instances)
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"{_HEARTBEAT_PREFIX}{machine_name}__",
            )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Heartbeat failed")
            await asyncio.sleep(5)


async def post_init(app: Application) -> None:
    """Called after bot initialization — send online notification."""
    settings = app.bot_data["settings"]
    shell = app.bot_data["shell"]
    state = app.bot_data["state"]

    await shell.start()

    await app.bot.send_message(
        chat_id=settings.authorized_chat_id,
        text=f"🟢 [{settings.machine_name}] è online",
    )

    # Start heartbeat task
    app.bot_data["heartbeat_task"] = asyncio.create_task(
        send_heartbeat(
            app=app,
            chat_id=settings.authorized_chat_id,
            machine_name=settings.machine_name,
            interval=settings.heartbeat_interval,
            state=state,
        ),
    )
    logger.info("[%s] Bot started, online notification sent", settings.machine_name)


async def post_shutdown(app: Application) -> None:
    """Called during shutdown — send offline notification and cleanup."""
    settings = app.bot_data["settings"]
    shell = app.bot_data["shell"]

    # Cancel heartbeat
    heartbeat_task = app.bot_data.get("heartbeat_task")
    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    await shell.shutdown()

    try:
        await app.bot.send_message(
            chat_id=settings.authorized_chat_id,
            text=f"🔴 [{settings.machine_name}] è offline",
        )
    except Exception:
        logger.exception("Failed to send offline notification")

    logger.info("[%s] Bot shutdown complete", settings.machine_name)


def build_application(env_path: Path | None = None) -> Application:
    """Build and configure the Telegram bot application.

    Parameters
    ----------
    env_path : Path | None
        Path to .env file.

    Returns
    -------
    Application
        Fully configured bot application ready to run.
    """
    settings = load_settings(env_path=env_path)

    shell = ShellSession(timeout=settings.command_timeout)
    state = StateManager(
        machine_name=settings.machine_name,
        heartbeat_interval=settings.heartbeat_interval,
    )

    handlers = create_handlers(
        state=state,
        shell=shell,
        authorized_chat_id=settings.authorized_chat_id,
        command_timeout=settings.command_timeout,
    )

    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Store references for lifecycle hooks
    app.bot_data["settings"] = settings
    app.bot_data["shell"] = shell
    app.bot_data["state"] = state

    # Register command handlers
    app.add_handler(CommandHandler("activate", handlers["activate"]))
    app.add_handler(CommandHandler("list", handlers["list"]))
    app.add_handler(CommandHandler("status", handlers["status"]))
    app.add_handler(CommandHandler("cancel", handlers["cancel"]))
    app.add_handler(CommandHandler("help", handlers["help"]))

    # Heartbeat message filter — intercept and process silently
    async def heartbeat_filter(update, context):
        if not update.message or not update.message.text:
            return
        if not update.effective_chat or update.effective_chat.id != settings.authorized_chat_id:
            return
        text = update.message.text
        if text.startswith(_HEARTBEAT_PREFIX) and text.endswith("__"):
            pc_name = text[len(_HEARTBEAT_PREFIX) : -2]
            if (
                not pc_name
                or len(pc_name) > 64
                or not pc_name.replace("-", "").replace("_", "").isalnum()
            ):
                return
            state.register_heartbeat(pc_name)
            # Delete heartbeat message to keep chat clean
            try:
                await update.message.delete()
            except Exception:
                pass
            return

    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{_HEARTBEAT_PREFIX}"),
            heartbeat_filter,
        ),
        group=-1,  # Process before other handlers
    )

    # Shell command handler — all non-command text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handlers["shell_command"],
        ),
    )

    return app


def main() -> None:
    """Main entry point."""
    setup_logging()

    # Handle graceful shutdown signals
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal.default_int_handler)

    app = build_application()
    logger.info("Starting Telegram Terminal Bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
