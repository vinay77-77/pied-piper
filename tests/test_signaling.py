"""Tests for signaling components, rooms, messages, and WebSocket server."""

import asyncio
import json
import time
import pytest
from starlette.testclient import TestClient

from backend.signaling.messages import (
    ConnectedMessage,
    CreateRoomMessage,
    ErrorMessage,
    JoinRoomMessage,
    PeerJoinedMessage,
    RelayedSignalMessage,
    RoomCreatedMessage,
    RoomExpiredMessage,
    SignalMessage,
    parse_client_message,
)
from backend.signaling.rooms import (
    ROOM_CODE_CHARS,
    ROOM_CODE_LENGTH,
    Room,
    RoomRegistry,
    RoomState,
    generate_room_code,
)
from backend.signaling.server import app, registry


# -----------------------------------------------------------------------------
# Room & Registry Unit Tests
# -----------------------------------------------------------------------------

def test_generate_room_code():
    """Verify room codes are 6 characters and use the unambiguous charset."""
    codes = set()
    for _ in range(100):
        code = generate_room_code()
        assert len(code) == ROOM_CODE_LENGTH
        assert all(c in ROOM_CODE_CHARS for c in code)
        for ambiguous in ("0", "O", "1", "I", "L"):
            assert ambiguous not in code
        codes.add(code)
    assert len(codes) == 100


def test_room_lifecycle():
    """Verify Room state transitions, peer tracking, and expiration."""
    room = Room(code="AB3XYZ", ttl_seconds=10)
    assert room.code == "AB3XYZ"
    assert room.state == RoomState.WAITING_FOR_PEER
    assert not room.is_full
    assert not room.is_expired(now=room.created_at + 5)
    assert room.is_expired(now=room.created_at + 11)

    ws1, ws2, ws3 = object(), object(), object()
    assert room.add_peer(ws1) is True
    assert room.add_peer(ws1) is False
    assert not room.is_full
    assert room.other_peer(ws1) is None

    assert room.add_peer(ws2) is True
    assert room.is_full is True
    assert room.add_peer(ws3) is False

    assert room.other_peer(ws1) is ws2
    assert room.other_peer(ws2) is ws1

    room.mark_connected()
    assert room.state == RoomState.CONNECTED
    assert not room.is_expired(now=room.created_at + 1000)

    assert room.remove_peer(ws1) is True
    assert not room.is_full


@pytest.mark.asyncio
async def test_room_registry_create_and_join():
    """Verify RoomRegistry creation, joining, and 3rd peer rejection."""
    reg = RoomRegistry(default_ttl_seconds=300)
    room = await reg.create_room()
    assert len(room.code) == 6

    ws1, ws2, ws3 = object(), object(), object()

    joined_room, error = await reg.join_room(room.code, ws1)
    assert joined_room is room
    assert error is None

    joined_room, error = await reg.join_room(room.code, ws2)
    assert joined_room is room
    assert error is None
    assert room.is_full is True

    rejected_room, error = await reg.join_room(room.code, ws3)
    assert rejected_room is None
    assert error == "Room is full (maximum 2 peers allowed)"


@pytest.mark.asyncio
async def test_room_registry_nonexistent_or_expired_code():
    """Verify RoomRegistry handles nonexistent codes properly."""
    reg = RoomRegistry()
    room, error = await reg.join_room("NONEXIST", object())
    assert room is None
    assert "not found" in error.lower()


@pytest.mark.asyncio
async def test_room_registry_ttl_sweep():
    """Verify RoomRegistry sweeps expired WAITING_FOR_PEER rooms."""
    reg = RoomRegistry(default_ttl_seconds=5)
    room = await reg.create_room(ttl_seconds=5)
    code = room.code

    swept = await reg.sweep_expired_rooms(now=room.created_at + 2)
    assert code not in swept
    assert await reg.get_room(code) is not None

    swept = await reg.sweep_expired_rooms(now=room.created_at + 6)
    assert code in swept
    assert await reg.get_room(code) is None


@pytest.mark.asyncio
async def test_room_registry_immediate_expire():
    """Verify immediate expiration of rooms."""
    reg = RoomRegistry()
    room = await reg.create_room()
    code = room.code

    expired_room = await reg.expire_room(code)
    assert expired_room is not None
    assert expired_room.state == RoomState.EXPIRED
    assert await reg.get_room(code) is None


@pytest.mark.asyncio
async def test_room_registry_background_sweeper():
    """Verify starting and stopping background sweeper task."""
    reg = RoomRegistry(default_ttl_seconds=1)
    task = reg.start_ttl_sweeper(interval_seconds=0.05)
    assert not task.done()
    await reg.stop_ttl_sweeper()
    assert task.done()


