"""Tests for shell session — integration tests with real bash."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

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


class TestShellSessionLifecycle:
    """Spawn / respawn / shutdown lifecycle paths."""

    @pytest.mark.asyncio
    async def test_start_replaces_existing_process(self) -> None:
        session = ShellSession(timeout=5)
        await session.start()
        first_proc = session._process
        try:
            # Calling start() again must terminate the previous process
            await session.start()
            assert session._process is not first_proc
            assert first_proc.returncode is not None  # reaped
            assert session._process.returncode is None  # new one alive
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_dead_process_is_respawned_on_next_execute(self) -> None:
        session = ShellSession(timeout=5)
        await session.start()
        try:
            # Kill the underlying shell out-of-band
            session._process.terminate()
            await session._process.wait()
            assert session._process.returncode is not None

            # Next execute should detect death and respawn
            result = await session.execute("echo alive")
            assert result.output == "alive"
            assert result.exit_code == 0
            assert session._process.returncode is None  # Fresh process
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_idle_session_is_reset_after_threshold(self) -> None:
        session = ShellSession(timeout=5)
        session._IDLE_TIMEOUT = 0  # Force immediate idle reset
        await session.start()
        try:
            # First command sets last_activity
            await session.execute("echo first")
            first_pid = session._process.pid

            # Any subsequent command should trigger the idle reset path
            result = await session.execute("echo second")
            assert result.output == "second"
            assert session._process.pid != first_pid
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_running_process_sends_sigint(self) -> None:
        session = ShellSession(timeout=5)
        await session.start()
        try:
            # The session has a process; cancel must signal it successfully
            ok = await session.cancel()
            assert ok is True
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_handles_unresponsive_process(self) -> None:
        from unittest.mock import patch

        session = ShellSession(timeout=5)
        await session.start()
        proc = session._process

        # Patch wait_for to time out so the fallback kill() path runs.
        # Closing the awaitable (self._process.wait()) is required because
        # the argument is evaluated before our patch is invoked; leaving it
        # un-awaited raises a RuntimeWarning.
        async def _hang(awaitable, *_args, **_kwargs):
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError()

        with patch("asyncio.wait_for", side_effect=_hang):
            await session.shutdown()

        # Best-effort cleanup so the test doesn't leak the bash
        if proc.returncode is None:
            proc.kill()
            await proc.wait()

    @pytest.mark.asyncio
    async def test_update_cwd_after_failed_cwd_change_keeps_previous(self) -> None:
        session = ShellSession(timeout=5)
        await session.start()
        try:
            await session.execute("cd /tmp")
            previous = session.cwd
            # cd into nonexistent directory — pwd remains
            await session.execute("cd /no/such/dir/here 2>/dev/null")
            assert session.cwd == previous
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_update_cwd_handles_broken_pipe_on_process_death(self) -> None:
        """If the bash process dies before _update_cwd writes its probe,
        the BrokenPipeError raised by stdin.write must be caught and the
        previous cwd preserved instead of crashing the await chain."""
        from unittest.mock import AsyncMock, MagicMock

        session = ShellSession(timeout=5)
        session._lock = __import__("asyncio").Lock()

        proc = MagicMock()
        proc.returncode = None  # _is_alive() → True
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock(side_effect=BrokenPipeError("pipe closed"))
        proc.stdin.drain = AsyncMock()
        proc.stdout = MagicMock()
        session._process = proc

        session._cwd = "/previous"
        await session._update_cwd()
        assert session._cwd == "/previous"  # unchanged


class TestExitCodeParsing:
    """The marker line carries exit code from each command."""

    @pytest.mark.asyncio
    async def test_specific_nonzero_exit_code_captured(self) -> None:
        session = ShellSession(timeout=5)
        await session.start()
        try:
            result = await session.execute("(exit 42)")
            assert result.exit_code == 42
        finally:
            await session.shutdown()

    @pytest.mark.asyncio
    async def test_corrupt_exit_marker_falls_back_to_one(self) -> None:
        """Specification: ValueError parsing the marker → exit_code=1."""
        from unittest.mock import MagicMock

        from src import shell_session as shs

        session = ShellSession(timeout=5)
        # Bypass actual spawn — install a fake process
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()

        # Stub _generate_marker so we can predict the marker line
        marker = "__END_deadbeefcafebabe__"
        monkey_marker = lambda: marker  # noqa: E731

        # Build readlines that emit "<marker>NOTANINT\n" (invalid suffix)
        lines = [b"hello\n", f"{marker}NOTANINT\n".encode(), b""]
        stdout = MagicMock()
        stdout.readline = AsyncMock(side_effect=lines)
        stderr = MagicMock()
        # stderr immediately returns marker / empty
        stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode(), b""])
        proc.stdout = stdout
        proc.stderr = stderr

        session._process = proc
        session._lock = asyncio.Lock()

        # Patch generate_marker so it matches what we injected
        original = shs._generate_marker
        shs._generate_marker = monkey_marker
        try:
            # Stub _update_cwd to avoid extra reads on the mock
            session._update_cwd = AsyncMock()
            result = await session.execute("anything")
            assert result.exit_code == 1
            assert "hello" in result.output
        finally:
            shs._generate_marker = original

    @pytest.mark.asyncio
    async def test_execute_when_spawn_yields_no_stdin_raises(self) -> None:
        from unittest.mock import MagicMock

        session = ShellSession(timeout=5)
        session._lock = asyncio.Lock()
        broken_proc = MagicMock()
        broken_proc.returncode = None
        broken_proc.stdin = None  # No stdin available
        session._process = broken_proc

        with pytest.raises(RuntimeError, match="failed to start"):
            await session.execute("ls")


class TestCancelErrorPaths:
    """The cancel() method handles process group lookup failures gracefully."""

    @pytest.mark.asyncio
    async def test_cancel_returns_false_on_process_lookup_error(self, monkeypatch) -> None:

        import src.shell_session as shs

        session = ShellSession(timeout=5)
        session._process = MagicMock()
        session._process.returncode = None
        session._process.pid = 99999

        def _raise(*_a, **_kw):
            raise ProcessLookupError()

        monkeypatch.setattr(shs.os, "getpgid", _raise)
        result = await session.cancel()
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_returns_false_on_oserror(self, monkeypatch) -> None:

        import src.shell_session as shs

        session = ShellSession(timeout=5)
        session._process = MagicMock()
        session._process.returncode = None
        session._process.pid = 99999

        monkeypatch.setattr(shs.os, "getpgid", lambda _pid: 99999)

        def _raise(*_a, **_kw):
            raise OSError("EPERM")

        monkeypatch.setattr(shs.os, "killpg", _raise)
        result = await session.cancel()
        assert result is False


class TestSpawnTerminateFallback:
    """When the previous process won't terminate in time, fallback to kill()."""

    @pytest.mark.asyncio
    async def test_spawn_kills_unresponsive_previous_process(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        session = ShellSession(timeout=5)

        # Inject a previous process that hangs on wait()
        old_proc = MagicMock()
        old_proc.returncode = None
        old_proc.terminate = MagicMock()
        old_proc.kill = MagicMock()

        async def _hang():
            raise asyncio.TimeoutError()

        # wait_for(self._process.wait(), timeout=5) → TimeoutError → kill()
        original_wait_for = asyncio.wait_for

        async def patched_wait_for(awaitable, timeout):
            # Close the un-awaited coroutine so we don't leak it
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", patched_wait_for)
        session._process = old_proc

        # _spawn_shell will call terminate + wait_for → timeout → kill, then create new
        new_proc = MagicMock()
        new_proc.pid = 4242

        async def _fake_create_subprocess_exec(*_a, **_kw):
            return new_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

        try:
            await session._spawn_shell()
        finally:
            monkeypatch.setattr(asyncio, "wait_for", original_wait_for)

        old_proc.terminate.assert_called_once()
        old_proc.kill.assert_called_once()
        assert session._process is new_proc


def _make_session_with_fake_proc(marker: str) -> tuple[ShellSession, MagicMock]:
    """Build a ShellSession with a fully-mocked subprocess."""
    import asyncio as _aio

    session = ShellSession(timeout=5)
    session._lock = _aio.Lock()
    proc = MagicMock()
    proc.returncode = None
    proc.pid = 12345
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    session._process = proc
    # Stub update_cwd to avoid extra reads from the mock
    session._update_cwd = AsyncMock()
    return session, proc


class TestReadOutputEdgeCases:
    """Internal _read_output paths require precise stdout/stderr mocking."""

    @pytest.mark.asyncio
    async def test_read_output_returns_empty_when_no_process(self) -> None:
        session = ShellSession(timeout=5)
        # No process at all
        stdout_lines, stderr_lines = await session._read_output("__END_x__")
        assert stdout_lines == []
        assert stderr_lines == []

    @pytest.mark.asyncio
    async def test_first_readline_value_error_marks_truncated(self, monkeypatch) -> None:
        import src.shell_session as shs

        marker = "__END_aaaa__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        # First readline raises ValueError (oversized line)
        proc.stdout.readline = AsyncMock(side_effect=ValueError("buffer overflow"))
        proc.stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode(), b""])

        result = await session.execute("anything")
        assert "[OUTPUT TRUNCATED" in result.output

    @pytest.mark.asyncio
    async def test_stdout_eof_before_marker_breaks(self, monkeypatch) -> None:
        import src.shell_session as shs

        marker = "__END_bbbb__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        # readline returns "" (EOF) immediately
        proc.stdout.readline = AsyncMock(return_value=b"")
        proc.stderr.readline = AsyncMock(return_value=b"")

        result = await session.execute("anything")
        # Output empty, exit code remains default 0 (no marker parsed)
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_oversized_output_drain_path(self, monkeypatch) -> None:
        """Output > 512KB triggers drain loop including marker detection."""
        import src.shell_session as shs

        marker = "__END_cccc__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)

        # Emit enough lines to trip the 512KB cap, then a marker line
        big_line = ("y" * 1000 + "\n").encode()
        seq = [big_line] * 600 + [f"{marker}0\n".encode(), b""]
        proc.stdout.readline = AsyncMock(side_effect=seq)
        proc.stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode(), b""])

        result = await session.execute("anything")
        assert "[OUTPUT TRUNCATED" in result.output
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_drain_value_error_is_continued(self, monkeypatch) -> None:
        """Inside the drain loop, ValueError must continue, not crash."""
        import src.shell_session as shs

        marker = "__END_dddd__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)

        big_line = ("z" * 1000 + "\n").encode()
        # Fill enough to trip the cap, raise ValueError once inside drain, then marker
        seq = [big_line] * 600 + [ValueError("again"), f"{marker}0\n".encode(), b""]

        async def _readline_side_effect():
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        proc.stdout.readline = _readline_side_effect
        proc.stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode(), b""])

        result = await session.execute("anything")
        assert "[OUTPUT TRUNCATED" in result.output

    @pytest.mark.asyncio
    async def test_stderr_timeout_breaks_drain_loop(self, monkeypatch) -> None:
        """Stderr read timeout (0.1s) breaks the loop cleanly."""
        import src.shell_session as shs

        marker = "__END_eeee__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        proc.stdout.readline = AsyncMock(side_effect=[b"hello\n", f"{marker}0\n".encode(), b""])

        async def _hang():
            await asyncio.sleep(10)
            return b""

        proc.stderr.readline = _hang  # Never returns within 0.1s

        result = await session.execute("anything")
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_stderr_marker_line_breaks_drain(self, monkeypatch) -> None:
        """A marker line on stderr terminates the drain immediately."""
        import src.shell_session as shs

        marker = "__END_ffff__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        proc.stdout.readline = AsyncMock(side_effect=[b"out\n", f"{marker}0\n".encode(), b""])
        # First stderr line is the marker → break, no stderr included
        proc.stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode()])

        result = await session.execute("anything")
        assert result.output == "out"


