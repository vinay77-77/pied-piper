"""Command-line reference peer client for Pied Piper.

Drives the signaling rendezvous flow (Phase 2):
- Sender creates a room, prints the 6-character code, and waits for receiver.
- Receiver joins using the 6-character code.
- Both peers confirm rendezvous upon receiving 'peer_joined'.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

from backend.config import Settings, get_settings
from backend.signaling.client import SignalingClient, SignalingError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pied-piper-peer")


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


async def run_sender_rendezvous(signaling_url: str, settings: Settings) -> int:
    """Run signaling rendezvous flow for sender peer."""
    logger.info("Starting sender peer rendezvous with signaling server: %s", signaling_url)
    async with SignalingClient(signaling_url) as client:
        room_code = await client.create_room(timeout=10.0)
        print("\n" + "=" * 60)
        print(f"  ROOM CREATED: {room_code}")
        print("  Share this 6-character room code with the receiving peer.")
        print("  Waiting for peer to join...")
        print("=" * 60 + "\n")

        await client.wait_for_peer(timeout=float(settings.room_ttl_seconds))
        print("\n" + "=" * 60)
        print(f"  PEER JOINED ROOM {room_code}!")
        print("  Signaling rendezvous successful.")
        print("=" * 60 + "\n")
        return 0


async def run_receiver_rendezvous(signaling_url: str, room_code: str, settings: Settings) -> int:
    """Run signaling rendezvous flow for receiver peer."""
    code = room_code.strip().upper()
    logger.info("Starting receiver peer rendezvous for room: %s", code)
    async with SignalingClient(signaling_url) as client:
        await client.join_room(code, timeout=10.0)
        print(f"\nJoining room {code} on signaling server {signaling_url}...")
        await client.wait_for_peer(timeout=float(settings.room_ttl_seconds))
        print("\n" + "=" * 60)
        print(f"  SUCCESSFULLY JOINED ROOM {code}!")
        print("  Signaling rendezvous successful.")
        print("=" * 60 + "\n")
        return 0


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
            return await run_sender_rendezvous(signaling_url, settings)
        elif args.role == "receive":
            if not args.room_code:
                print("Error: --room-code is required for 'receive' role.", file=sys.stderr)
                return 1
            return await run_receiver_rendezvous(signaling_url, args.room_code, settings)
        else:
            print(f"Error: Unknown role '{args.role}'", file=sys.stderr)
            return 1
    except (SignalingError, OSError) as exc:
        print(f"\nSignaling Error: {exc}", file=sys.stderr)
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
