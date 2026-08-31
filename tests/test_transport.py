"""Tests for transport components (Phase 3+)."""

from backend.transport import peer_connection, data_channels


def test_transport_module_imports():
    """Verify transport modules are importable."""
    assert peer_connection is not None
    assert data_channels is not None
