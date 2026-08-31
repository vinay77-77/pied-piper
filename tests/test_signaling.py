"""Tests for signaling components, rooms, and registry."""

import asyncio
import time
import pytest

from backend.signaling.rooms import (
    ROOM_CODE_CHARS,
    ROOM_CODE_LENGTH,
    Room,
    RoomRegistry,
    RoomState,
    generate_room_code,
)


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
    # Ensure randomness / high entropy across 100 iterations
    assert len(codes) == 100


def test_room_lifecycle():
    """Verify Room state transitions, peer tracking, and expiration."""
    room = Room(code="AB3XYZ", ttl_seconds=10)
    assert room.code == "AB3XYZ"
    assert room.state == RoomState.WAITING_FOR_PEER
    assert not room.is_full
    assert not room.is_expired(now=room.created_at + 5)
    assert room.is_expired(now=room.created_at + 11)

    # Adding peers
    ws1, ws2, ws3 = object(), object(), object()
    assert room.add_peer(ws1) is True
    assert room.add_peer(ws1) is False  # duplicate peer
    assert not room.is_full
    assert room.other_peer(ws1) is None

    assert room.add_peer(ws2) is True
    assert room.is_full is True
    assert room.add_peer(ws3) is False  # capacity full

    assert room.other_peer(ws1) is ws2
    assert room.other_peer(ws2) is ws1

    # Transition to connected (early expiration on success)
    room.mark_connected()
    assert room.state == RoomState.CONNECTED
    assert not room.is_expired(now=room.created_at + 1000)

    # Remove peer
    assert room.remove_peer(ws1) is True
    assert not room.is_full


@pytest.mark.asyncio
async def test_room_registry_create_and_join():
    """Verify RoomRegistry creation, joining, and 3rd peer rejection."""
    registry = RoomRegistry(default_ttl_seconds=300)
    room = await registry.create_room()
    assert len(room.code) == 6

    ws1, ws2, ws3 = object(), object(), object()

    # Peer 1 joins
    joined_room, error = await registry.join_room(room.code, ws1)
    assert joined_room is room
    assert error is None

    # Peer 2 joins
    joined_room, error = await registry.join_room(room.code, ws2)
    assert joined_room is room
    assert error is None
    assert room.is_full is True

    # Peer 3 joins (should be rejected)
    rejected_room, error = await registry.join_room(room.code, ws3)
    assert rejected_room is None
    assert error == "Room is full (maximum 2 peers allowed)"


@pytest.mark.asyncio
async def test_room_registry_nonexistent_or_expired_code():
    """Verify RoomRegistry handles nonexistent codes properly."""
    registry = RoomRegistry()
    room, error = await registry.join_room("NONEXIST", object())
    assert room is None
    assert "not found" in error.lower()


@pytest.mark.asyncio
async def test_room_registry_ttl_sweep():
    """Verify RoomRegistry sweeps expired WAITING_FOR_PEER rooms."""
    registry = RoomRegistry(default_ttl_seconds=5)
    room = await registry.create_room(ttl_seconds=5)
    code = room.code

    # Not expired yet
    swept = await registry.sweep_expired_rooms(now=room.created_at + 2)
    assert code not in swept
    assert await registry.get_room(code) is not None

    # Swept after TTL
    swept = await registry.sweep_expired_rooms(now=room.created_at + 6)
    assert code in swept
    assert await registry.get_room(code) is None


@pytest.mark.asyncio
async def test_room_registry_immediate_expire():
    """Verify immediate expiration of rooms on peer disconnect."""
    registry = RoomRegistry()
    room = await registry.create_room()
    code = room.code

    expired_room = await registry.expire_room(code)
    assert expired_room is not None
    assert expired_room.state == RoomState.EXPIRED
    assert await registry.get_room(code) is None


@pytest.mark.asyncio
async def test_room_registry_background_sweeper():
    """Verify starting and stopping background sweeper task."""
    registry = RoomRegistry(default_ttl_seconds=1)
    task = registry.start_ttl_sweeper(interval_seconds=0.05)
    assert not task.done()
    await registry.stop_ttl_sweeper()
    assert task.done()
