"""Append-only audit log for executed commands."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "telegram-terminal-bot"

# Conservative redaction patterns — applied only when redact_secrets=True.
# Each tuple is (compiled regex, replacement). Patterns are intentionally
# narrow to avoid mangling innocuous commands. Suffix-anchored env-var match
# means `KEY_PATH=...` (a path to a key) is NOT redacted, only the value of
# something whose name ends in `_KEY`, `_TOKEN`, etc.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # --password=VALUE, --token=VALUE, --secret=VALUE, --api-key=VALUE
    (
        re.compile(r"(--(?:password|token|secret|api[-_]?key)=)\S+", re.IGNORECASE),
        r"\1[REDACTED]",
    ),
    # mysql / mysqldump / mariadb with `-p<password>` (no space after -p)
    (
        re.compile(
            r"\b(mysql|mysqldump|mariadb)(\s+(?:[^|&;<>\n]*?\s)?-p)\S+",
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED]",
    ),
    # Env var assignment whose name ends in a secret-ish suffix
    (
        re.compile(
            r"\b([A-Z][A-Z0-9_]*"
            r"(?:_KEY|_TOKEN|_SECRET|_PASSWORD|_PASSWD|_PWD|_CRED|_CREDENTIALS))="
            r"\S+",
        ),
        r"\1=[REDACTED]",
    ),
    # Authorization: Bearer XYZ / Basic XYZ.
    # Token charset is limited to base64url / base64 ([A-Za-z0-9+/=._-]) so
    # the regex stops at quoting characters (`'`, `"`) that would otherwise
    # be consumed by `\S+`.
    (
        re.compile(
            r"(Authorization:\s+(?:Bearer|Basic)\s+)[A-Za-z0-9+/=._\-]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
)


def _redact_command(command: str) -> str:
    """Apply conservative secret-redaction patterns to a command string.

    Parameters
    ----------
    command : str
        Raw command as typed by the user.

    Returns
    -------
    str
        Command with known secret patterns replaced by ``[REDACTED]``.
    """
    for pattern, replacement in _REDACTION_PATTERNS:
        command = pattern.sub(replacement, command)
    return command


class AuditLog:
    """Records executed commands to an append-only JSON Lines file.

    Parameters
    ----------
    log_dir : Path | None
        Directory for the audit log file. Defaults to XDG-compliant path.
    redact_secrets : bool
        If True, apply conservative redaction patterns to the command
        string before persisting. Default False (back-compat). The
        redaction is best-effort: it covers common forms (``--password=``,
        ``mysql -p<pwd>``, ``AWS_SECRET_*=``, ``Authorization: Bearer``)
        but cannot guarantee zero leakage. See SECURITY.md for limits.
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        *,
        redact_secrets: bool = False,
    ) -> None:
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "audit.jsonl"
        self._redact_secrets = redact_secrets

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
        recorded_command = _redact_command(command) if self._redact_secrets else command
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "machine": machine_name,
            "command": recorded_command[:2048],
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
        }
        try:
            with self._log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Failed to write audit log entry")
