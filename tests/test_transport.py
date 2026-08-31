"""Tests for WebRTC transport, RTCPeerConnection wrapper, and signaling-coordinated handshake."""

import asyncio
import threading
import time
import pytest
import uvicorn

from backend.config import Settings
from backend.signaling.client import SignalingClient
from backend.signaling.server import app
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
async def test_direct_peer_connection_handshake():
    """Verify two PeerConnectionWrapper instances complete SDP offer/answer and reach connected state."""
    pc1 = PeerConnectionWrapper(role="send")
    pc2 = PeerConnectionWrapper(role="receive")

    try:
        # Offerer creates offer
        offer = await pc1.create_offer()
        assert offer["type"] == "offer"
        assert "v=0" in offer["sdp"]

        # Answerer handles offer and creates answer
        answer = await pc2.handle_offer(offer)
        assert answer["type"] == "answer"
        assert "v=0" in answer["sdp"]

        # Offerer handles answer
        await pc1.handle_answer(answer)

        # Wait for both sides to reach connected
        await asyncio.gather(
            pc1.wait_connected(timeout=5.0),
            pc2.wait_connected(timeout=5.0),
        )

        assert pc1.is_connected
        assert pc2.is_connected
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

        # Simulate early candidate arriving before handle_offer
        dummy_candidate = {
            "candidate": "candidate:1 1 UDP 2130706431 127.0.0.1 50000 typ host",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        }
        await pc2.handle_candidate(dummy_candidate)
        assert len(pc2._pending_candidates) == 1

        # Now set remote offer
        answer = await pc2.handle_offer(offer)
        # Pending candidates should have been flushed
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
    """Verify full end-to-end WebRTC connection coordinated via signaling service."""
    async with SignalingClient(signaling_transport_server) as sender_sig:
        room_code = await sender_sig.create_room()

        async with SignalingClient(signaling_transport_server) as receiver_sig:
            await receiver_sig.join_room(room_code)

            # Both peers wait for rendezvous
            await asyncio.gather(
                sender_sig.wait_for_peer(timeout=5.0),
                receiver_sig.wait_for_peer(timeout=5.0),
            )

            # Now run establish_webrtc_connection concurrently
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
                assert sender_pc.connection_state in ("connected", "completed")
                assert receiver_pc.connection_state in ("connected", "completed")
            finally:
                await sender_pc.close()
                await receiver_pc.close()
