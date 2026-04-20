"""Tests for utility functions."""

from __future__ import annotations

from src.utils import format_output, format_timeout_message, split_text


class TestSplitText:
    """Text splitting for Telegram message limits."""

    def test_short_text_returns_single_chunk(self) -> None:
        assert split_text("hello", max_length=100) == ["hello"]

    def test_splits_at_line_boundaries(self) -> None:
        text = "line1\nline2\nline3\nline4"
        chunks = split_text(text, max_length=12)
        assert all(len(c) <= 12 for c in chunks)
        # All content preserved
        assert "\n".join(chunks) == text or set("".join(chunks)) == set(text.replace("\n", ""))

    def test_long_single_line_force_splits(self) -> None:
        text = "a" * 100
        chunks = split_text(text, max_length=30)
        assert len(chunks) == 4  # 30+30+30+10
        assert "".join(chunks) == text

    def test_empty_text_returns_single_chunk(self) -> None:
        assert split_text("") == [""]

    def test_exact_boundary_no_split(self) -> None:
        text = "a" * 4000
        chunks = split_text(text, max_length=4000)
        assert len(chunks) == 1


class TestFormatOutput:
    """Output formatting for Telegram messages."""

    def test_no_output_success_shows_checkmark(self) -> None:
        result = format_output("", exit_code=0)
        assert result == ["✅ Comando eseguito (nessun output)"]

    def test_output_wrapped_in_code_block(self) -> None:
        result = format_output("hello world", exit_code=0)
        assert len(result) == 1
        assert result[0] == "```\nhello world\n```"

    def test_nonzero_exit_code_appended(self) -> None:
        result = format_output("error msg", exit_code=1)
        assert len(result) == 2
        assert result[0] == "```\nerror msg\n```"
        assert result[1] == "⚠️ Exit code: 1"

    def test_no_output_with_error_shows_only_exit_code(self) -> None:
        result = format_output("", exit_code=127)
        assert result == ["⚠️ Exit code: 127"]

    def test_long_output_splits_into_numbered_chunks(self) -> None:
        text = "x" * 8000
        result = format_output(text, exit_code=0)
        assert len(result) >= 2
        assert "[1/" in result[0]


class TestFormatTimeoutMessage:
    """Timeout message formatting."""

    def test_includes_timeout_value(self) -> None:
        msg = format_timeout_message(30)
        assert "30" in msg
        assert "Timeout" in msg

    def test_custom_timeout_value(self) -> None:
        msg = format_timeout_message(120)
        assert "120" in msg
