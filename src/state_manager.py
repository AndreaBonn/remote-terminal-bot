"""Multi-PC state management using Telegram as broadcast channel."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_NAME = "telegram-terminal-bot"


def _default_state_path() -> Path:
    """Return XDG-compliant state file path."""
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    app_dir = data_home / _APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "state.json"


@dataclass
class PeerInfo:
    """Information about a connected peer machine."""

    name: str
    last_heartbeat: float = 0.0


@dataclass
class StateManager:
    """Manages active PC state and peer heartbeat tracking.

    State is synchronized via Telegram broadcast — all PCs receive
    /activate commands and update their local state accordingly.
    """

    machine_name: str
    heartbeat_interval: int = 60
    state_file: Path = field(default_factory=lambda: _default_state_path())
    _active_pc: str = ""
    _peers: dict[str, PeerInfo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_state()
        self._register_self()

    @property
    def active_pc(self) -> str:
        """Name of the currently active PC."""
        return self._active_pc

    @property
    def is_active(self) -> bool:
        """Whether this machine is the currently active one."""
        return self._active_pc == self.machine_name

    def activate(self, pc_name: str) -> None:
        """Set the active PC. Called on all machines when /activate is received.

        Parameters
        ----------
        pc_name : str
            Name of the PC to activate.
        """
        self._active_pc = pc_name
        self._save_state()
        logger.info("Active PC set to: %s", pc_name)

    def register_heartbeat(self, pc_name: str) -> None:
        """Register a heartbeat from a peer machine.

        Parameters
        ----------
        pc_name : str
            Name of the machine that sent the heartbeat.
        """
        if pc_name not in self._peers:
            self._peers[pc_name] = PeerInfo(name=pc_name)
        self._peers[pc_name].last_heartbeat = time.time()

    def _register_self(self) -> None:
        """Register this machine in the peer list."""
        self.register_heartbeat(self.machine_name)

    def get_online_peers(self, max_age: float = 120.0) -> list[PeerInfo]:
        """Get list of peers with recent heartbeats.

        Parameters
        ----------
        max_age : float
            Maximum seconds since last heartbeat to consider online.

        Returns
        -------
        list[PeerInfo]
            Peers with heartbeat within max_age seconds.
        """
        now = time.time()
        return [peer for peer in self._peers.values() if (now - peer.last_heartbeat) <= max_age]

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._active_pc = data.get("active_pc", "")
        except (json.JSONDecodeError, OSError) as err:
            logger.warning("Failed to load state file: %s", err)

    def _save_state(self) -> None:
        """Persist current state to disk (atomic write via rename)."""
        data = {
            "active_pc": self._active_pc,
            "last_updated": time.time(),
        }
        tmp_file = self.state_file.with_suffix(".tmp")
        try:
            tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_file.replace(self.state_file)
            self.state_file.chmod(0o600)
        except OSError as err:
            logger.error("Failed to save state file: %s", err)
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
