# Desktop Frontend Integration Boundary

This directory is reserved for the desktop front-end application, owned independently by the human teammate.

## Integration Contract
The desktop frontend integrates with the backend starting in **Phase 17** via the async Transfer API defined at:
`backend/api/transfer_api.py`

### Key Architectural Guidelines
- **Zero Direct Protocol/Transport Knowledge**: The desktop layer consumes high-level async events (room code generation/entry, connection progress, transfer progress percentage, pause/resume, and transfer completion) and does not directly interact with WebRTC DataChannels, signaling sockets, or SQLite storage.
- **Async Event Callbacks**: The backend exposes an async Python API with event callbacks (rather than REST or inter-process communication) to minimize latency and architectural complexity while preserving clean separation.

For more details on the transfer engine architecture and phase roadmap, see [PROJECT.md](../PROJECT.md).
