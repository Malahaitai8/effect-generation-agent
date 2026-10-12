from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from effect_generation_agent.evaluation import Step12TrialEvaluator
from effect_generation_agent.executors import build_available_model_executors
from effect_generation_agent.model_execution import (
    ManualExchangeModelClient,
    ManualResultRequired,
    ModelExecutionBlocked,
    StructuredModelRequest,
    StructuredPromptExecutor,
    build_structured_prompt_executors,
)
from effect_generation_agent.resources import load_runtime_resources
from effect_generation_agent.video_preprocessing import Step1VideoUnderstandingExecutor
from effect_generation_agent.workflow import StepContext


ROOT = Path(__file__).resolve().parents[1]


class FakeModelClient:
    def __init__(self, output: dict | None = None, error: Exception | None = None) -> None:
        self.output = output or {}
        self.error = error
        self.requests: list[StructuredModelRequest] = []

    def generate(self, request: StructuredModelRequest):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.output


class FakeVideoPreprocessor:
    def __init__(self) -> None:
        self.calls = 0

    def preprocess(self, video_uri: str, output_dir: Path):
        self.calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        (frames_dir / "frame_0001.jpg").write_bytes(b"frame")
        manifest_path = output_dir / "frames.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "frames": [
                        {
                            "frame_id": "frame_0001",
                            "timestamp_seconds": 0,
                            "file_ref": "frames/frame_0001.jpg",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps({"source_video": str((ROOT / video_uri).resolve())}),
            encoding="utf-8",
        )
        overview_path = output_dir / "timeline-overview.jpg"
        overview_path.write_bytes(b"overview")
        return {
            "status": "completed",
            "reused": self.calls > 1,
            "metadata_ref": str(metadata_path),
            "frames_manifest_ref": str(manifest_path),
            "timeline_overview_ref": str(overview_path),
            "frames_dir": str(frames_dir),
            "frame_count": 1,
        }


def step_1_model_output() -> dict:
    return {
        "content_summary": "A complete mock video observation.",
        "visual_style": {},
        "narrative_structure": "single event",
        "timeline": [],
        "observations": {
            "subjects": [],
            "scene": {},
            "actions": [],
            "physical_interactions": [],
            "camera_and_composition": [],
            "visual_effects": [],
            "state_changes": [],
            "observed_text": [],
            "audio": {},
        },
        "key_frames": [],
        "screen_recording_artifacts": [],
        "uncertainties": [],
    }