class TestUpdateCwdEdgeCases:
    """The _update_cwd helper handles dead processes and timeouts."""

    @pytest.mark.asyncio
    async def test_update_cwd_skipped_when_process_dead(self) -> None:
        session = ShellSession(timeout=5)
        proc = MagicMock()
        proc.returncode = 0  # Already exited
        session._process = proc
        prev_cwd = session._cwd
        await session._update_cwd()
        assert session._cwd == prev_cwd  # Untouched

    @pytest.mark.asyncio
    async def test_update_cwd_returns_when_no_stdin(self) -> None:
        session = ShellSession(timeout=5)
        proc = MagicMock()
        proc.returncode = None
        proc.stdin = None
        session._process = proc
        prev_cwd = session._cwd
        await session._update_cwd()
        assert session._cwd == prev_cwd

    @pytest.mark.asyncio
    async def test_update_cwd_handles_eof(self, monkeypatch) -> None:
        import src.shell_session as shs

        marker = "__END_gggg__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        del session._update_cwd  # Restore original
        proc.stdout.readline = AsyncMock(return_value=b"")  # Immediate EOF

        prev_cwd = session._cwd
        await session._update_cwd()
        assert session._cwd == prev_cwd

    @pytest.mark.asyncio
    async def test_update_cwd_keeps_previous_on_timeout(self, monkeypatch) -> None:
        import src.shell_session as shs

        marker = "__END_hhhh__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        del session._update_cwd

        async def _hang():
            await asyncio.sleep(10)
            return b""

        proc.stdout.readline = _hang

        prev_cwd = session._cwd
        await session._update_cwd()
        assert session._cwd == prev_cwd


