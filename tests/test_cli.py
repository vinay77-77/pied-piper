"""Tests for backend.cli.peer CLI entrypoint, rendezvous, WebRTC, and DataChannels."""

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
async def test_cli_datachannels_end_to_end(signaling_test_server):
    """Test full sender and receiver CLI peer WebRTC and DataChannel verification flow concurrently."""
    from backend.signaling.client import SignalingClient

    # Connect sender client to create room
    async with SignalingClient(signaling_test_server) as sender_sig:
        room_code = await sender_sig.create_room()
        assert len(room_code) == 6

        from backend.transport.peer_connection import establish_webrtc_connection
        from backend.cli.peer import TEST_BINARY_SENDER, TEST_BINARY_RECEIVER
        import json

        async def run_sender_peer():
            await sender_sig.wait_for_peer(timeout=10.0)
            pc_wrapper = await establish_webrtc_connection(
                role="send",
                signaling_client=sender_sig,
                timeout=10.0,
            )
            try:
                # 1. Send test control ping
                pc_wrapper.channels.send_control({"type": "ping", "message": "ping from sender"})
                # 2. Send test binary payload
                pc_wrapper.channels.send_data(TEST_BINARY_SENDER)

                # 3. Receive pong
                pong_str = await pc_wrapper.channels.receive_control(timeout=10.0)
                pong = json.loads(pong_str)
                assert pong["type"] == "pong"

                # 4. Receive binary response
                data = await pc_wrapper.channels.receive_data(timeout=10.0)
                assert data == TEST_BINARY_RECEIVER
                return 0
            finally:
                await pc_wrapper.close()

        async def run_receiver_cli():
            # Run receiver CLI
            return await async_main([
                "--role", "receive",
                "--room-code", room_code,
                "--signaling-url", signaling_test_server,
            ])

        # Run sender peer and receiver CLI concurrently
        sender_code, receiver_code = await asyncio.gather(
            run_sender_peer(),
            run_receiver_cli(),
        )

        assert receiver_code == 0
        assert sender_code == 0
