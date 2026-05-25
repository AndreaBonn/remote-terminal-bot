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

    def test_existing_peer_heartbeat_updates_only_timestamp(self, tmp_path) -> None:
        state = StateManager(machine_name="pc1", state_file=tmp_path / "state.json")
        state.register_heartbeat("peer-a")
        first_ts = state._peers["peer-a"].last_heartbeat

        time.sleep(0.01)
        state.register_heartbeat("peer-a")
        second_ts = state._peers["peer-a"].last_heartbeat

        assert second_ts > first_ts
        assert len(state._peers) == 2  # self + peer-a, no duplicate created

    def test_load_state_handles_corrupt_json(self, tmp_path, caplog) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("{not valid json", encoding="utf-8")

        # Must not raise; active_pc stays empty
        state = StateManager(machine_name="pc1", state_file=state_file)
        assert state.active_pc == ""
        assert any("Failed to load state file" in r.message for r in caplog.records)

    def test_load_state_handles_unreadable_file(self, tmp_path, caplog) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text('{"active_pc": "desktop"}', encoding="utf-8")
        state_file.chmod(0o000)
        try:
            state = StateManager(machine_name="pc1", state_file=state_file)
            assert state.active_pc == ""
        finally:
            state_file.chmod(0o600)

    def test_save_state_handles_oserror(self, tmp_path, caplog, monkeypatch) -> None:
        state = StateManager(machine_name="pc1", state_file=tmp_path / "state.json")

        def _raise(*_args, **_kwargs):
            raise OSError("disk full")

        # Patch the tmp file write to fail
        monkeypatch.setattr("pathlib.Path.write_text", _raise)
        state.activate("desktop")  # Triggers _save_state

        assert any("Failed to save state file" in r.message for r in caplog.records)
        assert state.active_pc == "desktop"  # In-memory state still updated

    def test_save_state_handles_unlink_oserror_during_cleanup(
        self, tmp_path, caplog, monkeypatch
    ) -> None:
        """If the temp file cleanup itself raises OSError, _save_state must swallow it."""
        state = StateManager(machine_name="pc1", state_file=tmp_path / "state.json")

        def _raise_write(*_args, **_kwargs):
            raise OSError("disk full during write")

        def _raise_unlink(*_args, **_kwargs):
            raise OSError("permission denied during cleanup")

        # The primary write fails AND the cleanup unlink also fails — the outer
        # try/except OSError around unlink must prevent the cleanup error from
        # propagating and masking the original failure log.
        monkeypatch.setattr("pathlib.Path.write_text", _raise_write)
        monkeypatch.setattr("pathlib.Path.unlink", _raise_unlink)
        state.activate("desktop")  # Triggers _save_state

        assert any("Failed to save state file" in r.message for r in caplog.records)
        assert state.active_pc == "desktop"
