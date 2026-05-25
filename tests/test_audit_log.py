"""Tests for audit log."""

from __future__ import annotations

import json

import pytest

from src.audit_log import AuditLog, _redact_command


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

    def test_record_does_not_redact_by_default(self, tmp_path) -> None:
        audit = AuditLog(log_dir=tmp_path)
        audit.record(
            command="curl --token=ABCDEF https://example.com",
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=10,
        )
        entry = json.loads((tmp_path / "audit.jsonl").read_text().strip())
        assert entry["command"] == "curl --token=ABCDEF https://example.com"

    def test_record_redacts_when_enabled(self, tmp_path) -> None:
        audit = AuditLog(log_dir=tmp_path, redact_secrets=True)
        audit.record(
            command="curl --token=ABCDEF https://example.com",
            exit_code=0,
            timed_out=False,
            machine_name="pc1",
            duration_ms=10,
        )
        entry = json.loads((tmp_path / "audit.jsonl").read_text().strip())
        assert entry["command"] == "curl --token=[REDACTED] https://example.com"


class TestRedactCommand:
    """Behavior of the _redact_command helper."""

    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            (
                "curl --password=hunter2 https://x.com",
                "curl --password=[REDACTED] https://x.com",
            ),
            (
                "curl --token=abc.def.ghi https://x.com",
                "curl --token=[REDACTED] https://x.com",
            ),
            (
                "curl --secret=xyz https://x.com",
                "curl --secret=[REDACTED] https://x.com",
            ),
            (
                "tool --api-key=ABC123 --other=keep",
                "tool --api-key=[REDACTED] --other=keep",
            ),
            (
                "tool --API_KEY=ABC123 --other=keep",
                "tool --API_KEY=[REDACTED] --other=keep",
            ),
        ],
    )
    def test_redacts_dashed_secret_flags(self, cmd: str, expected: str) -> None:
        assert _redact_command(cmd) == expected

    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            (
                "mysql -uroot -psecret123 -h db",
                "mysql -uroot -p[REDACTED] -h db",
            ),
            (
                "mysql -psecret -h db",
                "mysql -p[REDACTED] -h db",
            ),
            (
                "mysqldump -uadmin -pTopSecret mydb",
                "mysqldump -uadmin -p[REDACTED] mydb",
            ),
            (
                "mariadb -pX12 -e 'show databases'",
                "mariadb -p[REDACTED] -e 'show databases'",
            ),
        ],
    )
    def test_redacts_mysql_p_pattern(self, cmd: str, expected: str) -> None:
        assert _redact_command(cmd) == expected

    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            (
                "export AWS_SECRET_ACCESS_KEY=AKIAEXAMPLE",
                "export AWS_SECRET_ACCESS_KEY=[REDACTED]",
            ),
            (
                "GITHUB_TOKEN=ghp_abc python deploy.py",
                "GITHUB_TOKEN=[REDACTED] python deploy.py",
            ),
            (
                "DB_PASSWORD=hunter2 ./run.sh",
                "DB_PASSWORD=[REDACTED] ./run.sh",
            ),
            (
                "MYSQL_PWD=secret mysql -e 'select 1'",
                "MYSQL_PWD=[REDACTED] mysql -e 'select 1'",
            ),
        ],
    )
    def test_redacts_env_assignments_with_secret_suffix(self, cmd: str, expected: str) -> None:
        assert _redact_command(cmd) == expected

    def test_does_not_redact_key_path_env_var(self) -> None:
        # KEY_PATH ends in _PATH, not in a secret-ish suffix
        cmd = "KEY_PATH=/etc/ssl/private.pem ./tool"
        assert _redact_command(cmd) == cmd

    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            (
                "curl -H 'Authorization: Bearer xyz123' https://api.x.com",
                "curl -H 'Authorization: Bearer [REDACTED]' https://api.x.com",
            ),
            (
                "curl -H 'Authorization: Basic dXNlcjpwYXNz' https://api.x.com",
                "curl -H 'Authorization: Basic [REDACTED]' https://api.x.com",
            ),
        ],
    )
    def test_redacts_authorization_header(self, cmd: str, expected: str) -> None:
        assert _redact_command(cmd) == expected

    @pytest.mark.parametrize(
        "cmd",
        [
            "ls -la /etc/ssl",
            "git log --oneline -10",
            "docker ps",
            "ps auxf | head -20",
            "echo hello world",
        ],
    )
    def test_does_not_redact_innocuous_commands(self, cmd: str) -> None:
        assert _redact_command(cmd) == cmd
