# Pied Piper 🚀

A peer-to-peer (P2P) file transfer engine built on WebRTC DataChannels with an ephemeral WebSocket signaling service, receiver-authoritative sliding-window protocol, chunk-level SHA-256 integrity verification, and SQLite transfer state persistence.

---

## Architecture Overview

```
Desktop App (Human Developer)
    │  (consumes async event callbacks)
    ▼
Transfer API (`backend/api/transfer_api.py`)
    │
    ▼
Transfer Orchestration (`backend/transfer/`)
    │
    ▼
Protocol Layer (`backend/protocol/`)
    │
    ▼
Transport Layer (`backend/transport/`)  [aiortc RTCPeerConnection: control + data DataChannels]
    │
    ▼
Signaling Client (`backend/signaling/`) [WebSocket room management, SDP/ICE relay]
```

For complete technical specifications, see [PROJECT.md](PROJECT.md) and [docs/milestone_1_lan.md](docs/milestone_1_lan.md).

---

## Repository Structure

```
pied-piper/
├── README.md
├── PROJECT.md
├── LICENSE                       # MIT
├── .env.example
├── .gitignore
├── requirements.txt
├── docs/
│   └── milestone_1_lan.md        # Phases 1–6 specifications
├── backend/
│   ├── __init__.py
│   ├── config.py                 # Typed settings loader with .env support
│   ├── signaling/                # FastAPI signaling server & room management
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── rooms.py
│   │   └── messages.py
│   ├── transport/                # aiortc WebRTC peer connection & DataChannels
│   │   ├── __init__.py
│   │   ├── peer_connection.py
│   │   └── data_channels.py
│   ├── protocol/                 # Wire framing, chunking, hashing, window logic
│   │   ├── __init__.py
│   │   ├── framing.py
│   │   ├── chunking.py
│   │   └── window.py
│   ├── transfer/                 # Transfer orchestration, sender/receiver, SQLite store
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── state_store.py
│   │   ├── sender.py
│   │   └── receiver.py
│   ├── api/                      # Async Transfer API for desktop frontend
│   │   ├── __init__.py
│   │   └── transfer_api.py
│   └── cli/                      # Reference peer CLI client
│       ├── __init__.py
│       └── peer.py
├── desktop/                      # Desktop UI integration boundary
│   └── README.md
└── tests/                        # Automated test suite
    ├── __init__.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_signaling.py
    ├── test_transport.py
    ├── test_protocol.py
    └── test_transfer.py
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Standard `venv` and `pip`

### 1. Virtual Environment Setup

Create and activate a virtual environment:

```bash
# Create virtual environment
python -m venv env

# Activate virtual environment
# On Linux / macOS:
source env/bin/activate

# On Windows (Command Prompt / PowerShell):
# env\Scripts\activate.bat   (cmd)
# .\env\Scripts\Activate.ps1  (PowerShell)
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the sample environment configuration:

```bash
cp .env.example .env
```

Key configuration parameters (`backend/config.py`):
| Key | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Environment mode |
| `SIGNALING_HOST` | `0.0.0.0` | Host to bind signaling server |
| `SIGNALING_PORT` | `8000` | Port to bind signaling server |
| `SIGNALING_URL` | `ws://localhost:8000/ws` | WebSocket endpoint for signaling |
| `STUN_URLS` | `stun:stun.l.google.com:19302` | STUN server URLs for NAT traversal |
| `CHUNK_SIZE_BYTES`| `16384` | Transfer chunk size (16 KB) |
| `SLIDING_WINDOW_SIZE` | `32` | Sliding window capacity |
| `SQLITE_PATH` | `./pied_piper.db` | Local SQLite database path |
| `ROOM_TTL_SECONDS`| `900` | Ephemeral room TTL (15 minutes) |

---

## Running the CLI Reference Peer (Phase 1 Stub)

The reference CLI peer entrypoint is located at `backend/cli/peer.py`.

### Send Mode
```bash
python -m backend.cli.peer --role send
```

### Receive Mode (with Custom Signaling URL)
```bash
python -m backend.cli.peer --role receive --signaling-url ws://192.168.1.100:8000/ws
```

---

## Running Tests

Run the full automated test suite with `pytest`:

```bash
pytest -v
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
