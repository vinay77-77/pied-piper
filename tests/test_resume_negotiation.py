"""Tests for receiver-side resume detection and negotiation (Phase 10)."""

import asyncio
import hashlib
from pathlib import Path

import pytest

from backend.protocol.framing import (
    FileManifestItem,
    TransferOfferMessage,
    TransferAcceptMessage,
    ResumeOffsetMessage,
    parse_control_message,
)
from backend.transfer.receiver import FileReceiver
from backend.transfer.state_store import TransferStateStore
from backend.transport.peer_connection import PeerConnectionWrapper


async def create_connected_peer_pair() -> tuple[PeerConnectionWrapper, PeerConnectionWrapper]:
    """Helper to establish a direct connected WebRTC PeerConnection pair with open DataChannels."""
    pc1 = PeerConnectionWrapper(role="send")
    pc2 = PeerConnectionWrapper(role="receive")

    offer = await pc1.create_offer()
    answer = await pc2.handle_offer(offer)
    await pc1.handle_answer(answer)

    await asyncio.gather(
        pc1.wait_channels_open(timeout=5.0),
        pc2.wait_channels_open(timeout=5.0),
    )
    return pc1, pc2


@pytest.mark.asyncio
async def test_receiver_resume_no_previous_transfer(tmp_path: Path):
    """Test that a clean receiver responds with TransferAcceptMessage."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)

        # Receiver task
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))

        # Send TransferOfferMessage
        offer = TransferOfferMessage(
            transfer_id="new_transfer_123",
            files=[
                FileManifestItem(
                    file_id="file_abc",
                    filename="test.txt",
                    size=1024,
                    sha256="A" * 64,
                    chunk_size=256,
                    total_chunks=4,
                )
            ]
        )
        pc1.channels.send_control(offer.model_dump())

        # Read response
        resp_str = await pc1.channels.receive_control(timeout=2.0)
        resp_msg = parse_control_message(resp_str)

        assert isinstance(resp_msg, TransferAcceptMessage)
        assert resp_msg.transfer_id == "new_transfer_123"

        # Cancel receiver since we won't send FileStartMessage
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_receiver_resume_valid_partial(tmp_path: Path):
    """Test that a valid partial transfer triggers ResumeOffsetMessage."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    
    # Create the part file
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        
        # Setup prior transfer state
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc",
            transfer_id="old_transfer",
            filename="test.txt",
            file_path=str(receiver_dir / "test.txt"),
            size_bytes=1024,
            total_chunks=4,
            chunk_size_bytes=256,
            sha256="A" * 64,
            highest_verified_chunk=1,  # 2 chunks verified (0, 1)
            status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)

        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))

        # Send new offer for same file
        offer = TransferOfferMessage(
            transfer_id="new_transfer_123",
            files=[
                FileManifestItem(
                    file_id="file_abc",
                    filename="test.txt",
                    size=1024,
                    sha256="A" * 64,
                    chunk_size=256,
                    total_chunks=4,
                )
            ]
        )
        pc1.channels.send_control(offer.model_dump())

        # Read response
        try:
            resp_str = await pc1.channels.receive_control(timeout=2.0)
        except Exception:
            if recv_task.done() and recv_task.exception():
                raise recv_task.exception()
            raise
        resp_msg = parse_control_message(resp_str)

        # Should respond with ResumeOffsetMessage from chunk 2
        assert isinstance(resp_msg, ResumeOffsetMessage)
        assert resp_msg.transfer_id == "new_transfer_123"
        assert resp_msg.file_id == "file_abc"
        assert resp_msg.resume_from_chunk == 2

        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_receiver_resume_completed_transfer(tmp_path: Path):
    """Test that a completed transfer does NOT trigger resume."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        
        await store.record_transfer("old_transfer", role="receiver", status="completed")
        await store.record_file(
            file_id="file_abc",
            transfer_id="old_transfer",
            filename="test.txt",
            file_path=str(receiver_dir / "test.txt"),
            size_bytes=1024,
            total_chunks=4,
            chunk_size_bytes=256,
            sha256="A" * 64,
            highest_verified_chunk=3,
            status="completed",  # Completed status
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))

        offer = TransferOfferMessage(
            transfer_id="new_transfer_123",
            files=[
                FileManifestItem(
                    file_id="file_abc",
                    filename="test.txt",
                    size=1024,
                    sha256="A" * 64,
                    chunk_size=256,
                    total_chunks=4,
                )
            ]
        )
        pc1.channels.send_control(offer.model_dump())

        resp_str = await pc1.channels.receive_control(timeout=2.0)
        resp_msg = parse_control_message(resp_str)

        assert isinstance(resp_msg, TransferAcceptMessage)

        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()


@pytest.mark.asyncio
async def test_receiver_resume_missing_part_file(tmp_path: Path):
    """Test that missing .part file prevents resume even if state exists."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc",
            transfer_id="old_transfer",
            filename="test.txt",
            file_path=str(receiver_dir / "test.txt"),
            size_bytes=1024,
            total_chunks=4,
            chunk_size_bytes=256,
            sha256="A" * 64,
            highest_verified_chunk=1,
            status="in_progress",
        )
        
        # Note: .part file is intentionally not created!
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))

        offer = TransferOfferMessage(
            transfer_id="new_transfer_123",
            files=[
                FileManifestItem(
                    file_id="file_abc",
                    filename="test.txt",
                    size=1024,
                    sha256="A" * 64,
                    chunk_size=256,
                    total_chunks=4,
                )
            ]
        )
        pc1.channels.send_control(offer.model_dump())

        resp_str = await pc1.channels.receive_control(timeout=2.0)
        resp_msg = parse_control_message(resp_str)

        assert isinstance(resp_msg, TransferAcceptMessage)

        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()

