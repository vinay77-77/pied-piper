"""Tests for backend.cli.peer CLI entrypoint, argument validation, and live file transfer."""

import asyncio
from pathlib import Path
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


def test_cli_peer_send_requires_file(capsys):
    """Verify send role without --file returns exit code 1."""
    exit_code = main(["--role", "send"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "--file is required" in captured.err


@pytest.mark.asyncio
async def test_cli_file_transfer_end_to_end(signaling_test_server, tmp_path: Path):
    """Test full end-to-end CLI peer file transfer over live test WebSocket signaling server."""
    from backend.signaling.client import SignalingClient
    from backend.transport.peer_connection import establish_webrtc_connection
    from backend.transfer.sender import FileSender

    sender_dir = tmp_path / "cli_sender"
    receiver_dir = tmp_path / "cli_receiver"
    sender_dir.mkdir()
    receiver_dir.mkdir()

    # Create a 32 KB test file
    test_file = sender_dir / "cli_test_doc.bin"
    file_bytes = b"PIED_PIPER_CLI_E2E_FILE_TRANSFER_TEST_DATA_" * 750
    test_file.write_bytes(file_bytes)

    # Sender client creates room
    async with SignalingClient(signaling_test_server) as sender_sig:
        room_code = await sender_sig.create_room()
        assert len(room_code) == 6

        async def run_sender_process():
            await sender_sig.wait_for_peer(timeout=10.0)
            pc_wrapper = await establish_webrtc_connection(
                role="send",
                signaling_client=sender_sig,
                timeout=10.0,
            )
            try:
                sender = FileSender(
                    channels=pc_wrapper.channels,
                    filepath=test_file,
                    chunk_size=8192,
                )
                summary = await sender.send(timeout=10.0)
                assert summary.size_bytes == len(file_bytes)
                # Keep connection open until receiver finishes
                await asyncio.sleep(0.5)
                return 0
            finally:
                await pc_wrapper.close()

        async def run_receiver_cli_process():
            return await async_main([
                "--role", "receive",
                "--room-code", room_code,
                "--output-dir", str(receiver_dir),
                "--signaling-url", signaling_test_server,
            ])

        # Run sender and receiver concurrently
        sender_code, receiver_code = await asyncio.gather(
            run_sender_process(),
            run_receiver_cli_process(),
        )

        assert sender_code == 0
        assert receiver_code == 0

        # Verify file is received and matches byte-for-byte
        received_file = receiver_dir / "cli_test_doc.bin"
        assert received_file.is_file()
        assert received_file.read_bytes() == file_bytes