class TestKillAndRespawnPaths:
    """The _kill_and_respawn helper survives process-lookup failures."""

    @pytest.mark.asyncio
    async def test_kill_and_respawn_handles_process_lookup_error(self, monkeypatch) -> None:
        import src.shell_session as shs

        session = ShellSession(timeout=5)
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 99999
        proc.wait = AsyncMock(return_value=0)
        session._process = proc

        def _raise(*_a, **_kw):
            raise ProcessLookupError()

        monkeypatch.setattr(shs.os, "getpgid", _raise)

        new_proc = MagicMock()
        new_proc.pid = 4242
        new_proc.returncode = None

        async def _fake_spawn(*_a, **_kw):
            return new_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)

        await session._kill_and_respawn()
        # cwd reset to home and process replaced
        import os as _os

        assert session._cwd == _os.path.expanduser("~")
        assert session._process is new_proc

    @pytest.mark.asyncio
    async def test_kill_and_respawn_handles_wait_timeout(self, monkeypatch) -> None:
        import src.shell_session as shs

        session = ShellSession(timeout=5)
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 99999
        session._process = proc

        monkeypatch.setattr(shs.os, "getpgid", lambda _pid: 99999)
        monkeypatch.setattr(shs.os, "killpg", lambda *_a, **_kw: None)

        async def _hanging_wait_for(awaitable, timeout):
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", _hanging_wait_for)

        new_proc = MagicMock()
        new_proc.pid = 5555
        new_proc.returncode = None

        async def _fake_spawn(*_a, **_kw):
            return new_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)

        # Must not raise despite wait timeout
        await session._kill_and_respawn()
        assert session._process is new_proc


