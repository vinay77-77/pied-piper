# Pied Piper — Project Architecture Hub (PROJECT.md)

## 1. What This Document Is
This is the single source of truth (SSOT) hub for Pied Piper, a peer-to-peer file
transfer system built on WebRTC. It summarizes the overall architecture, technology,
phase roadmap, and points to the detailed spoke documents:

- `docs/milestone_1_lan.md` — implementation-ready detail for Phases 1–6
- `docs/protocol_spec.md` — deep technical design of the application-level transfer protocol
- `docs/milestone_2_core.md` — implementation-ready detail for Phases 7–18

This document is written for **Antigravity**, the AI coding agent implementing the
backend/networking side of the system. Antigravity does **not** implement the desktop
UI. The desktop application is owned independently by a human teammate and integrates
later through the boundary defined in Phase 17.

## 2. Project Overview
Pied Piper allows two peers to establish a WebRTC connection via a lightweight
signaling/rendezvous service and transfer files directly, peer-to-peer, whenever
possible — falling back to TURN relay only when a direct path is unavailable. The
system is built incrementally, from a single-machine proof of concept up through a
production-hardened, resumable, large-file-capable transfer engine with a desktop
front end.

## 3. Team Structure
| Developer | Owns |
|---|---|
| **Antigravity** (AI agent, backend/networking) | Signaling service, room management, WebRTC transport, application-level transfer protocol, persistence, reconnection/resume, integrity, CLI reference peer, backend tests |
| **Human teammate** (desktop/frontend) | Desktop UI/UX, room-code entry flow, file picker, progress display, consuming the backend's async API |

The two developers work in parallel without integrating until Phase 17. The backend
must be fully runnable and testable standalone via the CLI reference peer.

## 4. Confirmed Technology
- Python 3.11+
- FastAPI (signaling service, WebSocket transport)
- `aiortc` (WebRTC: `RTCPeerConnection`, DataChannels)
- `asyncio` throughout
- SQLite (local persistent transfer state)
- SHA-256 (integrity, whole-file and per-chunk)
- Standard `venv` + `pip` (no Poetry/uv)
- Standard library `logging`
- `.env`-based configuration
- Public STUN servers (e.g., Google's) for NAT traversal in early/mid phases; TURN
  provider is an explicit, legitimate TBD deferred to Phase 15

Desktop GUI framework is intentionally undetermined and out of Antigravity's scope.

## 5. Architectural Boundaries & Dependency Direction

```
Desktop App
    │  (consumes)
    ▼
Transfer API (async, event-callback boundary — Phase 17 contract)
    │
    ▼
Transfer Orchestration  (session lifecycle, resume logic, checkpointing)
    │
    ▼
Protocol Layer  (framing, chunk model, ACK/window, hashing — see protocol_spec.md)
    │
    ▼
Transport Layer  (aiortc RTCPeerConnection, two DataChannels: control + data)
    │
    ▼
Signaling Client  (WebSocket to FastAPI signaling service; room join/create, SDP/ICE relay)
```

Rules:
- Lower layers never import from or know about higher layers.
- Signaling has zero knowledge of file/transfer semantics — it only relays opaque
  SDP/ICE payloads and manages room membership.
- Transport knows about DataChannels and connection state, not about chunks, files,
  or hashes.
- The Protocol layer defines wire format and ACK semantics but does not touch the
  filesystem directly — that's Transfer Orchestration's job (it owns SQLite state,
  file I/O, and checkpoint decisions).
- The Transfer API is the **only** thing the desktop app ever touches.

## 6. Repository Structure (initial, to be created)

```
pied-piper/
├── README.md
├── PROJECT.md
├── LICENSE                       # MIT
├── .env.example
├── .gitignore
├── pyproject.toml / requirements.txt
├── docs/
│   ├── milestone_1_lan.md
│   ├── protocol_spec.md
│   └── milestone_2_core.md
├── backend/
│   ├── __init__.py
│   ├── config.py                 # loads .env, exposes typed settings
│   ├── signaling/
│   │   ├── server.py              # FastAPI app, WS endpoint
│   │   ├── rooms.py               # room model, TTL, code generation
│   │   └── messages.py            # signaling message schemas
│   ├── transport/
│   │   ├── peer_connection.py     # aiortc RTCPeerConnection wrapper
│   │   └── data_channels.py       # control + data channel setup
│   ├── protocol/
│   │   ├── framing.py             # message framing / wire format
│   │   ├── chunking.py            # chunk model, hashing
│   │   └── window.py              # sliding window ACK logic
│   ├── transfer/
│   │   ├── session.py             # transfer session orchestration
│   │   ├── state_store.py         # SQLite persistence
│   │   ├── sender.py
│   │   └── receiver.py
│   ├── api/
│   │   └── transfer_api.py        # async boundary for desktop (Phase 17+)
│   └── cli/
│       └── peer.py                # full send/receive reference CLI client
├── desktop/                       # owned by teammate; not implemented here
│   └── README.md                  # placeholder describing integration boundary
└── tests/
    ├── test_signaling.py
    ├── test_transport.py
    ├── test_protocol.py
    └── test_transfer.py
```

This structure is stable from Phase 1 onward — no throwaway prototype directories.
Each phase adds to it incrementally.

## 7. Key Architectural Decisions (Summary)

| Decision | Choice | Rationale |
|---|---|---|
| Room code | 6-char alphanumeric, ambiguous chars excluded | Short, human-shareable, sufficient keyspace for short TTL |
| Room lifecycle | Ephemeral: 15-min TTL, or early expiry on successful WebRTC connection | Minimizes attack window; no long-lived guessable codes |
| Room storage | In-memory, single process | No integration complexity needed at current scale |
| Peers per room | Exactly 2 (sender, receiver) | Explicitly out of scope: multi-peer |
| DataChannels | Two: `control` (reliable-ordered, small messages) and `data` (reliable-ordered, bulk chunks) | Prevents control traffic (ACKs, heartbeats) from queuing behind bulk data |
| Chunk size | 16 KB default, configurable | Practical DataChannel message size; tunable in Phase 14 |
| Flow control | Sliding window ACK | Needed for throughput at scale (100s of GB); bounded memory via window cap |
| Resume authority | Receiver-authoritative | Receiver independently verifies on-disk partial data via persisted chunk hashes |
| Integrity | Per-chunk SHA-256 + whole-file SHA-256 | Localizes corruption for resume; final hash guarantees end-to-end correctness |
| Encryption | WebRTC DTLS only, no app-layer crypto | Sufficient transport security; avoids redundant complexity |
| Persistence | SQLite, local per-peer | Durable across full process restarts, not just network blips |
| TURN | Provider selection deferred (legitimate TBD, Phase 15) | Everything else has to be decided now; TURN vendor choice genuinely is a late-stage deployment detail |
| Desktop boundary | Async Python API with event callbacks, not REST/IPC | Lower latency/complexity for same-machine integration; clean seam still preserved |
| Config | `.env` files | Simple, universal, no hardcoded addresses |
| Repo | Single repo, backend/ and desktop/ separated | Supports parallel work without throwaway restructuring |

## 8. Full Phase Roadmap (Summary)

| # | Phase | One-line objective |
|---|---|---|
| 1 | Foundation | Repo, config, module skeleton, minimal CLI stub |
| 2 | Signaling & Rendezvous | WebSocket signaling, room create/join, TTL |
| 3 | WebRTC Connectivity | `aiortc` RTCPeerConnection, SDP/ICE exchange via signaling |
| 4 | DataChannel | Establish control + data channels, verify bidirectional messaging |
| 5 | Basic File Transfer | Minimal real protocol subset: single-file, sequential chunks, hash verification |
| 6 | LAN Functional System | Validate on two physically separate LAN laptops — **presentation checkpoint** |
| 7 | Application-Level Protocol | Finalize full wire format, framing, chunk/ACK model (see protocol_spec.md) |
| 8 | Large-File Streaming & Flow Control | Sliding window, backpressure, bounded memory streaming from disk |
| 9 | Progress & Checkpointing | Receiver-confirmed progress, safe checkpoint positions |
| 10 | Persistent Transfer State | SQLite schema, consistency rules across restarts |
| 11 | Reconnection | ICE state + heartbeat detection, reconnect grace window, renegotiation |
| 12 | Resume | Receiver dictates resume offset; sender continues from there |
| 13 | Recovery & Integrity Hardening | Corruption detection, rollback-to-checkpoint, cleanup of partial/orphaned state |
| 14 | Performance Engineering | Tune chunk size, window size, I/O buffering; benchmark |
| 15 | Real Network Connectivity | Direct P2P vs TURN relay; TURN provider selection (TBD resolved here) |
| 16 | Security & Hardening | Input validation, path traversal prevention, resource limits |
| 17 | Desktop Integration | Finalize and document the async Transfer API boundary |
| 18 | Production Readiness | Packaging, deployment, observability, docs |

Phases 1–6 are detailed in `docs/milestone_1_lan.md`. Phases 7–18 are detailed in
`docs/milestone_2_core.md`. The protocol's internal design (framing, chunk format,
ACK/window, resume algorithm, persistence schema) is fully specified — no TBDs — in
`docs/protocol_spec.md`.

