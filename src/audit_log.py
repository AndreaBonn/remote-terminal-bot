"""Append-only audit log for executed commands."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "telegram-terminal-bot"


class AuditLog:
    """Records executed commands to an append-only JSON Lines file.

    Parameters
    ----------
    log_dir : Path | None
        Directory for the audit log file. Defaults to XDG-compliant path.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "audit.jsonl"

    def record(
        self,
        *,
        command: str,
        exit_code: int,
        timed_out: bool,
        machine_name: str,
        duration_ms: int,
    ) -> None:
        """Append a command execution record to the audit log.

        Parameters
        ----------
        command : str
            The command that was executed.
        exit_code : int
            Exit code of the command.
        timed_out : bool
            Whether the command timed out.
        machine_name : str
            Name of the machine that executed it.
        duration_ms : int
            Execution duration in milliseconds.
        """
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "machine": machine_name,
            "command": command[:2048],
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
        }
        try:
            with self._log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Failed to write audit log entry")
