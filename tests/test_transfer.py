"""Tests for transfer orchestration components (Phase 5+)."""

from backend.transfer import session, state_store, sender, receiver
from backend.api import transfer_api


def test_transfer_module_imports():
    """Verify transfer and API modules are importable."""
    assert session is not None
    assert state_store is not None
    assert sender is not None
    assert receiver is not None
    assert transfer_api is not None