## 9. Testing Strategy (Summary)
Focused on high-value validation points only — no mandated exhaustive unit test
coverage:
- **Signaling:** room create/join, TTL expiry, SDP/ICE relay correctness
- **Transport:** DataChannel establishment (both channels) between two local peers
- **File Transfer:** real binary file sent and verified end-to-end (Phase 5/6)
- **Resume:** intentionally interrupted transfer reconnects and resumes correctly (Phase 12+)
- **Networking:** direct P2P success and TURN fallback both verified (Phase 15)
- **Performance:** throughput and memory-footprint benchmarks (Phase 14)

## 10. Security & Observability (Summary)
- **Security:** all remote (signaling and protocol) input validated; filenames
  sanitized; no path traversal; no arbitrary filesystem writes outside a
  designated transfer directory; malformed messages rejected, not trusted.
- **Observability:** structured logging (standard `logging`, JSON-capable) for
  signaling lifecycle, room state transitions, WebRTC/ICE state, DataChannel state,
  transfer progress, failures, and resume events. File contents are never logged.

## 11. Configuration Strategy (Summary)
All environment-specific values load from `.env` via `backend/config.py`:
signaling host/port, environment (dev/prod), STUN server URLs, TURN settings
(populated once Phase 15 resolves provider), chunk size, sliding window size,
SQLite path, log level/format. No hardcoded addresses anywhere in the codebase.

## 12. Document Map
- **This file** — architecture overview, boundaries, phase summary, decision log
- `docs/milestone_1_lan.md` — Phases 1–6, fully implementation-ready
- `docs/protocol_spec.md` — wire format, chunk/ACK model, resume algorithm, SQLite schema
- `docs/milestone_2_core.md` — Phases 7–18, fully implementation-ready
