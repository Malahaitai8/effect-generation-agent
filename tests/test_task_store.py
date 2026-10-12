from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filelock import FileLock

from effect_generation_agent.errors import (
    TaskLockTimeoutError,
    TaskValidationError,
)
from effect_generation_agent.store import TaskStore


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "task-result.schema.json"


class TaskStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.outputs_root = Path(self.temporary_directory.name) / "outputs"
        self.store = TaskStore(self.outputs_root, SCHEMA_PATH, lock_timeout=0.05)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_task_builds_schema_valid_seven_step_state(self) -> None:
        task = self.store.create_task("task-create-001", "inputs/example.mp4")

        self.store.validator.validate(task)
        self.assertEqual(task["schema_version"], "0.9.0")
        self.assertEqual(task["status"], "initialized")
        self.assertEqual(task["current_step"], 1)
        self.assertEqual(set(task["workflow"]), {f"step_{step}" for step in range(1, 8)})
        self.assertTrue(
            (self.outputs_root / "task-create-001" / "task-result.json").exists()
        )

    def test_invalid_result_does_not_replace_last_valid_state(self) -> None:
        self.store.create_task("task-invalid-001", "inputs/example.mp4")
        self.store.mark_step_running("task-invalid-001", 1)
        previous = self.store.load_task("task-invalid-001")

        with self.assertRaises(TaskValidationError):
            self.store.commit_step_result(
                "task-invalid-001",
                1,
                status="completed",
                output={},
            )

        self.assertEqual(self.store.load_task("task-invalid-001"), previous)

    def test_atomic_replace_failure_preserves_previous_file(self) -> None:
        task = self.store.create_task("task-atomic-001", "inputs/example.mp4")
        state_path = self.outputs_root / "task-atomic-001" / "task-result.json"
        original_bytes = state_path.read_bytes()

        with patch("effect_generation_agent.store.os.replace", side_effect=OSError("mock")):
            with self.assertRaises(OSError):
                self.store.mark_step_running("task-atomic-001", 1)

        self.assertEqual(state_path.read_bytes(), original_bytes)
        self.assertEqual(json.loads(original_bytes), task)
        self.assertEqual(list(state_path.parent.glob("*.tmp")), [])

    def test_state_lock_timeout_is_reported(self) -> None:
        self.store.create_task("task-lock-001", "inputs/example.mp4")
        lock_path = self.outputs_root / "task-lock-001" / ".state.lock"

        with FileLock(str(lock_path)).acquire(timeout=0.05):
            with self.assertRaises(TaskLockTimeoutError):
                self.store.load_task("task-lock-001")


if __name__ == "__main__":
    unittest.main()