@pytest.mark.asyncio
async def test_receiver_resume_no_confirmed_chunks(tmp_path: Path):
    """Test that a state with -1 verified chunks falls back safely to TransferAcceptMessage."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc", transfer_id="old_transfer", filename="test.txt",
            file_path=str(receiver_dir / "test.txt"), size_bytes=1024,
            total_chunks=4, chunk_size_bytes=256, sha256="A" * 64,
            highest_verified_chunk=-1, status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))

        offer = TransferOfferMessage(
            transfer_id="new_transfer",
            files=[FileManifestItem(file_id="file_abc", filename="test.txt", size=1024, sha256="A" * 64, chunk_size=256, total_chunks=4)]
        )
        pc1.channels.send_control(offer.model_dump())
        resp_msg = parse_control_message(await pc1.channels.receive_control(timeout=2.0))
        assert isinstance(resp_msg, TransferAcceptMessage)
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()

@pytest.mark.asyncio
async def test_receiver_resume_out_of_range_checkpoint(tmp_path: Path):
    """Test that an out-of-range checkpoint (>= total_chunks) is rejected and falls back."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc", transfer_id="old_transfer", filename="test.txt",
            file_path=str(receiver_dir / "test.txt"), size_bytes=1024,
            total_chunks=4, chunk_size_bytes=256, sha256="A" * 64,
            highest_verified_chunk=4, status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))
        offer = TransferOfferMessage(
            transfer_id="new_transfer",
            files=[FileManifestItem(file_id="file_abc", filename="test.txt", size=1024, sha256="A" * 64, chunk_size=256, total_chunks=4)]
        )
        pc1.channels.send_control(offer.model_dump())
        resp_msg = parse_control_message(await pc1.channels.receive_control(timeout=2.0))
        assert isinstance(resp_msg, TransferAcceptMessage)
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()

@pytest.mark.asyncio
async def test_receiver_resume_size_mismatch(tmp_path: Path):
    """Test that a file size mismatch prevents resume."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc", transfer_id="old_transfer", filename="test.txt",
            file_path=str(receiver_dir / "test.txt"), size_bytes=2048, # Mismatch
            total_chunks=4, chunk_size_bytes=256, sha256="A" * 64,
            highest_verified_chunk=1, status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))
        offer = TransferOfferMessage(
            transfer_id="new_transfer",
            files=[FileManifestItem(file_id="file_abc", filename="test.txt", size=1024, sha256="A" * 64, chunk_size=256, total_chunks=4)]
        )
        pc1.channels.send_control(offer.model_dump())
        resp_msg = parse_control_message(await pc1.channels.receive_control(timeout=2.0))
        assert isinstance(resp_msg, TransferAcceptMessage)
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()

@pytest.mark.asyncio
async def test_receiver_resume_sha256_mismatch(tmp_path: Path):
    """Test that a SHA-256 mismatch prevents resume."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc", transfer_id="old_transfer", filename="test.txt",
            file_path=str(receiver_dir / "test.txt"), size_bytes=1024,
            total_chunks=4, chunk_size_bytes=256, sha256="B" * 64, # Mismatch
            highest_verified_chunk=1, status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))
        offer = TransferOfferMessage(
            transfer_id="new_transfer",
            files=[FileManifestItem(file_id="file_abc", filename="test.txt", size=1024, sha256="A" * 64, chunk_size=256, total_chunks=4)]
        )
        pc1.channels.send_control(offer.model_dump())
        resp_msg = parse_control_message(await pc1.channels.receive_control(timeout=2.0))
        assert isinstance(resp_msg, TransferAcceptMessage)
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()

@pytest.mark.asyncio
async def test_receiver_resume_final_chunk(tmp_path: Path):
    """Test that a checkpoint at the final chunk sends resume for total_chunks index safely."""
    pc1, pc2 = await create_connected_peer_pair()
    receiver_dir = tmp_path / "receiver"
    receiver_dir.mkdir()
    part_file = receiver_dir / ".test.txt.part"
    part_file.write_bytes(b"data")
    
    try:
        store = TransferStateStore(tmp_path / "state.db")
        await store.initialize()
        await store.record_transfer("old_transfer", role="receiver", status="in_progress")
        await store.record_file(
            file_id="file_abc", transfer_id="old_transfer", filename="test.txt",
            file_path=str(receiver_dir / "test.txt"), size_bytes=1024,
            total_chunks=4, chunk_size_bytes=256, sha256="A" * 64,
            highest_verified_chunk=3, # Last chunk index (total_chunks - 1)
            status="in_progress",
        )
        
        receiver = FileReceiver(channels=pc2.channels, output_dir=receiver_dir, state_store=store)
        recv_task = asyncio.create_task(receiver.receive(timeout=1.0))
        offer = TransferOfferMessage(
            transfer_id="new_transfer",
            files=[FileManifestItem(file_id="file_abc", filename="test.txt", size=1024, sha256="A" * 64, chunk_size=256, total_chunks=4)]
        )
        pc1.channels.send_control(offer.model_dump())
        try:
            resp_str = await pc1.channels.receive_control(timeout=2.0)
        except Exception:
            if recv_task.done() and recv_task.exception():
                raise recv_task.exception()
            raise
        resp_msg = parse_control_message(resp_str)
        assert isinstance(resp_msg, ResumeOffsetMessage)
        assert resp_msg.resume_from_chunk == 4
        recv_task.cancel()
    finally:
        await pc1.close()
        await pc2.close()
