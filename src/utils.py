"""Utility functions for message formatting and splitting."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.state_manager import PeerInfo

_TELEGRAM_MAX_LENGTH = 4096
_CHUNK_SIZE = 4000  # Leave margin for formatting


def format_output(output: str, exit_code: int) -> list[str]:
    """Format command output for Telegram, splitting if necessary.

    Parameters
    ----------
    output : str
        Raw command output text.
    exit_code : int
        Command exit code.

    Returns
    -------
    list[str]
        List of formatted messages ready to send.
    """
    if not output and exit_code == 0:
        return ["✅ Comando eseguito (nessun output)"]

    messages: list[str] = []

    if output:
        chunks = split_text(output, max_length=_CHUNK_SIZE)
        for i, chunk in enumerate(chunks):
            formatted = f"```\n{chunk}\n```"
            if len(chunks) > 1:
                formatted = f"[{i + 1}/{len(chunks)}]\n{formatted}"
            messages.append(formatted)

    if exit_code != 0:
        messages.append(f"⚠️ Exit code: {exit_code}")

    return messages


def format_timeout_message(timeout: int) -> str:
    """Format timeout notification message.

    Parameters
    ----------
    timeout : int
        Timeout duration in seconds.

    Returns
    -------
    str
        Formatted timeout message.
    """
    return f"⚠️ Timeout: il comando ha superato i {timeout} secondi ed è stato terminato."


def split_text(text: str, max_length: int = _CHUNK_SIZE) -> list[str]:
    """Split text into chunks respecting line boundaries.

    Parameters
    ----------
    text : str
        Text to split.
    max_length : int
        Maximum characters per chunk.

    Returns
    -------
    list[str]
        List of text chunks.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    lines = text.split("\n")
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1  # +1 for newline

        if current_length + line_length > max_length:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0

            # Single line exceeds max — force split by characters
            if line_length > max_length:
                for i in range(0, len(line), max_length):
                    chunks.append(line[i : i + max_length])
                continue

        current_chunk.append(line)
        current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def format_peer_list(peers: list[PeerInfo], now: float | None = None) -> str:
    """Format peer list for /list command response.

    Parameters
    ----------
    peers : list[PeerInfo]
        List of peer info objects.
    now : float | None
        Current timestamp. If None, uses time.time().

    Returns
    -------
    str
        Formatted peer list message.
    """
    if not peers:
        return "🖥️ Nessun PC online."

    if now is None:
        now = time.time()
    lines = ["🖥️ PC Online:"]
    for peer in peers:
        elapsed = int(now - peer.last_heartbeat)
        lines.append(f"  • {peer.name}  (ultimo heartbeat: {elapsed}s fa)")
    return "\n".join(lines)
