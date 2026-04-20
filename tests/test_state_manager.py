"""Tests for state manager."""

from __future__ import annotations

import time

from src.state_manager import StateManager


class TestStateManager:
    """State management and peer tracking."""

    def test_initial_state_no_active_pc(self, tmp_path) -> None:
        state = StateManager(machine_name="test", state_file=tmp_path / "state.json")
        assert state.active_pc == ""
        assert not state.is_active

    def test_activate_sets_active_pc(self, tmp_path) -> None:
        state = StateManager(machine_name="desktop", state_file=tmp_path / "state.json")
        state.activate("desktop")
        assert state.active_pc == "desktop"
        assert state.is_active

    def test_activate_different_pc_deactivates_self(self, tmp_path) -> None:
        state = StateManager(machine_name="desktop", state_file=tmp_path / "state.json")
        state.activate("laptop")
        assert state.active_pc == "laptop"
        assert not state.is_active

    def test_self_registered_as_peer_on_init(self, tmp_path) -> None:
        state = StateManager(machine_name="mypc", state_file=tmp_path / "state.json")
        peers = state.get_online_peers()
        assert len(peers) == 1
        assert peers[0].name == "mypc"

    def test_register_heartbeat_updates_timestamp(self, tmp_path) -> None:
        state = StateManager(machine_name="pc1", state_file=tmp_path / "state.json")
        state.register_heartbeat("pc2")
        peers = state.get_online_peers()
        names = {p.name for p in peers}
        assert "pc1" in names
        assert "pc2" in names

    def test_stale_peers_excluded_from_online_list(self, tmp_path) -> None:
        state = StateManager(machine_name="pc1", state_file=tmp_path / "state.json")
        state.register_heartbeat("old_pc")
        # Artificially age the heartbeat
        state._peers["old_pc"].last_heartbeat = time.time() - 300
        peers = state.get_online_peers(max_age=120)
        names = {p.name for p in peers}
        assert "old_pc" not in names
        assert "pc1" in names

    def test_state_persists_to_disk(self, tmp_path) -> None:
        state_file = tmp_path / "state.json"
        state = StateManager(machine_name="pc1", state_file=state_file)
        state.activate("desktop")
        assert state_file.exists()

        # Load in a new instance
        state2 = StateManager(machine_name="pc2", state_file=state_file)
        assert state2.active_pc == "desktop"
