"""Tests for shell session — integration tests with real bash."""

from __future__ import annotations

import pytest

from src.shell_session import ShellSession


@pytest.fixture
async def shell() -> ShellSession:
    """Create and start a shell session for testing."""
    session = ShellSession(timeout=10)
    await session.start()
    yield session  # type: ignore[misc]
    await session.shutdown()


class TestShellSession:
    """Persistent shell session behavior."""

    @pytest.mark.asyncio
    async def test_simple_command_returns_output(self, shell: ShellSession) -> None:
        result = await shell.execute("echo hello")
        assert result.output == "hello"
        assert result.exit_code == 0
        assert not result.timed_out

    @pytest.mark.asyncio
    async def test_preserves_working_directory(self, shell: ShellSession) -> None:
        await shell.execute("cd /tmp")
        result = await shell.execute("pwd")
        assert result.output == "/tmp"
        assert shell.cwd == "/tmp"

    @pytest.mark.asyncio
    async def test_captures_exit_code(self, shell: ShellSession) -> None:
        result = await shell.execute("false")
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_captures_stderr(self, shell: ShellSession) -> None:
        result = await shell.execute("echo err >&2")
        assert "err" in result.output

    @pytest.mark.asyncio
    async def test_no_output_command(self, shell: ShellSession) -> None:
        result = await shell.execute("true")
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_multiline_output(self, shell: ShellSession) -> None:
        result = await shell.execute("echo -e 'line1\\nline2\\nline3'")
        lines = result.output.strip().split("\n")
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_timeout_kills_and_respawns(self) -> None:
        session = ShellSession(timeout=2)
        await session.start()
        try:
            result = await session.execute("sleep 30")
            assert result.timed_out
            # Session should be respawned — next command should work
            result2 = await session.execute("echo recovered")
            assert result2.output == "recovered"
            assert result2.exit_code == 0
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_environment_variables_persist(self, shell: ShellSession) -> None:
        await shell.execute("export TEST_VAR=hello123")
        result = await shell.execute("echo $TEST_VAR")
        assert result.output == "hello123"

    @pytest.mark.asyncio
    async def test_special_characters_in_command(self, shell: ShellSession) -> None:
        result = await shell.execute("echo 'hello world' | wc -w")
        assert result.output.strip() == "2"