# -----------------------------------------------------------------------------
# Message Schema Tests
# -----------------------------------------------------------------------------

def test_message_serialization_and_parsing():
    """Verify message models parse and validate correctly."""
    msg = parse_client_message('{"type": "create_room"}')
    assert isinstance(msg, CreateRoomMessage)

    msg = parse_client_message('{"type": "join_room", "room_code": "AB3XYZ"}')
    assert isinstance(msg, JoinRoomMessage)
    assert msg.room_code == "AB3XYZ"

    msg = parse_client_message('{"type": "signal", "payload": {"sdp": "v=0..."}}')
    assert isinstance(msg, SignalMessage)
    assert msg.payload == {"sdp": "v=0..."}

    msg = parse_client_message('{"type": "connected"}')
    assert isinstance(msg, ConnectedMessage)


# -----------------------------------------------------------------------------
# Server WebSocket Endpoint Tests
# -----------------------------------------------------------------------------

def test_health_endpoint():
    """Verify GET /health returns 200 healthy."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_signaling_full_rendezvous_flow():
    """Verify complete create_room, join_room, and signal relay between two peers."""
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws1:
        # Peer 1 creates room
        ws1.send_text(json.dumps({"type": "create_room"}))
        resp1 = json.loads(ws1.receive_text())
        assert resp1["type"] == "room_created"
        room_code = resp1["room_code"]
        assert len(room_code) == 6

        with client.websocket_connect("/ws") as ws2:
            # Peer 2 joins room
            ws2.send_text(json.dumps({"type": "join_room", "room_code": room_code}))

            # Both peers should receive peer_joined
            msg_ws1 = json.loads(ws1.receive_text())
            assert msg_ws1["type"] == "peer_joined"

            msg_ws2 = json.loads(ws2.receive_text())
            assert msg_ws2["type"] == "peer_joined"

            # Peer 1 sends signal (e.g. SDP offer)
            offer_payload = {"type": "offer", "sdp": "v=0\r\no=test..."}
            ws1.send_text(json.dumps({"type": "signal", "payload": offer_payload}))

            # Peer 2 receives relayed signal verbatim
            signal_received_by_ws2 = json.loads(ws2.receive_text())
            assert signal_received_by_ws2["type"] == "signal"
            assert signal_received_by_ws2["payload"] == offer_payload

            # Peer 2 sends answer signal
            answer_payload = {"type": "answer", "sdp": "v=0\r\no=test_ans..."}
            ws2.send_text(json.dumps({"type": "signal", "payload": answer_payload}))

            # Peer 1 receives relayed answer verbatim
            signal_received_by_ws1 = json.loads(ws1.receive_text())
            assert signal_received_by_ws1["type"] == "signal"
            assert signal_received_by_ws1["payload"] == answer_payload

            # Peers report connected
            ws1.send_text(json.dumps({"type": "connected"}))


def test_signaling_third_peer_rejected():
    """Verify a 3rd peer attempting to join an active room is rejected."""
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws1:
        ws1.send_text(json.dumps({"type": "create_room"}))
        resp = json.loads(ws1.receive_text())
        room_code = resp["room_code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_text(json.dumps({"type": "join_room", "room_code": room_code}))
            ws1.receive_text()  # peer_joined
            ws2.receive_text()  # peer_joined

            with client.websocket_connect("/ws") as ws3:
                ws3.send_text(json.dumps({"type": "join_room", "room_code": room_code}))
                resp3 = json.loads(ws3.receive_text())
                assert resp3["type"] == "error"
                assert "full" in resp3["reason"].lower()


def test_signaling_join_nonexistent_room():
    """Verify joining a nonexistent room returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join_room", "room_code": "XXXXXX"}))
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "error"
        assert "not found" in resp["reason"].lower()


def test_signaling_peer_disconnect_expires_waiting_room():
    """Verify peer disconnecting before CONNECTED expires the room for the other peer."""
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws1:
        ws1.send_text(json.dumps({"type": "create_room"}))
        resp = json.loads(ws1.receive_text())
        room_code = resp["room_code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_text(json.dumps({"type": "join_room", "room_code": room_code}))
            ws1.receive_text()  # peer_joined
            ws2.receive_text()  # peer_joined

        # ws2 closed/exited here
        # ws1 should receive room_expired
        msg = json.loads(ws1.receive_text())
        assert msg["type"] == "room_expired"
