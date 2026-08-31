# Milestone 1 — LAN Functional System (Phases 1–6)

## Purpose & Scope
This document is implementation-ready detail for Phases 1 through 6: the path from
an empty repository to a validated, real file transfer between two physically
separate laptops on the same LAN. This is the presentation checkpoint. Scope here
is deliberately conservative — no resume, no TURN, no desktop integration. The goal
is a flawless, reliable core, not maximum features.

Antigravity must implement **strictly phase-by-phase**, pausing after each phase
for human review and testing before proceeding to the next.

---

## Phase 1 — Foundation

**Objective:** Establish the repository skeleton, configuration system, and a
minimal CLI entry point, with nothing yet functional beyond "the project runs."

**Why this phase exists:** Every later phase needs a stable place to live. Getting
structure and config right first avoids reshuffling later.

**Prerequisites:** None — this is the starting point.

**Scope / Tasks:**
- Create the repository structure exactly as defined in `PROJECT.md` §6.
- Set up `venv` + `requirements.txt` (fastapi, uvicorn, aiortc, python-dotenv,
  pytest, and any minimal deps needed later — pin versions).
- Implement `backend/config.py`: loads `.env` (see `.env.example` below), exposes
  a typed `Settings` object (e.g., via `pydantic-settings` or a simple dataclass).
- Implement `backend/cli/peer.py` as a stub: parses `--role send|receive` and
  `--signaling-url` arguments, prints resolved config, and exits. No networking yet.
- Write `README.md` with setup instructions (`venv` creation, install, run stub CLI).
- Add `.gitignore` (standard Python + `.env`).
- Add `LICENSE` (MIT).

**`.env.example` keys to establish now (values filled in as later phases need them):**
```
ENVIRONMENT=development
SIGNALING_HOST=0.0.0.0
SIGNALING_PORT=8000
SIGNALING_URL=ws://localhost:8000/ws
STUN_URLS=stun:stun.l.google.com:19302
TURN_URL=
TURN_USERNAME=
TURN_CREDENTIAL=
CHUNK_SIZE_BYTES=16384
SLIDING_WINDOW_SIZE=32
SQLITE_PATH=./pied_piper.db
LOG_LEVEL=INFO
ROOM_TTL_SECONDS=900
```

**Expected Output:** A cloned repo where `pip install -r requirements.txt` succeeds,
`python -m backend.cli.peer --role send --signaling-url ws://localhost:8000/ws`
runs and prints resolved settings without error.

**Acceptance Criteria:**
- Repo structure matches `PROJECT.md`.
- Config loads correctly from `.env` with sensible defaults when values are absent.
- CLI stub runs on Windows, macOS, and Linux without OS-specific path issues
  (verify with `pathlib.Path` usage, not raw string concatenation).

**Deferred:** All networking, signaling, WebRTC, transfer logic.

---

## Phase 2 — Signaling and Rendezvous

**Objective:** A working FastAPI WebSocket signaling service supporting room
creation, joining by code, TTL expiry, and relaying opaque signaling payloads
between exactly two peers in a room.

**Why this phase exists:** Peers need a way to find each other and exchange
WebRTC negotiation data before any WebRTC connection can exist.

**Prerequisites:** Phase 1 complete.

**Scope / Tasks:**
- `backend/signaling/rooms.py`:
  - Room code generation: 6 characters, uppercase alphanumeric excluding
    ambiguous characters (`0`, `O`, `1`, `I`, `L`) — keyspace of 30 chars ≈ 30^6
    (~729M combinations).
  - In-memory `dict[str, Room]` room registry (single-process, per PROJECT.md).
  - On generation collision (existing active code), retry with a new code.
  - Room states: `WAITING_FOR_PEER`, `CONNECTED`, `EXPIRED`.
  - TTL: room is created with `ROOM_TTL_SECONDS` (default 900s / 15 min). A
    background asyncio task sweeps expired `WAITING_FOR_PEER` rooms.
  - Room transitions to `CONNECTED` (and TTL sweep no longer applies to it in
    the "waiting" sense) once both peers have joined and reported successful
    WebRTC connection establishment (signaled explicitly — see message schema
    below) — this is the "early expiration on success" behavior from PROJECT.md.
  - Hard cap: exactly 2 peers per room. A third join attempt is rejected.
