"""Tests for WebRTC transport, RTCPeerConnection wrapper, DataChannels, and signaling handshake."""

import asyncio
import json
import threading
import time
import pytest
import uvicorn

from backend.config import Settings
from backend.signaling.client import SignalingClient
from backend.signaling.server import app
from backend.transport.data_channels import DataChannelError
from backend.transport.peer_connection import (
    PeerConnectionError,
    PeerConnectionWrapper,
    establish_webrtc_connection,
)


@pytest.fixture(scope="module")
def signaling_transport_server():
    """Start a dedicated test signaling server for transport tests."""
    port = 8766
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config=config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)

    yield f"ws://127.0.0.1:{port}/ws"

    server.should_exit = True
    thread.join(timeout=2.0)


@pytest.mark.asyncio
async def test_peer_connection_wrapper_init():
    """Verify PeerConnectionWrapper initializes with STUN configuration from Settings."""
    settings = Settings(
        stun_urls="stun:stun1.example.com:19302, stun:stun2.example.com:19302",
        _env_file=None,
    )
    wrapper = PeerConnectionWrapper(settings=settings, role="send")
    try:
        assert wrapper.role == "send"
        assert len(wrapper.configuration.iceServers) == 2
        assert "stun:stun1.example.com:19302" in wrapper.configuration.iceServers[0].urls
    finally:
        await wrapper.close()


@pytest.mark.asyncio
async def test_direct_peer_connection_and_datachannels_handshake():
    """Verify two PeerConnectionWrapper instances complete SDP offer/answer and open DataChannels."""
    pc1 = PeerConnectionWrapper(role="send")
    pc2 = PeerConnectionWrapper(role="receive")

    try:
        offer = await pc1.create_offer()
        answer = await pc2.handle_offer(offer)
        await pc1.handle_answer(answer)

        # Wait for connections and DataChannels to open
        await asyncio.gather(
            pc1.wait_connected(timeout=5.0),
            pc2.wait_connected(timeout=5.0),
        )
        await asyncio.gather(
            pc1.wait_channels_open(timeout=5.0),
            pc2.wait_channels_open(timeout=5.0),
        )

        assert pc1.is_connected and pc2.is_connected
        assert pc1.channels.are_channels_open
        assert pc2.channels.are_channels_open

        # ---------------------------------------------------------------------
        # 1. Test bidirectional messaging on control channel (JSON/text)
        # ---------------------------------------------------------------------
        pc1.channels.send_control({"type": "ping", "data": "hello from pc1"})
        msg_pc2_str = await pc2.channels.receive_control(timeout=2.0)
        msg_pc2 = json.loads(msg_pc2_str)
        assert msg_pc2["type"] == "ping"
        assert msg_pc2["data"] == "hello from pc1"

        pc2.channels.send_control({"type": "pong", "data": "hello from pc2"})
        msg_pc1_str = await pc1.channels.receive_control(timeout=2.0)
        msg_pc1 = json.loads(msg_pc1_str)
        assert msg_pc1["type"] == "pong"
        assert msg_pc1["data"] == "hello from pc2"

        # ---------------------------------------------------------------------
        # 2. Test bidirectional binary blob transfer on data channel
        # ---------------------------------------------------------------------
        test_binary_1 = b"\x00\x01\x02\xfe\xff" * 1024  # 5 KB binary data
        pc1.channels.send_data(test_binary_1)
        received_binary_2 = await pc2.channels.receive_data(timeout=2.0)
        assert received_binary_2 == test_binary_1

        test_binary_2 = b"\xde\xad\xbe\xef" * 512
        pc2.channels.send_data(test_binary_2)
        received_binary_1 = await pc1.channels.receive_data(timeout=2.0)
        assert received_binary_1 == test_binary_2

    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_datachannel_closure():
    """Verify DataChannel closure is detected and logged."""
    pc1 = PeerConnectionWrapper(role="send")
    pc2 = PeerConnectionWrapper(role="receive")

    try:
        offer = await pc1.create_offer()
        answer = await pc2.handle_offer(offer)
        await pc1.handle_answer(answer)

        await asyncio.gather(
            pc1.wait_channels_open(timeout=5.0),
            pc2.wait_channels_open(timeout=5.0),
        )

        # Close pc1 channels
        pc1.channels.close()

        # pc2 should detect close
        await asyncio.wait_for(
            asyncio.gather(
                pc2.channels.control_closed_event.wait(),
                pc2.channels.data_closed_event.wait(),
            ),
            timeout=5.0,
        )
        assert pc2.channels.control_closed_event.is_set()
        assert pc2.channels.data_closed_event.is_set()

        # Sending on closed channel should raise DataChannelError
        with pytest.raises(DataChannelError):
            pc1.channels.send_control("test")
        with pytest.raises(DataChannelError):
            pc1.channels.send_data(b"test")

    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_ice_candidate_queueing_before_remote_description():
    """Verify ICE candidates can be queued and flushed after remote description is set."""
    pc1 = PeerConnectionWrapper(role="send")
    pc2 = PeerConnectionWrapper(role="receive")

    try:
        offer = await pc1.create_offer()

        dummy_candidate = {
            "candidate": "candidate:1 1 UDP 2130706431 127.0.0.1 50000 typ host",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        }
        await pc2.handle_candidate(dummy_candidate)
        assert len(pc2._pending_candidates) == 1

        answer = await pc2.handle_offer(offer)
        assert len(pc2._pending_candidates) == 0

        await pc1.handle_answer(answer)
        await asyncio.gather(
            pc1.wait_connected(timeout=5.0),
            pc2.wait_connected(timeout=5.0),
        )
    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_peer_connection_timeout_raises_error():
    """Verify wait_connected raises PeerConnectionError on timeout."""
    pc = PeerConnectionWrapper(role="send")
    try:
        with pytest.raises(PeerConnectionError) as exc_info:
            await pc.wait_connected(timeout=0.05)
        assert "timed out" in str(exc_info.value).lower()
    finally:
        await pc.close()


@pytest.mark.asyncio
async def test_establish_webrtc_connection_over_signaling(signaling_transport_server):
    """Verify full end-to-end WebRTC connection and DataChannels coordinated via signaling service."""
    async with SignalingClient(signaling_transport_server) as sender_sig:
        room_code = await sender_sig.create_room()

        async with SignalingClient(signaling_transport_server) as receiver_sig:
            await receiver_sig.join_room(room_code)

            await asyncio.gather(
                sender_sig.wait_for_peer(timeout=5.0),
                receiver_sig.wait_for_peer(timeout=5.0),
            )

            sender_pc, receiver_pc = await asyncio.gather(
                establish_webrtc_connection(
                    role="send",
                    signaling_client=sender_sig,
                    timeout=5.0,
                ),
                establish_webrtc_connection(
                    role="receive",
                    signaling_client=receiver_sig,
                    timeout=5.0,
                ),
            )

            try:
                assert sender_pc.is_connected
                assert receiver_pc.is_connected
                assert sender_pc.channels.are_channels_open
                assert receiver_pc.channels.are_channels_open

                # Test control message
                sender_pc.channels.send_control({"type": "test_signal", "val": 123})
                received_msg = json.loads(await receiver_pc.channels.receive_control(timeout=2.0))
                assert received_msg["val"] == 123

                # Test binary blob
                sender_pc.channels.send_data(b"Signaling relayed binary test")
                received_blob = await receiver_pc.channels.receive_data(timeout=2.0)
                assert received_blob == b"Signaling relayed binary test"

            finally:
                await sender_pc.close()
                await receiver_pc.close()
