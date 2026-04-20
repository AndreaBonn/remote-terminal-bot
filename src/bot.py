"""Entry point — Telegram Terminal Bot."""

from __future__ import annotations

import asyncio
import logging
import re  # noqa: F401 — used at runtime in filters.Regex
import signal
import sys
from pathlib import Path

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import ConfigurationError, Settings, load_settings
from src.handlers import create_handlers
from src.shell_session import ShellSession
from src.state_manager import StateManager

logger = logging.getLogger(__name__)

_HEARTBEAT_PREFIX = "__HB__"


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging to stdout.

    Parameters
    ----------
    level : str
        Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    resolved_level = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    # Ensure level is applied even on reconfiguration
    logging.getLogger().setLevel(resolved_level)
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
                disable_notification=True,
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


def build_application(
    env_path: Path | None = None, settings: Settings | None = None
) -> Application:
    """Build and configure the Telegram bot application.

    Parameters
    ----------
    env_path : Path | None
        Path to .env file.
    settings : Settings | None
        Pre-loaded settings. If None, loads from env_path.

    Returns
    -------
    Application
        Fully configured bot application ready to run.
    """
    if settings is None:
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
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^{re.escape(_HEARTBEAT_PREFIX)}"),
            handlers["heartbeat"],
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

    # Global error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Unhandled exception: %s", context.error, exc_info=context.error)

    app.add_error_handler(error_handler)

    return app


def main() -> None:
    """Main entry point."""
    # Bootstrap logging early (reconfigured after settings load)
    setup_logging()

    # Handle graceful shutdown signals
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal.default_int_handler)

    try:
        settings = load_settings()
    except ConfigurationError as err:
        logger.critical("Startup failed: %s", err.message)
        sys.exit(1)

    # Reconfigure logging with validated level from settings
    setup_logging(level=settings.log_level)

    try:
        app = build_application(settings=settings)
    except ConfigurationError as err:
        logger.critical("Startup failed: %s", err.message)
        sys.exit(1)

    logger.info("Starting Telegram Terminal Bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
