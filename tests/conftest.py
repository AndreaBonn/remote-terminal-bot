"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shell_session import ShellSession
from src.state_manager import StateManager


@pytest.fixture
def mock_shell() -> MagicMock:
    """Mock ShellSession with spec validation."""
    shell = MagicMock(spec=ShellSession)
    shell.cwd = "/home/user"
    shell.execute = AsyncMock()
    shell.cancel = AsyncMock()
    return shell


@pytest.fixture
def mock_state(tmp_path) -> StateManager:
    """Real StateManager with temp state file."""
    return StateManager(
        machine_name="test-pc",
        heartbeat_interval=60,
        state_file=tmp_path / "state.json",
    )


@pytest.fixture
def mock_update() -> MagicMock:
    """Mock Telegram Update object."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_chat.type = "private"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    update.message.text = "ls -la"
    return update


@pytest.fixture
def mock_context() -> MagicMock:
    """Mock Telegram context."""
    return MagicMock()
