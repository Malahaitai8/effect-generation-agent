"""Persistent, bounded-concurrency orchestration for independent tasks."""

from __future__ import annotations

import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable

from filelock import FileLock, Timeout

from .errors import AgentRuntimeError
from .store import TaskStore, utc_now
from .workflow import WorkflowEngine


EngineFactory = Callable[[], WorkflowEngine]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class BatchError(AgentRuntimeError):
    """A batch definition or persisted batch state is invalid."""


class BatchRunner:
    """Run multiple task state machines concurrently with failure isolation."""

    def __init__(self, store: TaskStore, *, lock_timeout: float = 5.0) -> None:
        self.store = store
        self.root = store.outputs_root / ".batches"
        self.lock_timeout = lock_timeout

    def create(self, batch_id: str, tasks: Iterable[dict[str, Any]]) -> dict[str, Any]:
        self._validate_id(batch_id)
        with self._lock(batch_id):
            if self._path(batch_id).exists():
                raise BatchError(f"Batch already exists: {batch_id}")
        definitions = list(tasks)
        if not definitions:
            raise BatchError("Batch manifest must contain at least one task")
        task_ids: list[str] = []
        for item in definitions:
            if not isinstance(item, dict) or not item.get("task_id") or not item.get("video_uri"):
                raise BatchError("Each batch task requires task_id and video_uri")
            task_id = str(item["task_id"])
            if task_id in task_ids:
                raise BatchError(f"Duplicate task_id in batch: {task_id}")
            self.store.create_task(
                task_id,
                str(item["video_uri"]),
                title=item.get("title"),
                duration_seconds=item.get("duration_seconds"),
                metadata=item.get("metadata"),
            )
            task_ids.append(task_id)
        timestamp = utc_now()
        state = {
            "batch_id": batch_id,
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": "initialized",
            "mode": None,
            "max_concurrency": None,
            "task_ids": task_ids,
            "tasks": {},
        }
        with self._lock(batch_id):
            self._write(batch_id, self._refresh(state))
        return self.show(batch_id)

    def show(self, batch_id: str) -> dict[str, Any]:
        with self._lock(batch_id):
            state = self._load(batch_id)
            state = self._refresh(state)
            self._write(batch_id, state)
            return state

    def run(
        self,
        batch_id: str,
        engine_factory: EngineFactory,
        *,
        mode: str,
        max_concurrency: int = 2,
        resume: bool = False,
    ) -> dict[str, Any]:
        if max_concurrency < 1:
            raise BatchError("max_concurrency must be at least 1")
        with self._lock(batch_id):
            state = self._refresh(self._load(batch_id))
            state["status"] = "running"
            state["mode"] = mode
            state["max_concurrency"] = max_concurrency
            state["updated_at"] = utc_now()
            self._write(batch_id, state)

        selected = []
        for task_id in state["task_ids"]:
            task_status = state["tasks"][task_id]["status"]
            if task_status == "completed":
                continue
            if resume or task_status in {"initialized", "running"}:
                selected.append(task_id)

        def execute(task_id: str) -> dict[str, Any]:
            task = self.store.load_task(task_id)
            engine = engine_factory()
            current_step = task["current_step"]
            current_step_status = task["workflow"][f"step_{current_step}"]["status"]
            if current_step_status in {"needs_input", "blocked", "running"}:
                return engine.resume(task_id)
            return engine.run(task_id)

        failures: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix="effect-task") as pool:
            futures = {pool.submit(execute, task_id): task_id for task_id in selected}
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    future.result()
                except Exception as error:  # Keep unrelated tasks progressing.
                    failures[task_id] = f"{type(error).__name__}: {error}"

        with self._lock(batch_id):
            state = self._refresh(self._load(batch_id), failures=failures)
            state["mode"] = mode
            state["max_concurrency"] = max_concurrency
            self._write(batch_id, state)
            return state

    def _refresh(
        self, state: dict[str, Any], *, failures: dict[str, str] | None = None
    ) -> dict[str, Any]:
        tasks: dict[str, Any] = {}
        statuses: list[str] = []
        for task_id in state["task_ids"]:
            try:
                task = self.store.load_task(task_id)
                summary = {
                    "status": task["status"],
                    "current_step": task["current_step"],
                    "updated_at": task["updated_at"],
                }
                statuses.append(task["status"])
            except Exception as error:
                summary = {"status": "failed", "current_step": None, "updated_at": None}
                summary["error"] = f"{type(error).__name__}: {error}"
                statuses.append("failed")
            if failures and task_id in failures:
                summary["scheduler_error"] = failures[task_id]
                if summary["status"] not in {"completed", "needs_input", "blocked", "failed"}:
                    summary["status"] = "failed"
            tasks[task_id] = summary
        state["tasks"] = tasks
        state["status"] = self._aggregate(statuses)
        state["updated_at"] = utc_now()
        return state

    @staticmethod
    def _aggregate(statuses: list[str]) -> str:
        unique = set(statuses)
        if unique == {"completed"}:
            return "completed"
        if unique <= {"initialized"}:
            return "initialized"
        if "running" in unique:
            return "running"
        if unique <= {"completed", "needs_input"} and "needs_input" in unique:
            return "needs_input"
        if unique <= {"completed", "blocked", "failed"} and unique & {"blocked", "failed"}:
            return "blocked"
        return "partial"

    def _load(self, batch_id: str) -> dict[str, Any]:
        self._validate_id(batch_id)
        path = self._path(batch_id)
        if not path.exists():
            raise BatchError(f"Batch not found: {batch_id}")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BatchError(f"Cannot read batch state: {error}") from error
        if state.get("batch_id") != batch_id or not isinstance(state.get("task_ids"), list):
            raise BatchError(f"Invalid batch state: {path}")
        return state

    def _write(self, batch_id: str, state: dict[str, Any]) -> None:
        path = self._path(batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                json.dump(state, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def _path(self, batch_id: str) -> Path:
        self._validate_id(batch_id)
        return self.root / batch_id / "batch-result.json"

    def _lock(self, batch_id: str):
        path = self.root / batch_id
        path.mkdir(parents=True, exist_ok=True)
        return FileLock(str(path / ".batch.lock"), timeout=self.lock_timeout)

    @staticmethod
    def _validate_id(batch_id: str) -> None:
        if not _SAFE_ID.fullmatch(batch_id):
            raise BatchError(f"Invalid batch_id: {batch_id!r}")
