"""Command-line reference peer client for Pied Piper.

Drives the signaling rendezvous, WebRTC peer connection, and DataChannel verification flow (Phase 4):
- Sender creates room, establishes WebRTC connection, and opens 'control' and 'data' channels.
- Receiver joins room, completes WebRTC connection, and receives 'control' and 'data' channels.
- Both peers verify bidirectional communication:
  1. Control channel: JSON ping/pong message round-trip.
  2. Data channel: Binary payload transfer verified byte-for-byte.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

from backend.config import Settings, get_settings
from backend.signaling.client import SignalingClient, SignalingError
from backend.transport.data_channels import DataChannelError
from backend.transport.peer_connection import (
    PeerConnectionError,
    establish_webrtc_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pied-piper-peer")

TEST_BINARY_SENDER = b"PIED_PIPER_DATA_CHANNEL_TEST_PAYLOAD_FROM_SENDER_\x00\x01\xfe\xff\x42"
TEST_BINARY_RECEIVER = b"PIED_PIPER_DATA_CHANNEL_TEST_PAYLOAD_FROM_RECEIVER_\x00\x01\xfe\xff\x24"


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="pied-piper-peer",
        description="Pied Piper P2P File Transfer CLI Reference Peer",
    )
    parser.add_argument(
        "--role",
        "-r",
        choices=["send", "receive"],
        required=True,
        help="Operating role for this peer ('send' or 'receive')",
    )
    parser.add_argument(
        "--signaling-url",
        "-s",
        type=str,
        default=None,
        help="WebSocket URL for the signaling service (defaults to config SIGNALING_URL)",
    )
    parser.add_argument(
        "--room-code",
        "-c",
        type=str,
        default=None,
        help="6-character room code to join (required for 'receive' role in Phase 2+)",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=None,
        help="Path to file to send (applicable for 'send' role in Phase 5+)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Directory to save received files (applicable for 'receive' role in Phase 5+)",
    )
    return parser


def format_config_summary(role: str, signaling_url: str, settings: Settings, room_code: Optional[str] = None) -> str:
    """Format resolved peer parameters and configuration into a clean summary."""
    stun_display = ", ".join(settings.stun_urls_list) if settings.stun_urls_list else "None"
    lines = [
        "============================================================",
        "              Pied Piper — CLI Reference Peer               ",
        "============================================================",
        f"Role:             {role}",
        f"Signaling URL:    {signaling_url}",
    ]
    if room_code:
        lines.append(f"Room Code:        {room_code}")
    lines.extend([
        f"Environment:      {settings.environment}",
        f"Log Level:        {settings.log_level}",
        f"Chunk Size:       {settings.chunk_size_bytes} bytes",
        f"Sliding Window:   {settings.sliding_window_size}",
        f"STUN URLs:        {stun_display}",
        f"SQLite DB Path:   {settings.sqlite_path}",
        f"Room TTL:         {settings.room_ttl_seconds}s",
        "============================================================",
    ])
    return "\n".join(lines)


async def run_sender_flow(signaling_url: str, settings: Settings) -> int:
    """Run signaling rendezvous, WebRTC handshake, and DataChannel verification for sender."""
    logger.info("Connecting to signaling server: %s", signaling_url)
    async with SignalingClient(signaling_url) as client:
        room_code = await client.create_room(timeout=10.0)
        print("\n" + "=" * 60)
        print(f"  ROOM CREATED: {room_code}")
        print("  Share this 6-character room code with the receiving peer.")
        print("  Waiting for peer to join...")
        print("=" * 60 + "\n")

        await client.wait_for_peer(timeout=float(settings.room_ttl_seconds))
        print("\n[+] Peer joined room. Establishing WebRTC connection & DataChannels...")

        # Negotiate WebRTC connection and wait for DataChannels
        pc_wrapper = await establish_webrtc_connection(
            role="send",
            signaling_client=client,
            settings=settings,
            timeout=30.0,
        )

        try:
            print("\n[+] Connection established. Running DataChannel verification...")

            # 1. Send test control ping
            ping_payload = {"type": "ping", "message": "ping from sender", "ts": time.time()}
            pc_wrapper.channels.send_control(ping_payload)
            logger.info("Sent test ping on 'control' channel")

            # 2. Send test binary payload on data channel
            pc_wrapper.channels.send_data(TEST_BINARY_SENDER)
            logger.info("Sent %d bytes on 'data' channel", len(TEST_BINARY_SENDER))

            # 3. Receive pong on control channel
            pong_msg_str = await pc_wrapper.channels.receive_control(timeout=10.0)
            pong_msg = json.loads(pong_msg_str)
            logger.info("Received control reply: %s", pong_msg)

            # 4. Receive binary response on data channel
            received_data = await pc_wrapper.channels.receive_data(timeout=10.0)
            if received_data != TEST_BINARY_RECEIVER:
                raise DataChannelError("Received binary payload did not match expected receiver bytes")
            logger.info("Received %d bytes on 'data' channel (byte-for-byte verified)", len(received_data))

            # Drain buffer before exit
            await asyncio.sleep(0.2)

            print("\n" + "=" * 60)
            print("  DATACHANNELS ESTABLISHED & VERIFIED!")
            print(f"  Connection State: {pc_wrapper.connection_state}")
            print("  Control Channel:  OPEN (JSON/text ping-pong verified)")
            print(f"  Data Channel:     OPEN ({len(received_data)} bytes verified byte-for-byte)")
            print("============================================================\n")
            return 0

        finally:
            await pc_wrapper.close()


async def run_receiver_flow(signaling_url: str, room_code: str, settings: Settings) -> int:
    """Run signaling rendezvous, WebRTC handshake, and DataChannel verification for receiver."""
    code = room_code.strip().upper()
    logger.info("Connecting to signaling server %s for room: %s", signaling_url, code)
    async with SignalingClient(signaling_url) as client:
        await client.join_room(code, timeout=10.0)
        print(f"\n[+] Joining room {code} on signaling server...")
        await client.wait_for_peer(timeout=float(settings.room_ttl_seconds))
        print("\n[+] Rendezvous confirmed. Establishing WebRTC connection & DataChannels...")

        # Negotiate WebRTC connection and wait for DataChannels
        pc_wrapper = await establish_webrtc_connection(
            role="receive",
            signaling_client=client,
            settings=settings,
            timeout=30.0,
        )

        try:
            print("\n[+] Connection established. Running DataChannel verification...")

            # 1. Receive test control ping
            ping_msg_str = await pc_wrapper.channels.receive_control(timeout=10.0)
            ping_msg = json.loads(ping_msg_str)
            logger.info("Received control message: %s", ping_msg)

            # 2. Receive test binary payload on data channel
            received_data = await pc_wrapper.channels.receive_data(timeout=10.0)
            if received_data != TEST_BINARY_SENDER:
                raise DataChannelError("Received binary payload did not match expected sender bytes")
            logger.info("Received %d bytes on 'data' channel (byte-for-byte verified)", len(received_data))

            # 3. Send control pong reply
            pong_payload = {"type": "pong", "message": "pong from receiver", "ts": time.time()}
            pc_wrapper.channels.send_control(pong_payload)
            logger.info("Sent test pong on 'control' channel")

            # 4. Send binary response on data channel
            pc_wrapper.channels.send_data(TEST_BINARY_RECEIVER)
            logger.info("Sent %d bytes on 'data' channel", len(TEST_BINARY_RECEIVER))

            # Drain buffer before exit
            await asyncio.sleep(0.2)

            print("\n" + "=" * 60)
            print("  DATACHANNELS ESTABLISHED & VERIFIED!")
            print(f"  Connection State: {pc_wrapper.connection_state}")
            print("  Control Channel:  OPEN (JSON/text ping-pong verified)")
            print(f"  Data Channel:     OPEN ({len(received_data)} bytes verified byte-for-byte)")
            print("============================================================\n")
            return 0

        finally:
            await pc_wrapper.close()


async def async_main(argv: Optional[List[str]] = None) -> int:
    """Async CLI entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    signaling_url = args.signaling_url if args.signaling_url is not None else settings.signaling_url

    print(format_config_summary(
        role=args.role,
        signaling_url=signaling_url,
        settings=settings,
        room_code=args.room_code,
    ))

    try:
        if args.role == "send":
            return await run_sender_flow(signaling_url, settings)
        elif args.role == "receive":
            if not args.room_code:
                print("Error: --room-code is required for 'receive' role.", file=sys.stderr)
                return 1
            return await run_receiver_flow(signaling_url, args.room_code, settings)
        else:
            print(f"Error: Unknown role '{args.role}'", file=sys.stderr)
            return 1
    except (SignalingError, PeerConnectionError, DataChannelError, OSError) as exc:
        print(f"\nConnection / Transport Error: {exc}", file=sys.stderr)
        return 1
    except asyncio.CancelledError:
        print("\nOperation cancelled.", file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
