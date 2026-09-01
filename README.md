# Pied Piper

Secure peer-to-peer file transfer — desktop client.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
python -m app.main
```

## Architecture

```
PySide6 UI
    ↓
TransferController
    ↓
    ├── TransferEngineInterface → MockTransferEngine (→ future aiortc)
    └── BackendClientInterface  → MockBackendClient  (→ future FastAPI/WS)
```

The UI communicates only with the `TransferController`. Mock services
simulate the backend and transfer engine for UI demonstration.

Replace `MockBackendClient` and `MockTransferEngine` in `app/main.py`
with real implementations to integrate the actual system.
