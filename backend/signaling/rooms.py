"""Room model, lifecycle management, and code generation for signaling rendezvous."""

import asyncio
import enum
import logging
import secrets
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 30-character keyspace excluding visually ambiguous characters (0, O, 1, I, L)
ROOM_CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
ROOM_CODE_LENGTH = 6


def generate_room_code(length: int = ROOM_CODE_LENGTH) -> str:
    """Generate a random alphanumeric room code excluding ambiguous characters."""
    return "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(length))


class RoomState(str, enum.Enum):
    """Lifecycle states of a signaling room."""
    WAITING_FOR_PEER = "WAITING_FOR_PEER"
    CONNECTED = "CONNECTED"
    EXPIRED = "EXPIRED"


class Room:
    """Represents an ephemeral two-peer rendezvous room."""

    def __init__(self, code: str, ttl_seconds: int = 900) -> None:
        self.code: str = code
        self.ttl_seconds: int = ttl_seconds
        self.created_at: float = time.time()
        self.state: RoomState = RoomState.WAITING_FOR_PEER
        self.peers: List[Any] = []  # WebSocket connection references

    @property
    def is_full(self) -> bool:
        """Check if the room has reached its maximum capacity of 2 peers."""
        return len(self.peers) >= 2

    def is_expired(self, now: Optional[float] = None) -> bool:
        """Check if the room has expired based on TTL while in WAITING_FOR_PEER state."""
        if self.state == RoomState.EXPIRED:
            return True
        if self.state == RoomState.CONNECTED:
            return False
        current_time = now if now is not None else time.time()
        return (current_time - self.created_at) >= self.ttl_seconds

    def add_peer(self, ws: Any) -> bool:
        """Add a peer WebSocket to the room. Returns True if added, False if full."""
        if self.is_full or ws in self.peers:
            return False
        self.peers.append(ws)
        return True

    def remove_peer(self, ws: Any) -> bool:
        """Remove a peer WebSocket from the room."""
        if ws in self.peers:
            self.peers.remove(ws)
            return True
        return False

    def other_peer(self, ws: Any) -> Optional[Any]:
        """Return the other peer in the room, if present."""
        for peer in self.peers:
            if peer != ws:
                return peer
        return None

    def mark_connected(self) -> None:
        """Transition room state to CONNECTED."""
        self.state = RoomState.CONNECTED

    def mark_expired(self) -> None:
        """Transition room state to EXPIRED."""
        self.state = RoomState.EXPIRED


class RoomRegistry:
    """In-memory thread-safe/asyncio room registry with TTL expiration."""

    def __init__(self, default_ttl_seconds: int = 900) -> None:
        self.default_ttl_seconds: int = default_ttl_seconds
        self._rooms: Dict[str, Room] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._sweeper_task: Optional[asyncio.Task] = None

    async def create_room(self, ttl_seconds: Optional[int] = None) -> Room:
        """Generate a unique room code and register a new Room."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        async with self._lock:
            # Retry on code collision
            while True:
                code = generate_room_code()
                if code not in self._rooms:
                    break
            room = Room(code=code, ttl_seconds=ttl)
            self._rooms[code] = room
            logger.info("Room %s created (TTL: %ds)", code, ttl)
            return room

    async def get_room(self, code: str) -> Optional[Room]:
        """Retrieve a room by code, expiring it if its TTL has lapsed."""
        async with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return None
            if room.is_expired():
                room.mark_expired()
                del self._rooms[code]
                logger.info("Room %s expired on access", code)
                return None
            return room

    async def join_room(self, code: str, ws: Any) -> Tuple[Optional[Room], Optional[str]]:
        """Attempt to join a room by code.

        Returns (Room, None) on success, or (None, error_reason) on failure.
        """
        async with self._lock:
            room = self._rooms.get(code)
            if room is None or room.is_expired():
                if room is not None:
                    del self._rooms[code]
                return None, "Room not found or expired"

            if room.state == RoomState.EXPIRED:
                del self._rooms[code]
                return None, "Room is expired"

            if room.is_full:
                return None, "Room is full (maximum 2 peers allowed)"

            added = room.add_peer(ws)
            if not added:
                return None, "Failed to join room"

            logger.info("Peer joined room %s (total peers: %d)", code, len(room.peers))
            return room, None

    async def mark_connected(self, code: str) -> bool:
        """Mark a room as CONNECTED."""
        async with self._lock:
            room = self._rooms.get(code)
            if room:
                room.mark_connected()
                logger.info("Room %s transitioned to CONNECTED", code)
                return True
            return False

    async def expire_room(self, code: str) -> Optional[Room]:
        """Immediately expire and remove a room."""
        async with self._lock:
            room = self._rooms.pop(code, None)
            if room:
                room.mark_expired()
                logger.info("Room %s immediately expired and removed", code)
            return room

    async def sweep_expired_rooms(self, now: Optional[float] = None) -> List[str]:
        """Sweep and remove all expired WAITING_FOR_PEER rooms."""
        expired_codes: List[str] = []
        async with self._lock:
            current_time = now if now is not None else time.time()
            to_remove = [
                code for code, room in self._rooms.items()
                if room.is_expired(current_time)
            ]
            for code in to_remove:
                room = self._rooms.pop(code)
                room.mark_expired()
                expired_codes.append(code)
                logger.info("Room %s swept by TTL expiration", code)
        return expired_codes

    async def _sweep_loop(self, interval_seconds: float = 1.0) -> None:
        """Background loop that periodically sweeps expired rooms."""
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                await self.sweep_expired_rooms()
        except asyncio.CancelledError:
            pass

    def start_ttl_sweeper(self, interval_seconds: float = 1.0) -> asyncio.Task:
        """Start the background TTL sweeper task."""
        if self._sweeper_task is None or self._sweeper_task.done():
            self._sweeper_task = asyncio.create_task(self._sweep_loop(interval_seconds))
            logger.info("Signaling room TTL sweeper started")
        return self._sweeper_task

    async def stop_ttl_sweeper(self) -> None:
        """Stop the background TTL sweeper task."""
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
            logger.info("Signaling room TTL sweeper stopped")
