"""Tests for WebRTC transport, RTCPeerConnection wrapper, DataChannels, and signaling handshake."""

import asyncio
import json
import threading
import time
import pytest
import uvicorn
from aiortc import RTCSessionDescription

from backend.config import Settings
from backend.signaling.client import SignalingClient
from backend.signaling.server import app
from backend.transport.data_channels import DataChannelError
from backend.transport.peer_connection import (
    PeerConnectionError,
    PeerConnectionWrapper,
    establish_webrtc_connection,
    filter_host_addresses,
    prioritize_stun_servers,
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


def test_filter_host_addresses_filters_virtual_interfaces(monkeypatch):
    """Verify that filter_host_addresses filters VirtualBox, Docker, and other virtual host interfaces."""
    from typing import NamedTuple, List, Union

    class MockIP(NamedTuple):
        ip: Union[str, tuple]

    class MockAdapter(NamedTuple):
        name: str
        ips: List[MockIP]

    mock_adapters = [
        MockAdapter("lo", [MockIP("127.0.0.1")]),
        MockAdapter("vboxnet0", [MockIP("192.168.56.1")]),
        MockAdapter("docker0", [MockIP("172.17.0.1")]),
        MockAdapter("br-abc1234", [MockIP("172.21.33.171")]),
        MockAdapter("virbr0", [MockIP("192.168.122.1")]),
        MockAdapter("wlp2s0", [MockIP("192.168.1.100")]),
    ]

    import ifaddr
    monkeypatch.setattr(ifaddr, "get_adapters", lambda: mock_adapters)

    filtered = filter_host_addresses(use_ipv4=True, use_ipv6=False)
    assert filtered == ["192.168.1.100"]

    # When inside a container, eth0 is not filtered
    container_adapters = [
        MockAdapter("lo", [MockIP("127.0.0.1")]),
        MockAdapter("eth0", [MockIP("172.21.0.5")]),
    ]
    monkeypatch.setattr(ifaddr, "get_adapters", lambda: container_adapters)
    filtered_container = filter_host_addresses(use_ipv4=True, use_ipv6=False)
    assert filtered_container == ["172.21.0.5"]


def test_prioritize_stun_servers_ordering(monkeypatch):
    """Verify prioritize_stun_servers places the responsive STUN server at index 0."""
    import backend.transport.peer_connection as pc_mod

    def mock_probe(host: str, port: int, timeout: float = 0.35) -> bool:
        return host == "stun.responsive.org"

    monkeypatch.setattr(pc_mod, "probe_single_stun", mock_probe)

    urls = [
        "stun:stun.dead.org:19302",
        "stun:stun.responsive.org:3478",
        "stun:stun.other.org:19302",
    ]
    prioritized = prioritize_stun_servers(urls)
    assert prioritized[0] == "stun:stun.responsive.org:3478"
    assert len(prioritized) == 3


@pytest.mark.asyncio
async def test_diagnose_ice_failure_diagnostics():
    """Verify _diagnose_ice_failure correctly identifies Symmetric NAT/CGNAT, missing srflx, and TURN status."""
    from unittest.mock import PropertyMock, patch
    from aiortc import RTCPeerConnection

    pc = PeerConnectionWrapper(role="send")
    try:
        desc_local_srflx = RTCSessionDescription(
            sdp="v=0\r\na=candidate:1 1 udp 2130706431 10.0.0.1 50000 typ host\r\n"
                "a=candidate:2 1 udp 1694498815 210.212.227.213 54388 typ srflx raddr 10.0.0.1 rport 50000\r\n",
            type="offer",
        )
        desc_remote_srflx = RTCSessionDescription(
            sdp="v=0\r\na=candidate:3 1 udp 2130706431 192.168.1.50 50000 typ host\r\n"
                "a=candidate:4 1 udp 1694498815 115.240.12.5 54388 typ srflx raddr 192.168.1.50 rport 50000\r\n",
            type="answer",
        )
        desc_remote_host = RTCSessionDescription(
            sdp="v=0\r\na=candidate:3 1 udp 2130706431 192.168.1.50 50000 typ host\r\n",
            type="answer",
        )
        desc_local_host = RTCSessionDescription(
            sdp="v=0\r\na=candidate:1 1 udp 2130706431 10.0.0.1 50000 typ host\r\n",
            type="offer",
        )

        with patch.object(RTCPeerConnection, "localDescription", new_callable=PropertyMock) as m_local, \
             patch.object(RTCPeerConnection, "remoteDescription", new_callable=PropertyMock) as m_remote:

            # 1. Both have srflx but disconnected (Symmetric NAT / CGNAT scenario)
            m_local.return_value = desc_local_srflx
            m_remote.return_value = desc_remote_srflx
            diag = pc._diagnose_ice_failure()
            assert "Symmetric NAT" in diag
            assert "TURN" in diag

            # 2. Remote peer has only private host candidates
            m_remote.return_value = desc_remote_host
            diag_missing_remote = pc._diagnose_ice_failure()
            assert "Remote peer did not gather any public (srflx) candidates" in diag_missing_remote

            # 3. Neither peer has srflx
            m_local.return_value = desc_local_host
            diag_neither = pc._diagnose_ice_failure()
            assert "Neither peer gathered public (srflx) candidates" in diag_neither

    finally:
        await pc.close()


@pytest.mark.asyncio
async def test_turn_configuration_initialization():
    """Verify that TURN server configuration is parsed and passed to RTCPeerConnection."""
    settings = Settings(
        turn_url="turn:turn.example.com:3478?transport=udp,turn:turn.example.com:3478?transport=tcp",
        turn_username="testuser",
        turn_credential="testsecret",
        _env_file=None,
    )
    wrapper = PeerConnectionWrapper(settings=settings, role="send")
    try:
        # Check that TURN iceServer is configured
        turn_servers = [s for s in wrapper.configuration.iceServers if any("turn:" in u for u in (s.urls if isinstance(s.urls, list) else [s.urls]))]
        assert len(turn_servers) == 1
        ts = turn_servers[0]
        assert ts.username == "testuser"
        assert ts.credential == "testsecret"
    finally:
        await wrapper.close()

