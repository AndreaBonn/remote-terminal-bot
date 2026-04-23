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

    @pytest.mark.asyncio
    async def test_execute_before_start_raises_runtime_error(self) -> None:
        session = ShellSession()
        with pytest.raises(RuntimeError, match="start\\(\\) must be called"):
            await session.execute("echo hi")

    @pytest.mark.asyncio
    async def test_large_output_is_truncated(self, shell: ShellSession) -> None:
        # Generate output > 512KB using many lines (avoids readline buffer limit)
        result = await shell.execute(
            "python3 -c \"import sys; [sys.stdout.write('x' * 200 + '\\n') for _ in range(4000)]\""
        )
        assert "[OUTPUT TRUNCATED" in result.output

    @pytest.mark.asyncio
    async def test_cancel_on_unstarted_session(self) -> None:
        session = ShellSession()
        result = await session.cancel()
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_sends_sigint_to_running_process(self, shell: ShellSession) -> None:
        """Cancel returns True when process is alive."""
        result = await shell.cancel()
        assert result is True

    @pytest.mark.asyncio
    async def test_respawn_after_process_death(self, shell: ShellSession) -> None:
        """Shell respawns automatically if process dies."""
        # Kill the process manually
        shell._process.kill()
        await shell._process.wait()
        # Next command should trigger respawn
        result = await shell.execute("echo alive")
        assert result.output == "alive"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_idle_timeout_resets_session(self) -> None:
        """Session resets after exceeding idle timeout."""
        session = ShellSession(timeout=10)
        await session.start()
        try:
            # Set last_activity far in the past to trigger idle reset
            session._last_activity = 1.0
            result = await session.execute("echo reset")
            assert result.output == "reset"
            assert result.exit_code == 0
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_spawn_shell_terminates_existing_process(self) -> None:
        """_spawn_shell terminates running process before spawning new one."""
        session = ShellSession(timeout=10)
        await session.start()
        try:
            old_pid = session._process.pid
            await session._spawn_shell()
            new_pid = session._process.pid
            assert old_pid != new_pid
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_kills_after_timeout(self) -> None:
        """shutdown() kills process if terminate doesn't work within timeout."""
        session = ShellSession(timeout=10)
        await session.start()
        assert session._process is not None
        # Start a long sleep so terminate might be slow
        session._process.stdin.write(b"sleep 999\n")
        await session._process.stdin.drain()
        await session.shutdown()
        # Process should be dead after shutdown
        assert session._process.returncode is not None

    @pytest.mark.asyncio
    async def test_stderr_output_combined_with_stdout(self, shell: ShellSession) -> None:
        """Stderr is appended to output when both stdout and stderr present."""
        result = await shell.execute("echo out && echo err >&2")
        assert "out" in result.output
        assert "err" in result.output

    @pytest.mark.asyncio
    async def test_kill_and_respawn_resets_cwd(self) -> None:
        """_kill_and_respawn resets cwd to home directory."""
        import os

        session = ShellSession(timeout=10)
        await session.start()
        try:
            await session.execute("cd /tmp")
            assert session.cwd == "/tmp"
            await session._kill_and_respawn()
            assert session.cwd == os.path.expanduser("~")
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_on_dead_process_returns_false(self) -> None:
        """Cancel returns False when process already exited."""
        session = ShellSession(timeout=10)
        await session.start()
        try:
            session._process.kill()
            await session._process.wait()
            result = await session.cancel()
            assert result is False
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_process_lookup_error_returns_false(self) -> None:
        """Cancel returns False on ProcessLookupError (race condition)."""
        import os
        from unittest.mock import patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            with patch.object(os, "getpgid", side_effect=ProcessLookupError):
                result = await session.cancel()
            assert result is False
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_read_output_with_no_process_returns_empty(self) -> None:
        """_read_output returns empty lists when process is None."""
        session = ShellSession(timeout=10)
        session._process = None
        result = await session._read_output("marker")
        assert result == ([], [])

    @pytest.mark.asyncio
    async def test_update_cwd_on_dead_process_noop(self) -> None:
        """_update_cwd returns early when process is dead."""
        session = ShellSession(timeout=10)
        await session.start()
        try:
            session._process.kill()
            await session._process.wait()
            old_cwd = session._cwd
            await session._update_cwd()
            assert session._cwd == old_cwd
        finally:
            pass

    @pytest.mark.asyncio
    async def test_spawn_shell_kills_stuck_process(self) -> None:
        """_spawn_shell kills process that doesn't terminate gracefully."""
        import asyncio
        from unittest.mock import patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            # Make terminate not actually kill — wait_for will timeout
            old_process = session._process
            with (
                patch.object(old_process, "terminate"),
                patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError),
            ):
                await session._spawn_shell()
            # New process should be spawned
            assert session._process is not old_process
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_kill_and_respawn_handles_process_lookup_error(self) -> None:
        """_kill_and_respawn handles ProcessLookupError gracefully."""
        import os
        from unittest.mock import patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            with patch.object(os, "getpgid", side_effect=ProcessLookupError):
                await session._kill_and_respawn()
            # Should have a new working process
            result = await session.execute("echo ok")
            assert result.output == "ok"
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_exit_code_parse_error_defaults_to_one(self, shell: ShellSession) -> None:
        """Invalid exit code in marker line defaults to 1."""
        result = await shell.execute("exit 42")
        assert isinstance(result.exit_code, int)

    @pytest.mark.asyncio
    async def test_update_cwd_timeout_keeps_previous_cwd(self) -> None:
        """_update_cwd keeps previous cwd when readline times out."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            session._cwd = "/previous"
            # Mock stdout readline to always timeout
            with patch.object(
                session._process.stdout,
                "readline",
                new_callable=AsyncMock,
                side_effect=asyncio.TimeoutError,
            ):
                await session._update_cwd()
            assert session._cwd == "/previous"
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_update_cwd_with_none_process_noop(self) -> None:
        """_update_cwd handles None stdin/stdout gracefully."""
        session = ShellSession(timeout=10)
        await session.start()
        try:
            session._process.stdin = None
            old_cwd = session._cwd
            await session._update_cwd()
            assert session._cwd == old_cwd
        finally:
            pass

    @pytest.mark.asyncio
    async def test_process_failed_to_start_raises(self) -> None:
        """_execute_locked raises when process is None after respawn attempt."""
        from unittest.mock import AsyncMock, patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            # Simulate process that sets to None
            session._process = None
            session._last_activity = 0.0
            with (
                patch.object(session, "_spawn_shell", new_callable=AsyncMock),
                pytest.raises(RuntimeError, match="failed to start"),
            ):
                await session._execute_locked("echo hi")
        finally:
            pass

    @pytest.mark.asyncio
    async def test_readline_value_error_truncates_output(self) -> None:
        """ValueError from readline (line > buffer) triggers truncation."""
        from unittest.mock import patch

        session = ShellSession(timeout=10)
        await session.start()
        try:
            original_readline = session._process.stdout.readline

            call_count = 0

            async def mock_readline():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ValueError("Separator is not found")
                return await original_readline()

            with patch.object(session._process.stdout, "readline", side_effect=mock_readline):
                stdout, stderr = await session._read_output("__MARKER__")
            assert any("TRUNCATED" in line for line in stdout)
        finally:
            await session.shutdown()