- `backend/signaling/messages.py`: Define message schemas (as Pydantic models
  or typed dicts) for the signaling protocol:
  ```
  # Client -> Server
  {"type": "create_room"}
  {"type": "join_room", "room_code": "AB3XYZ"}
  {"type": "signal", "payload": {...}}   # opaque SDP/ICE relay
  {"type": "connected"}                   # peer reports successful WebRTC connection

  # Server -> Client
  {"type": "room_created", "room_code": "AB3XYZ"}
  {"type": "peer_joined"}
  {"type": "signal", "payload": {...}}   # relayed opaque payload
  {"type": "room_expired"}
  {"type": "error", "reason": "..."}
  ```
  The `signal` payload is opaque to the signaling layer — it never inspects SDP/ICE
  content, only relays it to the other peer in the room.
- `backend/signaling/server.py`: FastAPI app with a single `/ws` WebSocket endpoint.
  Each connected WebSocket is associated with a room via the message flow above.
  On disconnect, mark the peer as gone; if a room's peer disconnects before
  `CONNECTED`, expire the room immediately (no reason to keep a half-open room
  waiting out the full TTL).
- Extend `backend/cli/peer.py`: `--role send` creates a room and prints the code;
  `--role receive --room-code XXXXXX` joins. Confirm both sides see `peer_joined`.

**Expected Output:** Two terminal instances of the CLI (same machine, for this
phase) can create/join a room and see confirmation of the other's presence.

**Acceptance Criteria:**
- Room codes are always 6 chars from the defined charset.
- Joining a nonexistent or expired code returns a clear `error` message.
- A third join attempt to an already-full room is rejected.
- TTL expiry actually removes rooms from the registry (verify via test).
- Signaling payloads are relayed verbatim without the server needing to
  understand their content.

