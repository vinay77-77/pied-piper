"""Command-line reference peer client for Pied Piper.

Phase 1 Stub: Parses CLI arguments, resolves configuration, prints settings,
and exits cleanly without initiating any networking.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from backend.config import Settings, get_settings


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
        "--file",
        "-f",
        type=Path,
        default=None,
        help="Path to file to send (applicable for 'send' role)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Directory to save received files (applicable for 'receive' role)",
    )
    parser.add_argument(
        "--room-code",
        "-c",
        type=str,
        default=None,
        help="6-character room code to join (applicable for 'receive' role)",
    )
    return parser


def format_config_summary(role: str, signaling_url: str, settings: Settings) -> str:
    """Format resolved peer parameters and configuration into a clean summary."""
    stun_display = ", ".join(settings.stun_urls_list) if settings.stun_urls_list else "None"
    lines = [
        "============================================================",
        "              Pied Piper — CLI Reference Peer               ",
        "============================================================",
        f"Role:             {role}",
        f"Signaling URL:    {signaling_url}",
        f"Environment:      {settings.environment}",
        f"Log Level:        {settings.log_level}",
        f"Chunk Size:       {settings.chunk_size_bytes} bytes",
        f"Sliding Window:   {settings.sliding_window_size}",
        f"STUN URLs:        {stun_display}",
        f"SQLite DB Path:   {settings.sqlite_path}",
        f"Room TTL:         {settings.room_ttl_seconds}s",
        "============================================================",
        "[Phase 1] CLI stub executed successfully. No networking active.",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    signaling_url = args.signaling_url if args.signaling_url is not None else settings.signaling_url

    summary = format_config_summary(
        role=args.role,
        signaling_url=signaling_url,
        settings=settings,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