class StructuredModelExecutionTests(unittest.TestCase):
    def test_manual_exchange_exports_and_consumes_only_matching_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            client = ManualExchangeModelClient(Path(temporary_directory), "0.2.0")
            request = StructuredModelRequest(
                task_id="task-manual-001",
                step=2,
                prompt_key="step_2",
                prompt="Return JSON.",
                inputs={"workflow.step_1.output": {"summary": "x"}},
            )

            with self.assertRaises(ManualResultRequired):
                client.generate(request)
            pending = client.pending_request("task-manual-001", 2)
            self.assertEqual(pending["output_target"], "workflow.step_2.output")
            self.assertEqual(pending["schema_version"], "0.2.0")

            client.submit("task-manual-001", 2, {"result": "ok"})
            self.assertEqual(client.generate(request), {"result": "ok"})

            changed = StructuredModelRequest(
                task_id=request.task_id,
                step=request.step,
                prompt_key=request.prompt_key,
                prompt="Changed Prompt.",
                inputs=request.inputs,
            )
            with self.assertRaises(ManualResultRequired):
                client.generate(changed)

    def test_step_4_manual_request_contains_capabilities_and_selected_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            outputs = temporary / "outputs"
            snapshot = outputs / "task-model-step4" / "case-snapshot.json"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                json.dumps(
                    {
                        "cases": [
                            {"case_id": "selected", "name": "keep"},
                            {"case_id": "other", "name": "drop"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            client = ManualExchangeModelClient(outputs, "0.2.0")
            executor = StructuredPromptExecutor("step_4.single_image", client)
            context = StepContext(
                task_id="task-model-step4",
                step=4,
                inputs=MappingProxyType(
                    {
                        "workflow.step_3.output": {"case_ids": ["selected"]},
                        "artifacts.case_snapshot_path": str(snapshot),
                    }
                ),
                artifacts=MappingProxyType({}),
                resources=load_runtime_resources(ROOT, outputs),
            )

            result = executor.execute(context)

            self.assertEqual(result.status, "needs_input")
            pending = client.pending_request("task-model-step4", 4)
            runtime = pending["inputs"]["_runtime"]
            self.assertTrue(runtime["model_capabilities"])
            self.assertEqual(
                [case["case_id"] for case in runtime["case_snapshot"]["cases"]],
                ["selected"],
            )

    def test_generic_executor_loads_prompt_and_passes_structured_inputs(self) -> None:
        client = FakeModelClient({"result": "ok"})
        executor = StructuredPromptExecutor("step_2", client)
        context = StepContext(
            task_id="task-model-001",
            step=2,
            inputs=MappingProxyType({"workflow.step_1.output": {"summary": "x"}}),
            artifacts=MappingProxyType({}),
            resources=load_runtime_resources(ROOT),
        )

        result = executor.execute(context)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, {"result": "ok"})
        self.assertIn("Step 2", client.requests[0].prompt)
        self.assertEqual(client.requests[0].inputs, context.inputs)

    def test_recoverable_model_problem_becomes_blocked(self) -> None:
        client = FakeModelClient(error=ModelExecutionBlocked("provider unavailable"))
        executor = StructuredPromptExecutor("step_2", client)
        context = StepContext(
            task_id="task-model-blocked",
            step=2,
            inputs=MappingProxyType({}),
            artifacts=MappingProxyType({}),
            resources=load_runtime_resources(ROOT),
        )

        result = executor.execute(context)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0]["code"], "model_execution_blocked")

    def test_step_1_preprocesses_then_sends_video_overview_and_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            materials_dir = Path(temporary_directory) / "task" / "materials"
            materials_dir.mkdir(parents=True)
            preprocessor = FakeVideoPreprocessor()
            client = FakeModelClient(step_1_model_output())
            executor = Step1VideoUnderstandingExecutor(preprocessor, client)
            context = StepContext(
                task_id="task-video-001",
                step=1,
                inputs=MappingProxyType(
                    {
                        "source": {"video_uri": "input.mov", "metadata": {}},
                        "workflow.step_1.output": None,
                    }
                ),
                artifacts=MappingProxyType({"materials_dir": str(materials_dir)}),
                resources=load_runtime_resources(ROOT),
            )

            result = executor.execute(context)

            self.assertEqual(result.status, "completed")
            self.assertEqual(preprocessor.calls, 1)
            self.assertEqual(len(client.requests[0].media_refs), 3)
            self.assertTrue(client.requests[0].media_refs[0].endswith("input.mov"))
            self.assertTrue(
                client.requests[0].media_refs[1].endswith("timeline-overview.jpg")
            )
            self.assertTrue(client.requests[0].media_refs[2].endswith("frame_0001.jpg"))
            self.assertIn("video_preprocessing", result.output)

    def test_only_step_1_executor_owns_video_preprocessing(self) -> None:
        executors = build_structured_prompt_executors(FakeModelClient())

        self.assertNotIn(1, executors)
        self.assertNotIn(5, executors)
        self.assertEqual(
            set(executors),
            {
                2,
                (4, "single_image"),
                (4, "reference_video"),
                (4, "multi_image"),
                (6, "single_image"),
                (6, "reference_video"),
                (6, "multi_image"),
            },
        )

    def test_available_real_factory_wires_step_1_2_4_and_6(self) -> None:
        executors = build_available_model_executors(ROOT, FakeModelClient())

        self.assertEqual(
            set(executors),
            {
                1,
                2,
                (4, "single_image"),
                (4, "reference_video"),
                (4, "multi_image"),
                (6, "single_image"),
                (6, "reference_video"),
                (6, "multi_image"),
            },
        )

    def test_human_baseline_is_read_only_after_step_1_and_2_complete(self) -> None:
        client = FakeModelClient({"overall_alignment": "aligned"})
        evaluator = Step12TrialEvaluator(
            client,
            ROOT / "evals" / "step1-step2-comparison.md",
        )
        task = {
            "task_id": "task-eval-001",
            "workflow": {
                "step_1": {"status": "completed", "output": {"facts": []}},
                "step_2": {"status": "completed", "output": {"selling_points": []}},
            },
        }
        baseline = (
            ROOT
            / "特效自动化链路skill初步验证"
            / "生日车窗特效生成链路试跑记录.md"
        )

        result = evaluator.compare(task, baseline)

        self.assertEqual(result["overall_alignment"], "aligned")
        self.assertIn("human_trial_baseline", client.requests[0].inputs)
        self.assertNotIn("human_trial_baseline", task["workflow"]["step_1"]["output"])

    def test_human_baseline_comparison_requires_both_steps_completed(self) -> None:
        evaluator = Step12TrialEvaluator(
            FakeModelClient(),
            ROOT / "evals" / "step1-step2-comparison.md",
        )
        task = {
            "task_id": "task-eval-pending",
            "workflow": {
                "step_1": {"status": "completed", "output": {}},
                "step_2": {"status": "pending", "output": None},
            },
        }

        with self.assertRaises(ValueError):
            evaluator.compare(task, ROOT / "README.md")


if __name__ == "__main__":
    unittest.main()
