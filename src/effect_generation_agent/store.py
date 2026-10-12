"""Cross-platform, schema-validated file storage for task state."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from filelock import FileLock, Timeout

from .errors import (
    InvalidTaskTransitionError,
    TaskAlreadyExistsError,
    TaskLockTimeoutError,
    TaskNotFoundError,
    TaskValidationError,
)
from .validation import TaskValidator


STEP_INPUT_REFS: dict[int, list[str]] = {
    1: ["source", "workflow.step_1.output"],
    2: ["workflow.step_1.output"],
    3: ["workflow.step_1.output", "workflow.step_2.output"],
    4: [
        "source",
        "workflow.step_1.output",
        "workflow.step_2.output",
        "workflow.step_3.output",
        "artifacts.case_snapshot_path",
    ],
    5: [
        "source",
        "workflow.step_1.output",
        "workflow.step_4.output",
        "artifacts.materials_dir",
    ],
    6: [
        "workflow.step_1.output",
        "workflow.step_2.output",
        "workflow.step_3.output",
        "workflow.step_4.output",
        "workflow.step_5.output",
        "artifacts.case_snapshot_path",
    ],
    7: [
        "source",
        "workflow.step_1.output",
        "workflow.step_2.output",
        "workflow.step_3.output",
        "workflow.step_4.output",
        "workflow.step_5.output",
        "workflow.step_6.output",
    ],
}

TERMINAL_STEP_STATUSES = {"completed", "needs_input", "blocked", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskStore:
    """Own all persisted mutations to ``task-result.json`` files."""

    def __init__(
        self,
        outputs_root: Path,
        schema_path: Path,
        *,
        lock_timeout: float = 5.0,
    ) -> None:
        self.outputs_root = outputs_root.resolve()
        self.validator = TaskValidator(schema_path)
        self.project_root = schema_path.resolve().parent.parent
        self.lock_timeout = lock_timeout
        task_pattern = self.validator.schema["properties"]["task_id"].get("pattern")
        self._task_id_pattern = re.compile(task_pattern) if task_pattern else None

    def create_task(
        self,
        task_id: str,
        video_uri: str,
        *,
        title: str | None = None,
        duration_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_task_id(task_id)
        if not video_uri:
            raise TaskValidationError("video_uri must not be empty")

        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "materials").mkdir(exist_ok=True)

        with self._state_lock(task_id):
            if self._task_path(task_id).exists():
                raise TaskAlreadyExistsError(f"Task already exists: {task_id}")
            timestamp = utc_now()
            task: dict[str, Any] = {
                "schema_version": self.validator.schema_version,
                "task_id": task_id,
                "created_at": timestamp,
                "updated_at": timestamp,
                "status": "initialized",
                "current_step": 1,
                "source": {
                    "video_uri": video_uri,
                    "title": title,
                    "duration_seconds": duration_seconds,
                    "metadata": metadata or {},
                },
                "workflow": {
                    f"step_{step}": self._new_step_state(step) for step in range(1, 8)
                },
                "artifacts": {
                    "task_result_path": self._display_path(self._task_path(task_id)),
                    "production_plan_path": None,
                    "case_snapshot_path": None,
                    "materials_dir": self._display_path(task_dir / "materials"),
                },
                "issues": [],
            }
            self._write_unlocked(task_id, task)
            return copy.deepcopy(task)

    def load_task(self, task_id: str) -> dict[str, Any]:
        self._validate_task_id(task_id)
        with self._state_lock(task_id):
            return copy.deepcopy(self._load_unlocked(task_id))

    def validate_step_output(
        self,
        task_id: str,
        step: int,
        output: dict[str, Any],
    ) -> None:
        """Validate a candidate Step output without changing persisted state."""

        self._validate_step(step)
        task = self.load_task(task_id)
        self._require_current_step(task, step)
        candidate = copy.deepcopy(task)
        candidate["workflow"][f"step_{step}"]["output"] = copy.deepcopy(output)
        self.validator.validate(candidate)

    @contextmanager
    def execution_lock(self, task_id: str) -> Iterator[None]:
        """Prevent two workflow engines from running one task concurrently."""

        self._validate_task_id(task_id)
        task_dir = self._task_dir(task_id)
        if not self._task_path(task_id).exists():
            raise TaskNotFoundError(f"Task not found: {task_id}")
        lock = FileLock(str(task_dir / ".run.lock"))
        try:
            with lock.acquire(timeout=self.lock_timeout):
                yield
        except Timeout as error:
            raise TaskLockTimeoutError(f"Timed out waiting for task run lock: {task_id}") from error

    def mark_step_running(self, task_id: str, step: int) -> dict[str, Any]:
        self._validate_step(step)
        with self._state_lock(task_id):
            task = self._load_unlocked(task_id)
            self._require_current_step(task, step)
            step_state = task["workflow"][f"step_{step}"]
            if step_state["status"] not in {"pending", "running"}:
                raise InvalidTaskTransitionError(
                    f"Step {step} cannot start from status {step_state['status']}"
                )
            if step > 1 and task["workflow"][f"step_{step - 1}"]["status"] != "completed":
                raise InvalidTaskTransitionError(f"Step {step - 1} must complete before Step {step}")

            step_state["status"] = "running"
            step_state["attempt"] += 1
            step_state["started_at"] = utc_now()
            step_state["completed_at"] = None
            step_state["errors"] = []
            task["status"] = "running"
            self._save_updated_unlocked(task_id, task)
            return copy.deepcopy(task)

    def commit_step_result(
        self,
        task_id: str,
        step: int,
        *,
        status: str,
        output: dict[str, Any] | None,
        errors: list[dict[str, Any]] | None = None,
        artifact_updates: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        self._validate_step(step)
        if status not in TERMINAL_STEP_STATUSES:
            raise InvalidTaskTransitionError(f"Unsupported Step result status: {status}")
        if status == "completed" and output is None:
            raise TaskValidationError(f"Step {step} must return output when completed")

        with self._state_lock(task_id):
            task = self._load_unlocked(task_id)
            self._require_current_step(task, step)
            step_state = task["workflow"][f"step_{step}"]
            if step_state["status"] != "running":
                raise InvalidTaskTransitionError(
                    f"Step {step} result cannot be committed from status {step_state['status']}"
                )

            step_state["status"] = status
            step_state["output"] = copy.deepcopy(output)
            step_state["errors"] = copy.deepcopy(errors or [])
            step_state["completed_at"] = utc_now() if status in {"completed", "failed"} else None
            if step == 3 and status == "completed":
                step_state["main_retrieval_count"] = 1

            if artifact_updates:
                unknown = set(artifact_updates) - set(task["artifacts"])
                if unknown:
                    raise TaskValidationError(
                        "Unknown artifact fields: " + ", ".join(sorted(unknown))
                    )
                task["artifacts"].update(copy.deepcopy(artifact_updates))

            if status == "completed":
                if step == 7:
                    task["status"] = "completed"
                else:
                    task["current_step"] = step + 1
                    task["status"] = "running"
            else:
                task["status"] = status

            task["issues"].extend(copy.deepcopy(errors or []))
            self._save_updated_unlocked(task_id, task)
            return copy.deepcopy(task)

    def prepare_resume(self, task_id: str) -> dict[str, Any]:
        """Reset a recoverable current Step so the engine can execute it again."""

        with self._state_lock(task_id):
            task = self._load_unlocked(task_id)
            if task["status"] not in {"needs_input", "blocked", "running"}:
                raise InvalidTaskTransitionError(
                    f"Task cannot resume from status {task['status']}"
                )
            step = task["current_step"]
            step_state = task["workflow"][f"step_{step}"]
            if step_state["status"] not in {"needs_input", "blocked", "running"}:
                raise InvalidTaskTransitionError(
                    f"Step {step} cannot resume from status {step_state['status']}"
                )

            if step_state["status"] == "running":
                issue = {
                    "code": "execution_interrupted",
                    "message": f"Step {step} was running when execution stopped; retrying it.",
                    "severity": "warning",
                    "step": step,
                    "recoverable": True,
                    "details": {},
                }
                task["issues"].append(issue)

            step_state["status"] = "pending"
            step_state["started_at"] = None
            step_state["completed_at"] = None
            step_state["errors"] = []
            task["status"] = "initialized"
            self._save_updated_unlocked(task_id, task)
            return copy.deepcopy(task)

    def _new_step_state(self, step: int) -> dict[str, Any]:
        state: dict[str, Any] = {
            "status": "pending",
            "attempt": 0,
            "started_at": None,
            "completed_at": None,
            "input_refs": STEP_INPUT_REFS[step],
            "output": None,
            "errors": [],
        }
        if step == 3:
            state["main_retrieval_count"] = 0
        if step == 6:
            state["supplemental_retrievals"] = 0
        return state

    def _save_updated_unlocked(self, task_id: str, task: dict[str, Any]) -> None:
        task["updated_at"] = utc_now()
        self._write_unlocked(task_id, task)

    def _load_unlocked(self, task_id: str) -> dict[str, Any]:
        path = self._task_path(task_id)
        if not path.exists():
            raise TaskNotFoundError(f"Task not found: {task_id}")
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskValidationError(f"Cannot read task state {path}: {error}") from error
        self.validator.validate(task)
        return task

    def _write_unlocked(self, task_id: str, task: dict[str, Any]) -> None:
        self.validator.validate(task)
        path = self._task_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(task, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    @contextmanager
    def _state_lock(self, task_id: str) -> Iterator[None]:
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(task_dir / ".state.lock"))
        try:
            with lock.acquire(timeout=self.lock_timeout):
                yield
        except Timeout as error:
            raise TaskLockTimeoutError(f"Timed out waiting for task state lock: {task_id}") from error

    def _task_dir(self, task_id: str) -> Path:
        return self.outputs_root / task_id

    def _task_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "task-result.json"

    @staticmethod
    def _require_current_step(task: dict[str, Any], step: int) -> None:
        if task["current_step"] != step:
            raise InvalidTaskTransitionError(
                f"Task current_step is {task['current_step']}, not {step}"
            )

    @staticmethod
    def _validate_step(step: int) -> None:
        if step not in range(1, 8):
            raise InvalidTaskTransitionError(f"Step must be between 1 and 7: {step}")

    def _validate_task_id(self, task_id: str) -> None:
        if not task_id or (self._task_id_pattern and not self._task_id_pattern.fullmatch(task_id)):
            raise TaskValidationError(f"Invalid task_id: {task_id!r}")

    def _display_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return resolved.as_posix()
