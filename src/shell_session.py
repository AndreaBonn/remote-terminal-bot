"""Persistent shell session management with async I/O."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import signal
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_OUTPUT_BYTES = 512 * 1024  # 512 KB hard cap


def _generate_marker() -> str:
    """Generate a unique, unpredictable end marker per command."""
    return f"__END_{secrets.token_hex(16)}__"


@dataclass
class CommandResult:
    """Result of a shell command execution."""

    output: str
    exit_code: int
    timed_out: bool = False


class ShellSession:
    """Persistent bash session communicating via stdin/stdout.

    Maintains working directory between commands and supports
    timeout-based termination with automatic session recreation.
    """

    _IDLE_TIMEOUT = 1800  # 30 minutes of inactivity before session reset

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout
        self._process: asyncio.subprocess.Process | None = None
        self._cwd: str = os.path.expanduser("~")
        self._lock: asyncio.Lock | None = None
        self._last_activity: float = 0.0

    async def start(self) -> None:
        """Start or restart the persistent bash process."""
        self._lock = asyncio.Lock()
        await self._spawn_shell()

    async def _spawn_shell(self) -> None:
        """Spawn a new bash subprocess."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                self._process.kill()

        self._process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "--norc",
            "--noprofile",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            cwd=self._cwd,
        )
        logger.info("Shell session spawned (PID: %d)", self._process.pid)

    async def execute(self, command: str) -> CommandResult:
        """Execute a command in the persistent shell.

        Parameters
        ----------
        command : str
            Shell command to execute.

        Returns
        -------
        CommandResult
            Output, exit code, and timeout status.
        """
        if self._lock is None:
            msg = "ShellSession.start() must be called before execute()"
            raise RuntimeError(msg)
        async with self._lock:
            return await self._execute_locked(command)

    async def _execute_locked(self, command: str) -> CommandResult:
        """Execute command while holding the lock."""
        # Reset session if idle for too long (security: limit exposure window)
        now = time.monotonic()
        if self._last_activity > 0 and (now - self._last_activity) > self._IDLE_TIMEOUT:
            logger.info("Session idle for >%ds, resetting", self._IDLE_TIMEOUT)
            await self._kill_and_respawn()
        self._last_activity = now

        if not self._is_alive():
            logger.warning("Shell process dead, respawning")
            await self._spawn_shell()

        if not self._process or not self._process.stdin:
            raise RuntimeError("Shell process failed to start")

        # Generate fresh marker per-command to prevent marker injection
        marker = _generate_marker()

        # Write command + marker to stdin
        payload = f'{command}\necho "{marker}$?"\necho "{marker}" >&2\n'
        self._process.stdin.write(payload.encode())
        await self._process.stdin.drain()

        try:
            stdout_lines, stderr_lines = await asyncio.wait_for(
                self._read_output(marker),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Command timed out after %ds (len=%d)", self._timeout, len(command))
            await self._kill_and_respawn()
            return CommandResult(
                output="",
                exit_code=-1,
                timed_out=True,
            )

        # Parse exit code from marker line
        exit_code = 0
        output_lines: list[str] = []
        for line in stdout_lines:
            if line.startswith(marker):
                try:
                    exit_code = int(line[len(marker) :])
                except ValueError:
                    exit_code = 1
            else:
                output_lines.append(line)

        # Combine stdout and stderr
        output = "\n".join(output_lines).rstrip()
        stderr = "\n".join(stderr_lines).rstrip()
        if stderr:
            output = f"{output}\n{stderr}" if output else stderr

        # Update cwd
        await self._update_cwd()

        return CommandResult(output=output, exit_code=exit_code)

    async def _read_output(self, marker: str) -> tuple[list[str], list[str]]:
        """Read stdout and stderr until end markers are found."""
        if not self._process or not self._process.stdout or not self._process.stderr:
            return [], []

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        total_bytes = 0
        truncated = False

        # Read stdout until marker
        while True:
            try:
                line = await self._process.stdout.readline()
            except ValueError:
                # Single line exceeded asyncio stream buffer limit (~64KB)
                truncated = True
                break
            if not line:
                break
            decoded = line.decode(errors="replace").rstrip("\n")
            if decoded.startswith(marker):
                stdout_lines.append(decoded)
                break
            total_bytes += len(decoded) + 1
            if total_bytes > _MAX_OUTPUT_BYTES:
                truncated = True
                # Drain remaining stdout until marker
                while True:
                    try:
                        drain_line = await self._process.stdout.readline()
                    except ValueError:
                        continue
                    if not drain_line:
                        break
                    if drain_line.decode(errors="replace").rstrip("\n").startswith(marker):
                        stdout_lines.append(drain_line.decode(errors="replace").rstrip("\n"))
                        break
                break
            stdout_lines.append(decoded)

        if truncated:
            stdout_lines.append("[OUTPUT TRUNCATED: exceeded 512KB limit]")

        # Read available stderr (non-blocking drain)
        while True:
            try:
                line = await asyncio.wait_for(
                    self._process.stderr.readline(),
                    timeout=0.1,
                )
                if not line:
                    break
                decoded = line.decode(errors="replace").rstrip("\n")
                if decoded.startswith(marker):
                    break
                stderr_lines.append(decoded)
            except asyncio.TimeoutError:
                break

        return stdout_lines, stderr_lines

    async def _update_cwd(self) -> None:
        """Update tracked working directory after command execution."""
        if not self._is_alive():
            return

        if not self._process or not self._process.stdin or not self._process.stdout:
            return

        cwd_marker = _generate_marker()
        try:
            self._process.stdin.write(f'echo "{cwd_marker}__CWD__$(pwd)"\n'.encode())
            await self._process.stdin.drain()
        except (ConnectionResetError, BrokenPipeError):
            logger.debug("Process died before cwd update, keeping previous: %s", self._cwd)
            return

        try:
            while True:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=2,
                )
                if not line:
                    break
                decoded = line.decode().rstrip("\n")
                cwd_prefix = f"{cwd_marker}__CWD__"
                if decoded.startswith(cwd_prefix):
                    self._cwd = decoded[len(cwd_prefix) :]
                    break
        except asyncio.TimeoutError:
            logger.debug("Timeout reading cwd update, keeping previous: %s", self._cwd)

    async def _kill_and_respawn(self) -> None:
        """Kill current process group and start fresh."""
        if self._process and self._process.returncode is None:
            try:
                pgid = os.getpgid(self._process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass

        self._cwd = os.path.expanduser("~")
        await self._spawn_shell()

    async def cancel(self) -> bool:
        """Send SIGINT to the running command's process group.

        Returns
        -------
        bool
            True if signal was sent, False if no process running.
        """
        if not self._is_alive() or not self._process:
            return False
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGINT)
            return True
        except (ProcessLookupError, OSError):
            return False

    @property
    def cwd(self) -> str:
        """Current working directory of the shell session."""
        return self._cwd

    def _is_alive(self) -> bool:
        """Check if the bash process is still running."""
        return self._process is not None and self._process.returncode is None

    async def shutdown(self) -> None:
        """Gracefully terminate the shell session."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            logger.info("Shell session terminated")
