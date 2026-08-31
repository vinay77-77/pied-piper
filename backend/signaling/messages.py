"""Signaling message schemas and serialization."""

import json
from typing import Annotated, Any, Dict, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


# -----------------------------------------------------------------------------
# Client -> Server Messages
# -----------------------------------------------------------------------------

class CreateRoomMessage(BaseModel):
    """Client requests creation of a new signaling room."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["create_room"] = "create_room"


class JoinRoomMessage(BaseModel):
    """Client requests to join an existing signaling room by code."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["join_room"] = "join_room"
    room_code: str = Field(..., min_length=1, max_length=32)


class SignalMessage(BaseModel):
    """Client sends an opaque WebRTC signaling payload (SDP / ICE candidate)."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["signal"] = "signal"
    payload: Any = Field(..., description="Opaque SDP or ICE candidate payload")


class ConnectedMessage(BaseModel):
    """Client reports successful WebRTC connection establishment."""
    model_config = ConfigDict(extra="ignore")
    type: Literal["connected"] = "connected"


ClientMessage = Annotated[
    Union[CreateRoomMessage, JoinRoomMessage, SignalMessage, ConnectedMessage],
    Field(discriminator="type"),
]

_client_message_adapter = TypeAdapter(ClientMessage)


def parse_client_message(data: Union[str, Dict[str, Any]]) -> ClientMessage:
    """Parse raw JSON string or dictionary into a validated ClientMessage."""
    if isinstance(data, str):
        parsed = json.loads(data)
    else:
        parsed = data
    return _client_message_adapter.validate_python(parsed)


# -----------------------------------------------------------------------------
# Server -> Client Messages
# -----------------------------------------------------------------------------

class RoomCreatedMessage(BaseModel):
    """Server notifies creator of the generated room code."""
    type: Literal["room_created"] = "room_created"
    room_code: str


class PeerJoinedMessage(BaseModel):
    """Server notifies room participants that both peers are present."""
    type: Literal["peer_joined"] = "peer_joined"


class RelayedSignalMessage(BaseModel):
    """Server relays an opaque signaling payload to the other peer."""
    type: Literal["signal"] = "signal"
    payload: Any


class RoomExpiredMessage(BaseModel):
    """Server notifies peer that the room has expired or peer disconnected."""
    type: Literal["room_expired"] = "room_expired"


class ErrorMessage(BaseModel):
    """Server notifies client of an error condition."""
    type: Literal["error"] = "error"
    reason: str


ServerMessage = Annotated[
    Union[RoomCreatedMessage, PeerJoinedMessage, RelayedSignalMessage, RoomExpiredMessage, ErrorMessage],
    Field(discriminator="type"),
]
