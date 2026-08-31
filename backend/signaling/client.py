"""Async WebSocket client for the Pied Piper signaling service."""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional, Union

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


class SignalingError(Exception):
    """Exception raised when a signaling protocol or server error occurs."""
    pass


class SignalingClient:
    """Async WebSocket client to interact with the Pied Piper signaling server."""

    def __init__(self, url: str) -> None:
        self.url: str = url
        self._ws: Optional[ClientConnection] = None
        self._incoming_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._listener_task: Optional[asyncio.Task] = None
        self._closed: bool = False

    async def connect(self) -> None:
        """Establish WebSocket connection to the signaling server."""
        if self._ws is not None:
            return
        logger.info("Connecting to signaling server at %s", self.url)
        self._ws = await websockets.connect(self.url)
        self._closed = False
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def close(self) -> None:
        """Close the WebSocket connection and stop background listener."""
        self._closed = True
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("Signaling client closed")

    async def __aenter__(self) -> "SignalingClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _send_json(self, data: Dict[str, Any]) -> None:
        """Send a JSON-encoded dictionary to the server."""
        if self._ws is None:
            raise SignalingError("Not connected to signaling server")
        await self._ws.send(json.dumps(data))

    async def _listen_loop(self) -> None:
        """Background loop reading incoming messages from WebSocket."""
        try:
            while not self._closed and self._ws is not None:
                raw_msg = await self._ws.recv()
                data = json.loads(raw_msg)
                await self._incoming_queue.put(data)
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.error("Error in signaling client listener: %s", exc)

    async def receive_message(self, timeout: Optional[float] = 30.0) -> Dict[str, Any]:
        """Wait for the next incoming server message."""
        try:
            msg = await asyncio.wait_for(self._incoming_queue.get(), timeout=timeout)
            if msg.get("type") == "error":
                raise SignalingError(msg.get("reason", "Unknown signaling server error"))
            return msg
        except asyncio.TimeoutError:
            raise SignalingError("Timed out waiting for signaling server response")

    async def create_room(self, timeout: float = 10.0) -> str:
        """Request creation of a new room. Returns the 6-character room code."""
        await self._send_json({"type": "create_room"})
        resp = await self.receive_message(timeout=timeout)
        if resp.get("type") != "room_created":
            raise SignalingError(f"Unexpected response to create_room: {resp}")
        return resp["room_code"]

    async def join_room(self, room_code: str, timeout: float = 10.0) -> None:
        """Request to join an existing room by code."""
        await self._send_json({"type": "join_room", "room_code": room_code})

    async def wait_for_peer(self, timeout: Optional[float] = 900.0) -> None:
        """Wait until peer_joined message is received from the server."""
        resp = await self.receive_message(timeout=timeout)
        if resp.get("type") != "peer_joined":
            if resp.get("type") == "room_expired":
                raise SignalingError("Room expired before peer joined")
            raise SignalingError(f"Unexpected message while waiting for peer: {resp}")

    async def send_signal(self, payload: Any) -> None:
        """Send an opaque WebRTC signaling payload (SDP or ICE candidate)."""
        await self._send_json({"type": "signal", "payload": payload})

    async def report_connected(self) -> None:
        """Notify signaling server that WebRTC connection is established."""
        await self._send_json({"type": "connected"})

    async def messages(self) -> AsyncIterator[Dict[str, Any]]:
        """Async generator yielding incoming messages until disconnected."""
        while not self._closed:
            try:
                msg = await self.receive_message(timeout=None)
                yield msg
            except SignalingError:
                break
