"""Tests for protocol components (Phase 5+)."""

from backend.protocol import framing, chunking, window


def test_protocol_module_imports():
    """Verify protocol modules are importable."""
    assert framing is not None
    assert chunking is not None
    assert window is not None
