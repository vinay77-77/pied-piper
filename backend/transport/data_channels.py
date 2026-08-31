"""DataChannel management for control (JSON/text) and data (binary) streams."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union

from aiortc import RTCDataChannel, RTCPeerConnection

logger = logging.getLogger(__name__)


class DataChannelError(Exception):
    """Exception raised when a DataChannel operation fails."""
    pass


class DataChannelManager:
    """Manages control (ordered JSON/text) and data (ordered binary) DataChannels."""

    def __init__(self) -> None:
        self.control_channel: Optional[RTCDataChannel] = None
        self.data_channel: Optional[RTCDataChannel] = None

        self.control_open_event: asyncio.Event = asyncio.Event()
        self.data_open_event: asyncio.Event = asyncio.Event()
        self.control_closed_event: asyncio.Event = asyncio.Event()
        self.data_closed_event: asyncio.Event = asyncio.Event()

        self.control_queue: asyncio.Queue[str] = asyncio.Queue()
        self.data_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def setup_offerer_channels(self, pc: RTCPeerConnection) -> None:
        """Create 'control' and 'data' channels as offerer/sender."""
        logger.info("Creating 'control' and 'data' DataChannels (offerer)")
        self.control_channel = pc.createDataChannel("control", ordered=True)
        self.data_channel = pc.createDataChannel("data", ordered=True)

        self._bind_channel(self.control_channel)
        self._bind_channel(self.data_channel)

    def setup_answerer_channels(self, pc: RTCPeerConnection) -> None:
        """Listen for incoming DataChannels on the answering peer."""
        @pc.on("datachannel")
        def on_datachannel(channel: RTCDataChannel) -> None:
            logger.info("Received incoming DataChannel with label '%s' (id: %s)", channel.label, channel.id)
            if channel.label == "control":
                self.control_channel = channel
                self._bind_channel(channel)
            elif channel.label == "data":
                self.data_channel = channel
                self._bind_channel(channel)
            else:
                logger.warning("Unknown DataChannel label received: %s", channel.label)

    def _bind_channel(self, channel: RTCDataChannel) -> None:
        """Attach event handlers to an RTCDataChannel."""
        label = channel.label

        @channel.on("open")
        def on_open() -> None:
            logger.info("DataChannel '%s' is now OPEN (id: %s)", label, channel.id)
            if label == "control":
                self.control_open_event.set()
            elif label == "data":
                self.data_open_event.set()

        @channel.on("close")
        def on_close() -> None:
            logger.info("DataChannel '%s' has CLOSED", label)
            if label == "control":
                self.control_closed_event.set()
            elif label == "data":
                self.data_closed_event.set()

        @channel.on("error")
        def on_error(error: Any) -> None:
            logger.error("DataChannel '%s' encountered an error: %s", label, error)

        @channel.on("message")
        def on_message(message: Union[str, bytes]) -> None:
            logger.debug("Received message on DataChannel '%s' (%d bytes/chars)", label, len(message))
            if label == "control":
                if isinstance(message, bytes):
                    text = message.decode("utf-8", errors="replace")
                else:
                    text = str(message)
                self.control_queue.put_nowait(text)
            elif label == "data":
                if isinstance(message, str):
                    blob = message.encode("utf-8")
                else:
                    blob = message
                self.data_queue.put_nowait(blob)

        # In case channel is already open upon registration
        if channel.readyState == "open":
            if label == "control":
                self.control_open_event.set()
            elif label == "data":
                self.data_open_event.set()

    @property
    def is_control_open(self) -> bool:
        """Check if control channel is open."""
        return self.control_channel is not None and self.control_channel.readyState == "open"

    @property
    def is_data_open(self) -> bool:
        """Check if data channel is open."""
        return self.data_channel is not None and self.data_channel.readyState == "open"

    @property
    def are_channels_open(self) -> bool:
        """Check if both control and data channels are open."""
        return self.is_control_open and self.is_data_open

    async def wait_channels_open(self, timeout: float = 15.0) -> None:
        """Wait until both control and data channels reach 'open' readyState."""
        if self.are_channels_open:
            return

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    self.control_open_event.wait(),
                    self.data_open_event.wait(),
                ),
                timeout=timeout,
            )
            logger.info("Both 'control' and 'data' channels are OPEN")
        except asyncio.TimeoutError as exc:
            ctrl_state = self.control_channel.readyState if self.control_channel else "None"
            data_state = self.data_channel.readyState if self.data_channel else "None"
            raise DataChannelError(
                f"DataChannels failed to open within {timeout}s (control: {ctrl_state}, data: {data_state})"
            ) from exc

    def send_control(self, message: Union[str, Dict[str, Any]]) -> None:
        """Send a JSON/text message over the control channel."""
        if not self.is_control_open or self.control_channel is None:
            raise DataChannelError("Control channel is not open")

        if isinstance(message, dict):
            payload_str = json.dumps(message)
        else:
            payload_str = str(message)

        self.control_channel.send(payload_str)
        logger.debug("Sent control message: %s", payload_str)

    def send_data(self, payload: bytes) -> None:
        """Send binary chunk payload over the data channel."""
        if not self.is_data_open or self.data_channel is None:
            raise DataChannelError("Data channel is not open")

        if not isinstance(payload, bytes):
            raise TypeError("send_data expects bytes payload")

        self.data_channel.send(payload)
        logger.debug("Sent data payload (%d bytes)", len(payload))

    async def receive_control(self, timeout: Optional[float] = 10.0) -> str:
        """Receive the next text message from the control channel."""
        try:
            if timeout is not None:
                return await asyncio.wait_for(self.control_queue.get(), timeout=timeout)
            return await self.control_queue.get()
        except asyncio.TimeoutError as exc:
            raise DataChannelError("Timed out waiting for control message") from exc

    async def receive_data(self, timeout: Optional[float] = 10.0) -> bytes:
        """Receive the next binary chunk from the data channel."""
        try:
            if timeout is not None:
                return await asyncio.wait_for(self.data_queue.get(), timeout=timeout)
            return await self.data_queue.get()
        except asyncio.TimeoutError as exc:
            raise DataChannelError("Timed out waiting for data payload") from exc

    def close(self) -> None:
        """Close both control and data channels."""
        if self.control_channel:
            self.control_channel.close()
        if self.data_channel:
            self.data_channel.close()
        logger.info("DataChannelManager closed")
