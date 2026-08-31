"""Tests for backend.cli.peer CLI entrypoint."""

import pytest
from backend.cli.peer import main


def test_cli_peer_send_role(capsys):
    """Verify running CLI with --role send prints correct summary and exits 0."""
    exit_code = main(["--role", "send"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Role:             send" in captured.out
    assert "Signaling URL:    ws://localhost:8000/ws" in captured.out
    assert "[Phase 1] CLI stub executed successfully." in captured.out


def test_cli_peer_receive_custom_signaling_url(capsys):
    """Verify running CLI with --role receive and explicit --signaling-url."""
    custom_url = "ws://192.168.1.50:9000/ws"
    exit_code = main(["--role", "receive", "--signaling-url", custom_url])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Role:             receive" in captured.out
    assert f"Signaling URL:    {custom_url}" in captured.out


def test_cli_peer_requires_role():
    """Verify CLI raises error if --role is omitted."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_cli_peer_invalid_role():
    """Verify CLI raises error if invalid role is passed."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--role", "invalid_role"])
    assert exc_info.value.code != 0
