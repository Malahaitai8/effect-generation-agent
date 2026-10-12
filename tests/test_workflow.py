from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.mock_executor import build_mock_executors
from effect_generation_agent.resources import load_runtime_resources
from effect_generation_agent.store import TaskStore
from effect_generation_agent.workflow import StepContext, StepResult, WorkflowEngine


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "task-result.schema.json"


class RaisingExecutor:
    def execute(self, context: StepContext) -> StepResult:
        raise RuntimeError("mock executor failure")


class InvalidOutputExecutor:
    def execute(self, context: StepContext) -> StepResult:
        return StepResult(status="completed", output={})


class CapturingExecutor:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.contexts: list[StepContext] = []

    def execute(self, context: StepContext) -> StepResult:
        self.contexts.append(context)
        return self.delegate.execute(context)


class DesignRevisionExecutor:
    def execute(self, context: StepContext) -> StepResult:
        return StepResult(
            status="blocked",
            output=None,
            errors=[
                {
                    "code": "design_revision_required",
                    "message": "The available material contradicts a Step 4 requirement.",
                    "severity": "warning",
                    "step": 5,
                    "recoverable": True,
                    "details": {"suggested_review_step": 4},
                }
            ],
        )


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        outputs_root = Path(self.temporary_directory.name) / "outputs"
        self.store = TaskStore(outputs_root, SCHEMA_PATH, lock_timeout=0.05)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_task(self, task_id: str) -> None:
        self.store.create_task(task_id, "inputs/example.mp4")

    def test_mock_workflow_completes_all_seven_steps(self) -> None:
        self.create_task("task-complete-001")
        engine = WorkflowEngine(self.store, build_mock_executors())

        task = engine.run("task-complete-001")

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["current_step"], 7)
        for step in range(1, 8):
            self.assertEqual(task["workflow"][f"step_{step}"]["status"], "completed")
            self.assertEqual(task["workflow"][f"step_{step}"]["attempt"], 1)
        self.assertEqual(task["workflow"]["step_3"]["main_retrieval_count"], 1)
        self.assertEqual(
            task["artifacts"]["case_snapshot_path"],
            (
                Path(task["artifacts"]["task_result_path"]).parent
                / "case-snapshot.json"
            ).as_posix(),
        )
        self.store.validator.validate(task)

    def test_needs_input_and_blocked_tasks_resume_current_step(self) -> None:
        for status in ("needs_input", "blocked"):
            with self.subTest(status=status):
                task_id = f"task-{status}-001"
                self.create_task(task_id)
                paused_engine = WorkflowEngine(
                    self.store,
                    build_mock_executors({2: status}),
                )
                paused = paused_engine.run(task_id)
                self.assertEqual(paused["status"], status)
                self.assertEqual(paused["current_step"], 2)

                resumed = WorkflowEngine(
                    self.store,
                    build_mock_executors(),
                ).resume(task_id)
                self.assertEqual(resumed["status"], "completed")
                self.assertEqual(resumed["workflow"]["step_2"]["attempt"], 2)

    def test_executor_exception_becomes_structured_failure(self) -> None:
        self.create_task("task-error-001")
        executors = build_mock_executors()
        executors[3] = RaisingExecutor()

        task = WorkflowEngine(self.store, executors).run("task-error-001")

        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["current_step"], 3)
        self.assertEqual(task["workflow"]["step_3"]["status"], "failed")
        self.assertEqual(task["workflow"]["step_3"]["errors"][0]["code"], "executor_error")
        self.store.validator.validate(task)

    def test_invalid_executor_output_becomes_structured_failure(self) -> None:
        self.create_task("task-invalid-output")
        executors = build_mock_executors()
        executors[2] = InvalidOutputExecutor()

        task = WorkflowEngine(self.store, executors).run("task-invalid-output")

        self.assertEqual(task["status"], "failed")
        self.assertEqual(
            task["workflow"]["step_2"]["errors"][0]["code"],
            "invalid_executor_result",
        )
        self.store.validator.validate(task)

    def test_interrupted_running_step_is_retried(self) -> None:
        self.create_task("task-interrupted-001")
        self.store.mark_step_running("task-interrupted-001", 1)

        task = WorkflowEngine(self.store, build_mock_executors()).run(
            "task-interrupted-001"
        )

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["workflow"]["step_1"]["attempt"], 2)
        self.assertIn("execution_interrupted", {issue["code"] for issue in task["issues"]})

    def test_step_context_contains_resolved_input_references(self) -> None:
        self.create_task("task-inputs-001")
        task = self.store.load_task("task-inputs-001")

        inputs = WorkflowEngine._resolve_inputs(task, 1)

        self.assertEqual(inputs["source"]["video_uri"], "inputs/example.mp4")
        self.assertIsNone(inputs["workflow.step_1.output"])

    def test_step_4_and_6_receive_complete_declared_inputs(self) -> None:
        self.create_task("task-context-001")
        executors = build_mock_executors()
        step_4 = CapturingExecutor(executors[(4, "single_image")])
        step_5 = CapturingExecutor(executors[5])
        step_6 = CapturingExecutor(executors[(6, "single_image")])
        executors[(4, "single_image")] = step_4
        executors[5] = step_5
        executors[(6, "single_image")] = step_6

        task = WorkflowEngine(self.store, executors).run("task-context-001")

        self.assertEqual(task["status"], "completed")
        self.assertEqual(
            set(step_4.contexts[0].inputs),
            {
                "source",
                "workflow.step_1.output",
                "workflow.step_2.output",
                "workflow.step_3.output",
                "artifacts.case_snapshot_path",
            },
        )
        self.assertEqual(
            set(step_5.contexts[0].inputs),
            {
                "source",
                "workflow.step_1.output",
                "workflow.step_4.output",
                "artifacts.materials_dir",
            },
        )
        self.assertEqual(
            set(step_6.contexts[0].inputs),
            {
                "workflow.step_1.output",
                "workflow.step_2.output",
                "workflow.step_3.output",
                "workflow.step_4.output",
                "workflow.step_5.output",
                "artifacts.case_snapshot_path",
            },
        )
        self.assertNotIn("task_result_path", step_4.contexts[0].artifacts)

    def test_reference_video_uses_chain_specific_step_4_and_6_executors(self) -> None:
        self.create_task("task-reference-001")

        task = WorkflowEngine(
            self.store,
            build_mock_executors(selected_chain="reference_video"),
        ).run("task-reference-001")

        self.assertEqual(task["status"], "completed")
        self.assertEqual(
            task["workflow"]["step_4"]["output"]["nodes"][0]["model"],
            "mock-reference-video-model",
        )
        self.assertEqual(
            task["workflow"]["step_6"]["output"]["node_prompts"][0]["model"],
            "mock-reference-video-model",
        )

    def test_multi_image_uses_chain_specific_step_4_and_6_executors(self) -> None:
        self.create_task("task-multi-image-001")

        task = WorkflowEngine(
            self.store,
            build_mock_executors(selected_chain="multi_image"),
        ).run("task-multi-image-001")

        self.assertEqual(task["status"], "completed")
        node = task["workflow"]["step_4"]["output"]["nodes"][0]
        self.assertEqual(node["model"], "mock-multi-image-video-model")
        self.assertEqual(node["inputs"], ["start_frame", "end_frame"])
        self.assertEqual(node["parameters"]["input_mode"], "first_last_frame")
        self.assertEqual(
            task["workflow"]["step_6"]["output"]["node_prompts"][0]["model"],
            "mock-multi-image-video-model",
        )

    def test_non_executable_chains_stop_before_step_4_executor(self) -> None:
        for selected_chain in ("unsupported",):
            with self.subTest(selected_chain=selected_chain):
                task_id = f"task-{selected_chain.replace('_', '-')}-001"
                self.create_task(task_id)
                task = WorkflowEngine(
                    self.store,
                    build_mock_executors(selected_chain=selected_chain),
                ).run(task_id)

                self.assertEqual(task["status"], "blocked")
                self.assertEqual(task["current_step"], 4)
                self.assertEqual(task["workflow"]["step_3"]["status"], "completed")
                self.assertEqual(
                    task["workflow"]["step_4"]["errors"][0]["code"],
                    "chain_not_executable",
                )
                self.assertIsNone(task["workflow"]["step_4"]["output"])

    def test_step_6_is_blocked_when_materials_are_not_ready(self) -> None:
        self.create_task("task-materials-not-ready")

        task = WorkflowEngine(
            self.store,
            build_mock_executors(ready_for_prompting=False),
        ).run("task-materials-not-ready")

        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["current_step"], 6)
        self.assertEqual(task["workflow"]["step_5"]["status"], "completed")
        self.assertEqual(
            task["workflow"]["step_6"]["errors"][0]["code"],
            "materials_not_ready",
        )

    def test_design_revision_blocks_step_5_without_clearing_completed_steps(self) -> None:
        self.create_task("task-design-revision")
        executors = build_mock_executors()
        executors[5] = DesignRevisionExecutor()

        task = WorkflowEngine(self.store, executors).run("task-design-revision")

        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["current_step"], 5)
        self.assertEqual(task["workflow"]["step_4"]["status"], "completed")
        self.assertEqual(
            task["workflow"]["step_5"]["errors"][0]["code"],
            "design_revision_required",
        )

    def test_runtime_resources_are_injected_without_becoming_task_state(self) -> None:
        self.create_task("task-resources-001")
        executors = build_mock_executors()
        step_1 = CapturingExecutor(executors[1])
        executors[1] = step_1
        resources = load_runtime_resources(ROOT)

        task = WorkflowEngine(
            self.store,
            executors,
            resources=resources,
        ).run("task-resources-001")

        self.assertEqual(task["status"], "completed")
        self.assertIn("step_1", step_1.contexts[0].resources.prompt_paths)
        self.assertTrue(step_1.contexts[0].resources.model_capabilities)
        self.assertNotIn("resources", task)


if __name__ == "__main__":
    unittest.main()
