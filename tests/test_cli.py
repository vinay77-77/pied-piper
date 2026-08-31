"""Tests for backend.cli.peer CLI entrypoint, rendezvous, and WebRTC connection flow."""

import asyncio
import threading
import time
import pytest
import uvicorn

from backend.cli.peer import async_main, main
from backend.signaling.server import app


@pytest.fixture(scope="module")
def signaling_test_server():
    """Start an in-process signaling server on a dedicated local test port."""
    port = 8765
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config=config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    time.sleep(0.5)
    yield f"ws://127.0.0.1:{port}/ws"

    server.should_exit = True
    thread.join(timeout=2.0)


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


def test_cli_peer_receive_requires_room_code(capsys):
    """Verify receive role without --room-code returns exit code 1."""
    exit_code = main(["--role", "receive"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "--room-code is required" in captured.err


@pytest.mark.asyncio
async def test_cli_webrtc_end_to_end(signaling_test_server):
    """Test full sender and receiver CLI peer WebRTC connection flow over live test WebSocket server."""
    from backend.signaling.client import SignalingClient

    # Connect sender client to create room
    async with SignalingClient(signaling_test_server) as sender_sig:
        room_code = await sender_sig.create_room()
        assert len(room_code) == 6

        # Run sender WebRTC connection in background task using CLI entrypoint
        async def run_sender():
            from backend.transport.peer_connection import establish_webrtc_connection
            await sender_sig.wait_for_peer(timeout=5.0)
            pc = await establish_webrtc_connection(
                role="send",
                signaling_client=sender_sig,
                timeout=5.0,
            )
            is_conn = pc.is_connected
            await pc.close()
            return is_conn

        sender_task = asyncio.create_task(run_sender())

        # Run receiver CLI
        receiver_exit_code = await async_main([
            "--role", "receive",
            "--room-code", room_code,
            "--signaling-url", signaling_test_server,
        ])

        sender_connected = await asyncio.wait_for(sender_task, timeout=5.0)

        assert receiver_exit_code == 0
        assert sender_connected is True
