"""Tests for audit log."""

from __future__ import annotations

import json

from src.audit_log import AuditLog


class TestAuditLog:
    """Audit log behavior."""

    def test_record_creates_jsonl_entry(self, tmp_path) -> None:
        audit = AuditLog(log_dir=tmp_path)
        audit.record(
            command="ls -la",
            exit_code=0,
            timed_out=False,
            machine_name="test-pc",
            duration_ms=150,
        )

        log_file = tmp_path / "audit.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["command"] == "ls -la"
        assert entry["exit_code"] == 0
        assert entry["timed_out"] is False
        assert entry["machine"] == "test-pc"
        assert entry["duration_ms"] == 150
        assert "ts" in entry

    def test_record_appends_multiple_entries(self, tmp_path) -> None:
        audit = AuditLog(log_dir=tmp_path)
        audit.record(
            command="echo 1",
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=10,
        )
        audit.record(
            command="echo 2",
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=20,
        )

        log_file = tmp_path / "audit.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_record_truncates_long_commands(self, tmp_path) -> None:
        audit = AuditLog(log_dir=tmp_path)
        long_cmd = "x" * 5000
        audit.record(
            command=long_cmd,
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=10,
        )

        log_file = tmp_path / "audit.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert len(entry["command"]) == 2048

    def test_record_does_not_raise_on_readonly_dir(self, tmp_path) -> None:
        read_only = tmp_path / "readonly"
        read_only.mkdir()
        audit = AuditLog(log_dir=read_only)
        # Make the file read-only after creation
        log_file = read_only / "audit.jsonl"
        log_file.touch()
        log_file.chmod(0o444)
        # Should not raise
        audit.record(
            command="test",
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=10,
        )
