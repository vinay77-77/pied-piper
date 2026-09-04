"""
Unit tests for Desktop Step 3 & 4:
TransferState models, TransferController, MainWindow navigation shell, and menu actions.
"""

import sys
import unittest
from pathlib import Path

# Ensure desktop package is importable
desktop_dir = Path(__file__).resolve().parent.parent / "desktop"
if str(desktop_dir) not in sys.path:
    sys.path.insert(0, str(desktop_dir))

from PySide6.QtWidgets import QApplication
from app.models.transfer_state import (
    FileInfo,
    TransferProgress,
    TransferSessionInfo,
    TransferState,
)
from app.controllers.transfer_controller import TransferController
from app.ui.main_window import MainWindow
from app.ui.style import apply_win95_theme


class TestDesktopStep3And4(unittest.TestCase):
    """Test suite for desktop transfer state, controller, and MainWindow navigation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_win95_theme(cls.app)

    def test_transfer_state_enum(self) -> None:
        """Verify that all documented lifecycle states exist."""
        expected_states = {
            "IDLE",
            "SELECTING_FILE",
            "FILE_SELECTED",
            "CREATING_SESSION",
            "WAITING_FOR_RECEIVER",
            "RECEIVER_CONNECTED",
            "AWAITING_ACCEPTANCE",
            "CONNECTING",
            "TRANSFERRING",
            "INTERRUPTED",
            "RESUMING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        }
        actual_states = {state.value for state in TransferState}
        self.assertEqual(expected_states, actual_states)

    def test_models_instantiation(self) -> None:
        """Verify dataclass instantiation and default values."""
        file_info = FileInfo(file_path="/dummy/path.txt", file_name="path.txt", file_size=1024)
        self.assertEqual(file_info.file_path, "/dummy/path.txt")
        self.assertEqual(file_info.file_name, "path.txt")
        self.assertEqual(file_info.file_size, 1024)
        self.assertIsNone(file_info.sha256)

        progress = TransferProgress(
            bytes_transferred=512,
            total_bytes=1024,
            speed_bps=100.0,
            percentage=50.0,
        )
        self.assertEqual(progress.bytes_transferred, 512)
        self.assertEqual(progress.percentage, 50.0)

        session = TransferSessionInfo(state=TransferState.IDLE)
        self.assertEqual(session.state, TransferState.IDLE)
        self.assertIsNone(session.role)

    def test_transfer_controller_initial_state(self) -> None:
        """Verify controller initial state is IDLE."""
        controller = TransferController()
        self.assertEqual(controller.state, TransferState.IDLE)
        self.assertIsNone(controller.file_info)
        self.assertIsNone(controller.progress)
        self.assertIsNone(controller.error_message)

    def test_transfer_controller_valid_transitions(self) -> None:
        """Verify controller allows legitimate transitions and emits signals."""
        controller = TransferController()
        emitted_states = []
        controller.state_changed.connect(emitted_states.append)

        # Transition IDLE -> SELECTING_FILE
        self.assertTrue(controller.set_state(TransferState.SELECTING_FILE))
        self.assertEqual(controller.state, TransferState.SELECTING_FILE)

        # Transition SELECTING_FILE -> FILE_SELECTED via select_file
        selected_files = []
        controller.file_selected.connect(selected_files.append)
        self.assertTrue(controller.select_file("/test/sample.bin", 2048))
        self.assertEqual(controller.state, TransferState.FILE_SELECTED)
        self.assertIsNotNone(controller.file_info)
        self.assertEqual(controller.file_info.file_name, "sample.bin")
        self.assertEqual(len(selected_files), 1)

        # Transition FILE_SELECTED -> CREATING_SESSION
        self.assertTrue(controller.set_state(TransferState.CREATING_SESSION))
        self.assertEqual(controller.state, TransferState.CREATING_SESSION)

        # Transition CREATING_SESSION -> WAITING_FOR_RECEIVER
        self.assertTrue(controller.set_state(TransferState.WAITING_FOR_RECEIVER))
        self.assertEqual(controller.state, TransferState.WAITING_FOR_RECEIVER)

        # Transition WAITING_FOR_RECEIVER -> RECEIVER_CONNECTED
        self.assertTrue(controller.set_state(TransferState.RECEIVER_CONNECTED))

        # Transition RECEIVER_CONNECTED -> TRANSFERRING
        self.assertTrue(controller.set_state(TransferState.TRANSFERRING))

        # Update progress
        progress_updates = []
        controller.progress_updated.connect(progress_updates.append)
        controller.update_progress(bytes_transferred=1024, total_bytes=2048, speed_bps=500.0)
        self.assertEqual(len(progress_updates), 1)
        self.assertEqual(progress_updates[0].percentage, 50.0)

        # Transition TRANSFERRING -> COMPLETED
        self.assertTrue(controller.set_state(TransferState.COMPLETED))

        # Transition COMPLETED -> IDLE
        self.assertTrue(controller.set_state(TransferState.IDLE))
        self.assertEqual(controller.state, TransferState.IDLE)

    def test_transfer_controller_invalid_transitions(self) -> None:
        """Verify invalid transitions are rejected and state is preserved."""
        controller = TransferController()
        self.assertEqual(controller.state, TransferState.IDLE)

        # IDLE cannot directly jump to TRANSFERRING or COMPLETED
        self.assertFalse(controller.set_state(TransferState.TRANSFERRING))
        self.assertEqual(controller.state, TransferState.IDLE)

        self.assertFalse(controller.set_state(TransferState.COMPLETED))
        self.assertEqual(controller.state, TransferState.IDLE)

    def test_transfer_controller_reset_and_error(self) -> None:
        """Verify reset and error handling."""
        controller = TransferController()
        controller.select_file("/test/data.zip", 4096)
        self.assertEqual(controller.state, TransferState.FILE_SELECTED)

        # Set error
        errors = []
        controller.error_occurred.connect(errors.append)
        controller.set_error("Connection timed out")
        self.assertEqual(controller.state, TransferState.FAILED)
        self.assertEqual(controller.error_message, "Connection timed out")
        self.assertEqual(errors, ["Connection timed out"])

        # Reset
        resets = []
        controller.session_reset.connect(lambda: resets.append(True))
        controller.reset()
        self.assertEqual(controller.state, TransferState.IDLE)
        self.assertIsNone(controller.file_info)
        self.assertIsNone(controller.error_message)
        self.assertEqual(len(resets), 1)

    def test_main_window_navigation_and_views(self) -> None:
        """Verify MainWindow view stack navigation and back actions."""
        controller = TransferController()
        window = MainWindow(controller=controller)

        # Initial view is Home
        self.assertIs(window.controller, controller)
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_HOME)
        self.assertEqual(window._status_label.text(), "Ready")

        # Navigate to Send View
        window.navigate_to_send()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_SEND)

        # Navigate Back to Home
        window.navigate_to_home()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_HOME)

        # Navigate to Receive View
        window.navigate_to_receive()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_RECEIVE)

        # Navigate Back to Home
        window.navigate_to_home()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_HOME)

        window.close()

    def test_menu_bar_structure_and_shortcuts(self) -> None:
        """Verify menu bar actions trigger correct navigation."""
        window = MainWindow()
        menu_bar = window.menuBar()

        # Verify menus exist
        menu_texts = [m.text() for m in menu_bar.actions()]
        self.assertIn("&File", menu_texts)
        self.assertIn("&Transfer", menu_texts)
        self.assertIn("&Help", menu_texts)

        # Test Transfer -> Send File
        window.navigate_to_send()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_SEND)

        # Test File -> Home
        window.navigate_to_home()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_HOME)

        # Test Transfer -> Receive File
        window.navigate_to_receive()
        self.assertEqual(window._stack.currentIndex(), MainWindow.VIEW_RECEIVE)

        window.close()


if __name__ == "__main__":
    unittest.main()