**Deferred:** Actual SDP/ICE content (that's Phase 3), WebRTC connection itself,
DataChannels, cross-machine LAN testing (that's Phase 6 validation, though nothing
stops early manual testing across machines here).

---

## Phase 3 — WebRTC Connectivity

**Objective:** Using `aiortc`, establish a real `RTCPeerConnection` between two
CLI peers, with SDP offer/answer and ICE candidates exchanged via the Phase 2
signaling service.

**Why this phase exists:** This is the actual peer-to-peer connection — signaling
only sets up the handshake; this phase makes the handshake succeed.

**Prerequisites:** Phase 2 complete and tested.

**Scope / Tasks:**
- `backend/transport/peer_connection.py`:
  - Wrap `aiortc.RTCPeerConnection`, configured with `STUN_URLS` from config
    (via `RTCConfiguration`/`RTCIceServer`).
  - Sender/offerer role: create offer, set local description, send via
    `signal` message; on receiving answer, set remote description.
  - Receiver/answerer role: on receiving offer, set remote description, create
    answer, set local description, send via `signal` message.
  - ICE candidate trickling: both sides forward `icecandidate` events through
    the `signal` message channel and apply incoming candidates via
    `addIceCandidate`.
  - Track and log `connectionState`/`iceConnectionState` transitions.
  - On reaching `connected` state, send the `{"type": "connected"}` signaling
    message (triggers early room expiry from Phase 2).
- Update CLI peer to drive this flow for both roles.

**Expected Output:** Two CLI peer processes (same machine first, then two
machines for informal testing) complete SDP/ICE negotiation and reach
`connectionState == "connected"`.

**Acceptance Criteria:**
- Connection succeeds consistently on same-machine and same-LAN runs.
- ICE candidates are correctly trickled (not just bundled in the initial SDP).
- Connection state transitions are logged clearly (for observability).
- Failure cases (e.g., peer never joins) time out gracefully rather than hanging.

**Deferred:** DataChannels (Phase 4), TURN (Phase 15), any file transfer logic.

---

## Phase 4 — DataChannel

**Objective:** Establish the two DataChannels — `control` and `data` — over the
Phase 3 `RTCPeerConnection`, and verify basic bidirectional messaging on each.

**Why this phase exists:** DataChannels are the actual transport surface the
transfer protocol will ride on. Validating them in isolation, before any file
logic, isolates transport bugs from protocol bugs.

**Prerequisites:** Phase 3 complete and tested.

**Scope / Tasks:**
- `backend/transport/data_channels.py`:
  - Offering peer creates two channels: `pc.createDataChannel("control", ordered=True)`
    and `pc.createDataChannel("data", ordered=True)`. Both reliable-ordered
    (default SCTP behavior — no need to disable reliability).
  - Answering peer receives both via the `datachannel` event and stores references.
  - Simple message framing distinction: `control` carries small JSON/text
    messages; `data` carries binary chunk payloads (framing detail finalized in
    `protocol_spec.md`, but for this phase, just prove raw bytes flow correctly).
  - Log `open`/`close`/`error` events for both channels.
- CLI peer: once both channels report `open`, send a test ping on `control` and
  a test binary blob on `data`; confirm receipt on the other side.

**Expected Output:** Both channels open successfully and pass test messages in
both directions.

**Acceptance Criteria:**
- Both channels reach `readyState == "open"` before any test message is sent.
- Control message round-trips correctly.
- Binary data message round-trips correctly and byte-for-byte matches what was sent.
- Channel closure (e.g., one peer exits) is detected and logged on the other side.

**Deferred:** Real file chunking, hashing, ACKs, progress tracking — this phase
proves the pipe works, not the protocol running through it.

---

## Phase 5 — Basic File Transfer (Protocol Foundation)

**Objective:** Implement the foundational, non-throwaway subset of the final
application-level protocol: single-file transfer, sequential chunking, basic
progress reporting, and whole-file + per-chunk integrity verification.

**Why this phase exists:** This is the first real file transfer. It must be a
strict subset of the eventual full protocol (see `protocol_spec.md`) — not a
disposable prototype — so later phases extend it rather than replace it.

**Prerequisites:** Phase 4 complete and tested.

**Scope / Tasks:**
- `backend/protocol/framing.py`: define the minimal message frame used on the
  `control` channel for this phase:
  ```
  {"type": "file_offer", "filename": "...", "size": N, "sha256": "...", "chunk_size": 16384, "total_chunks": N}
  {"type": "file_accept"}
  {"type": "chunk_ack", "chunk_index": N}
  {"type": "transfer_complete", "sha256": "..."}
  ```
  (Full wire format generalization for batch transfers, sliding window, resume
  happens in Phase 7 / `protocol_spec.md` — this is intentionally minimal.)
- `backend/protocol/chunking.py`: read file via `pathlib`/binary I/O in
  `CHUNK_SIZE_BYTES`-sized sequential chunks; compute per-chunk SHA-256 as each
  is read; compute running whole-file SHA-256 incrementally (don't re-read the
  whole file at the end).
- `backend/transfer/sender.py`: sends `file_offer` on `control`, waits for
  `file_accept`, then streams chunks sequentially on `data`, waiting for each
  `chunk_ack` before sending the next (stop-and-wait is acceptable here —
  sliding window arrives in Phase 8). Sends `transfer_complete` with final hash
  when done.
- `backend/transfer/receiver.py`: on `file_offer`, sends `file_accept`; writes
  incoming chunks sequentially to a temp file in a designated output directory
  (sanitize filename — no path traversal, even at this early stage); verifies
  each chunk's hash before sending its `chunk_ack`; on `transfer_complete`,
  verifies whole-file hash and renames temp file to final filename.
- CLI peer: `--role send --file path/to/file` and `--role receive --output-dir path/`
  drive this end-to-end.
- Basic progress: log/print percentage complete based on chunks ACKed.

**Expected Output:** A real file sent from one CLI peer process is received
intact and verified on the other, on the same machine.

**Acceptance Criteria:**
- Sent and received files are byte-identical (verify independently, not just
  via the protocol's own hash check, during testing).
- Per-chunk hash mismatches are detected (test by injecting corruption) and
  cause the transfer to fail cleanly, not silently succeed.
- Filenames are sanitized; attempting a path-traversal filename is rejected.
- Progress percentage updates are visible during transfer.

**Deferred:** Multi-file/batch, sliding window, resume, reconnection,
persistence across restarts, TURN, desktop integration.

---

## Phase 6 — LAN Functional System (Presentation Checkpoint)

**Objective:** Validate the complete Phase 1–5 stack running between two
physically separate laptops on the same LAN — the presentation checkpoint.

**Why this phase exists:** Everything so far has plausibly been tested on one
machine. This phase proves it actually works across real network boundaries,
which is where signaling-endpoint configuration and NAT/firewall issues
first surface.

**Prerequisites:** Phases 1–5 complete and individually tested.

**Scope / Tasks:**
- Document clearly (in README and/or this doc) that `localhost` refers to the
  current machine only — a client on Laptop B cannot reach a signaling server
  on Laptop A via `ws://localhost:8000`. It must use Laptop A's LAN IP, e.g.
  `ws://192.168.1.23:8000`.
- Run the signaling server (`uvicorn backend.signaling.server:app`) on one
  laptop, bound to `0.0.0.0` so it's reachable on the LAN.
- Run the CLI sender on Laptop A, CLI receiver on Laptop B, both pointed at
  Laptop A's LAN IP for signaling.
- Confirm room create/join, WebRTC connection (direct P2P — no TURN needed on
  same LAN), DataChannel establishment, and full file transfer with
  verification, all across the two machines.
- Test with at least one non-trivial file size (e.g., tens to low hundreds of
  MB) to get a first real sense of throughput, without doing formal
  benchmarking (that's Phase 14).
- Note and log any LAN-specific friction (firewall prompts, local network
  discovery issues) for awareness — not necessarily solved now.

**Expected Output:** A live, working demo: room code created on one laptop,
entered on the other, connection established, real file sent and verified,
all over an actual LAN — no code changes needed beyond configuring the
signaling URL.

**Acceptance Criteria:**
- Successful end-to-end transfer across two separate physical machines,
  repeated at least twice to confirm reliability (not a one-off success).
- Clear operator instructions exist (README) for how to run this demo again
  (which IP to use, which commands, in which order).
- No crashes, hangs, or silent failures during the demo scenario.

**Deferred:** Everything in Phases 7–18 — this checkpoint intentionally does not
include resume, TURN, cross-network (non-LAN) operation, or desktop
integration. Do not build a separate "just for the demo" architecture; this
is the same codebase that continues into Milestone 2.

---

## Cross-Phase Notes

**CLI reference peer:** From Phase 5 onward, `backend/cli/peer.py` is treated as
a full reference implementation of both sender and receiver roles — not a
throwaway debug tool. It remains the primary functional client through Phase 16,
until desktop integration (Phase 17) is complete.

**Parallel work:** While Antigravity works through Phases 1–6, the desktop
developer can independently begin UI/UX work, room-code entry screens, and file
picker design — none of this requires the backend to be finished, since the
eventual integration point (Phase 17's async API) is fixed in shape (if not
final detail) from the boundaries defined in `PROJECT.md` §5.

**Review cadence:** Antigravity pauses after each phase above for human review
before proceeding — do not implement multiple phases in a single pass.
