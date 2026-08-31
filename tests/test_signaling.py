"""Tests for signaling components (Phase 2+)."""

from backend.signaling import server, rooms, messages


def test_signaling_module_imports():
    """Verify signaling modules are importable."""
    assert server is not None
    assert rooms is not None
    assert messages is not None
