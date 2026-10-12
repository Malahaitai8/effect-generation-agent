from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from effect_generation_agent.batch import BatchRunner
from effect_generation_agent.mock_executor import build_mock_executors
from effect_generation_agent.store import TaskStore
from effect_generation_agent.workflow import StepContext, StepResult, WorkflowEngine


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "task-result.schema.json"


class WaitingExecutor:
    def execute(self, context: StepContext) -> StepResult:
        return StepResult(status="needs_input", output=None)


class BatchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp.name) / "outputs", SCHEMA)
        self.runner = BatchRunner(self.store)
        self.manifest = [
            {"task_id": "batch-task-a", "video_uri": "a.mp4"},
            {"task_id": "batch-task-b", "video_uri": "b.mp4"},
        ]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_mock_batch_completes_and_persists_summary(self) -> None:
        self.runner.create("batch-001", self.manifest)
        result = self.runner.run(
            "batch-001",
            lambda: WorkflowEngine(self.store, build_mock_executors()),
            mode="mock",
            max_concurrency=2,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual({item["status"] for item in result["tasks"].values()}, {"completed"})
        self.assertEqual(self.runner.show("batch-001")["status"], "completed")

    def test_tasks_execute_concurrently(self) -> None:
        self.runner.create("batch-concurrent", self.manifest)
        barrier = threading.Barrier(2, timeout=2)

        class ConcurrentStepOne:
            def execute(self, context: StepContext) -> StepResult:
                barrier.wait()
                return build_mock_executors()[1].execute(context)

        def factory() -> WorkflowEngine:
            executors = build_mock_executors()
            executors[1] = ConcurrentStepOne()
            return WorkflowEngine(self.store, executors)

        result = self.runner.run(
            "batch-concurrent", factory, mode="mock", max_concurrency=2
        )
        self.assertEqual(result["status"], "completed")

    def test_needs_input_isolated_and_resumable(self) -> None:
        self.runner.create("batch-resume", self.manifest)
        waiting = self.runner.run(
            "batch-resume",
            lambda: WorkflowEngine(self.store, {1: WaitingExecutor()}),
            mode="manual",
            max_concurrency=2,
        )
        self.assertEqual(waiting["status"], "needs_input")
        completed = self.runner.run(
            "batch-resume",
            lambda: WorkflowEngine(self.store, build_mock_executors()),
            mode="mock",
            max_concurrency=2,
            resume=True,
        )
        self.assertEqual(completed["status"], "completed")

    def test_resume_starts_pending_current_step_after_reused_step_one(self) -> None:
        self.runner.create("batch-reused-step-one", self.manifest)
        step_one_output = build_mock_executors()[1].execute(
            StepContext(
                task_id="unused",
                step=1,
                inputs={},
                artifacts={"materials_dir": str(Path(self.temp.name) / "materials")},
            )
        ).output
        for item in self.manifest:
            task_id = item["task_id"]
            self.store.mark_step_running(task_id, 1)
            self.store.commit_step_result(
                task_id, 1, status="completed", output=step_one_output
            )

        result = self.runner.run(
            "batch-reused-step-one",
            lambda: WorkflowEngine(self.store, build_mock_executors()),
            mode="mock",
            max_concurrency=2,
            resume=True,
        )

        self.assertEqual(result["status"], "completed")
