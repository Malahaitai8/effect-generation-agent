"""Sequential seven-Step workflow orchestration."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol, TypeAlias

from .errors import InputReferenceError, InvalidTaskTransitionError, TaskValidationError
from .store import TaskStore


class CaseSnapshotReader(Protocol):
    def read(self, reference: str) -> Mapping[str, Any]:
        """Read one task-level case snapshot without changing task state."""


@dataclass(frozen=True)
class RuntimeResources:
    """Read-only dependencies supplied to executors, never persisted as task state."""

    prompt_paths: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    model_capabilities: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    case_snapshot_reader: CaseSnapshotReader | None = None
    adapters: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class StepContext:
    """Validated, read-only-by-convention input passed to one Step executor."""

    task_id: str
    step: int
    inputs: Mapping[str, Any]
    artifacts: Mapping[str, str | None]
    resources: RuntimeResources = field(default_factory=RuntimeResources)


@dataclass(frozen=True)
class StepResult:
    """A Step executor result awaiting validation and persistence."""

    status: str
    output: dict[str, Any] | None
    errors: list[dict[str, Any]] = field(default_factory=list)
    artifact_updates: dict[str, str | None] = field(default_factory=dict)


class StepExecutor(Protocol):
    def execute(self, context: StepContext) -> StepResult:
        """Execute one Step without writing task state directly."""


ExecutorKey: TypeAlias = int | tuple[int, str]


class WorkflowEngine:
    """Run the current Step until the task completes or needs attention."""

    def __init__(
        self,
        store: TaskStore,
        executors: Mapping[ExecutorKey, StepExecutor],
        *,
        resources: RuntimeResources | None = None,
    ) -> None:
        self.store = store
        self.executors = dict(executors)
        self.resources = resources or RuntimeResources()

    def run(self, task_id: str) -> dict[str, Any]:
        with self.store.execution_lock(task_id):
            state = self.store.load_task(task_id)
            if state["status"] == "running":
                step_state = state["workflow"][f"step_{state['current_step']}"]
                if step_state["status"] == "running":
                    self.store.prepare_resume(task_id)
            return self._run_locked(task_id)

    def resume(self, task_id: str) -> dict[str, Any]:
        with self.store.execution_lock(task_id):
            self.store.prepare_resume(task_id)
            return self._run_locked(task_id)

    def _run_locked(self, task_id: str) -> dict[str, Any]:
        while True:
            task = self.store.load_task(task_id)
            if task["status"] in {"completed", "needs_input", "blocked", "failed"}:
                return task

            step = task["current_step"]
            guard_result = self._guard_step(task, step)
            if guard_result is not None:
                self.store.mark_step_running(task_id, step)
                return self.store.commit_step_result(
                    task_id,
                    step,
                    status=guard_result.status,
                    output=guard_result.output,
                    errors=guard_result.errors,
                )

            executor = self._select_executor(task, step)
            if executor is None:
                self.store.mark_step_running(task_id, step)
                return self.store.commit_step_result(
                    task_id,
                    step,
                    status="failed",
                    output=None,
                    errors=[self._issue(step, "executor_missing", f"No executor for Step {step}")],
                )

            running_task = self.store.mark_step_running(task_id, step)
            try:
                inputs = self._resolve_inputs(running_task, step)
                context = StepContext(
                    task_id=task_id,
                    step=step,
                    inputs=inputs,
                    artifacts=self._executor_artifacts(running_task),
                    resources=self.resources,
                )
                result = executor.execute(context)
            except Exception as error:  # Executors are an isolation boundary.
                result = StepResult(
                    status="failed",
                    output=None,
                    errors=[
                        self._issue(
                            step,
                            "executor_error",
                            f"{type(error).__name__}: {error}",
                            details={"exception_type": type(error).__name__},
                        )
                    ],
                )

            try:
                task = self.store.commit_step_result(
                    task_id,
                    step,
                    status=result.status,
                    output=copy.deepcopy(result.output),
                    errors=copy.deepcopy(result.errors),
                    artifact_updates=copy.deepcopy(result.artifact_updates),
                )
            except (TaskValidationError, InvalidTaskTransitionError) as error:
                task = self.store.commit_step_result(
                    task_id,
                    step,
                    status="failed",
                    output=None,
                    errors=[
                        self._issue(
                            step,
                            "invalid_executor_result",
                            str(error),
                            details={"exception_type": type(error).__name__},
                        )
                    ],
                )
            if task["status"] != "running":
                return task

    def _select_executor(self, task: dict[str, Any], step: int) -> StepExecutor | None:
        if step in {4, 6}:
            selected_chain = task["workflow"]["step_3"]["output"]["selected_chain"]
            return self.executors.get((step, selected_chain))
        return self.executors.get(step)

    @classmethod
    def _guard_step(cls, task: dict[str, Any], step: int) -> StepResult | None:
        if step == 4:
            step_3 = task["workflow"]["step_3"]
            if step_3["status"] != "completed" or step_3["output"] is None:
                return StepResult(
                    status="failed",
                    output=None,
                    errors=[cls._issue(4, "chain_selection_missing", "Step 3 must complete before Step 4.")],
                )
            selected_chain = step_3["output"]["selected_chain"]
            if selected_chain == "unsupported":
                return StepResult(
                    status="blocked",
                    output=None,
                    errors=[
                        cls._issue(
                            4,
                            "chain_not_executable",
                            f"The current MVP does not execute the {selected_chain} chain.",
                            recoverable=True,
                            details={"selected_chain": selected_chain},
                        )
                    ],
                )

        if step == 6:
            step_5_output = task["workflow"]["step_5"]["output"]
            if not step_5_output or step_5_output["ready_for_prompting"] is not True:
                return StepResult(
                    status="blocked",
                    output=None,
                    errors=[
                        cls._issue(
                            6,
                            "materials_not_ready",
                            "Step 6 requires Step 5 ready_for_prompting to be true.",
                            recoverable=True,
                        )
                    ],
                )
        return None

    @staticmethod
    def _executor_artifacts(task: dict[str, Any]) -> dict[str, str | None]:
        """Expose production artifacts without giving executors the state-file path."""

        return {
            key: copy.deepcopy(value)
            for key, value in task["artifacts"].items()
            if key != "task_result_path"
        }

    @staticmethod
    def _resolve_inputs(task: dict[str, Any], step: int) -> dict[str, Any]:
        step_state = task["workflow"][f"step_{step}"]
        resolved: dict[str, Any] = {}
        for reference in step_state["input_refs"]:
            value: Any = task
            try:
                for part in reference.split("."):
                    value = value[part]
            except (KeyError, TypeError) as error:
                raise InputReferenceError(
                    f"Cannot resolve input reference for Step {step}: {reference}"
                ) from error
            resolved[reference] = copy.deepcopy(value)
        return resolved

    @staticmethod
    def _issue(
        step: int,
        code: str,
        message: str,
        *,
        recoverable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "severity": "error",
            "step": step,
            "recoverable": recoverable,
            "details": details or {},
        }