class TestShutdownAlreadyExited:
    """Shutdown is a no-op when the process is already gone."""

    @pytest.mark.asyncio
    async def test_shutdown_with_already_exited_process_does_nothing(self) -> None:
        session = ShellSession(timeout=5)
        proc = MagicMock()
        proc.returncode = 0  # Already exited
        proc.terminate = MagicMock()
        session._process = proc
        await session.shutdown()
        proc.terminate.assert_not_called()


class TestRemainingShellBranches:
    """Final branches: drain EOF, cwd non-marker lines, kill_respawn no-process."""

    @pytest.mark.asyncio
    async def test_drain_loop_breaks_on_eof(self, monkeypatch) -> None:
        """During drain after truncation, EOF (empty bytes) breaks the loop."""
        import src.shell_session as shs

        marker = "__END_iiii__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        big_line = ("q" * 1000 + "\n").encode()
        # Trip the cap, then EOF (b"") in the drain — no marker
        seq = [big_line] * 600 + [b""]
        proc.stdout.readline = AsyncMock(side_effect=seq)
        proc.stderr.readline = AsyncMock(side_effect=[f"{marker}\n".encode(), b""])

        result = await session.execute("x")
        assert "[OUTPUT TRUNCATED" in result.output

    @pytest.mark.asyncio
    async def test_update_cwd_skips_non_marker_lines(self, monkeypatch) -> None:
        """Non-matching readline output is discarded; loop continues."""
        import src.shell_session as shs

        marker = "__END_jjjj__"
        monkeypatch.setattr(shs, "_generate_marker", lambda: marker)

        session, proc = _make_session_with_fake_proc(marker)
        del session._update_cwd  # Restore real method

        # First a non-marker line, then the cwd marker
        proc.stdout.readline = AsyncMock(
            side_effect=[
                b"some unrelated output\n",
                f"{marker}__CWD__/var/tmp\n".encode(),
                b"",
            ]
        )

        await session._update_cwd()
        assert session._cwd == "/var/tmp"

    @pytest.mark.asyncio
    async def test_kill_and_respawn_when_no_process_exists(self, monkeypatch) -> None:
        """If there's no process, _kill_and_respawn skips kill and spawns fresh."""
        session = ShellSession(timeout=5)
        # No _process at all
        new_proc = MagicMock()
        new_proc.pid = 1111
        new_proc.returncode = None

        async def _fake_spawn(*_a, **_kw):
            return new_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)

        await session._kill_and_respawn()
        import os as _os

        assert session._cwd == _os.path.expanduser("~")
        assert session._process is new_proc
