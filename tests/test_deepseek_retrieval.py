from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.model_execution import (
    DeepSeekStructuredModelClient,
    ManualResultRequired,
    ModelExecutionBlocked,
    StructuredModelRequest,
)
from effect_generation_agent.retrieval import CaseRetriever
from effect_generation_agent.mock_executor import MockStepExecutor
from effect_generation_agent.resources import load_runtime_resources
from effect_generation_agent.step3 import Step3RetrievalSelectionExecutor
from effect_generation_agent.store import TaskStore
from effect_generation_agent.workflow import StepContext, StepResult, WorkflowEngine


ROOT = Path(__file__).resolve().parents[1]


class FixedEncoder:
    model_id = "fixed-test-encoder"

    def __init__(self) -> None:
        self.query_calls = 0

    def encode_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return [1.0, 0.0]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class RouteSelectionClient:
    def __init__(self, route: str) -> None:
        self.route = route

    def generate(self, request: StructuredModelRequest) -> dict:
        candidates = request.inputs["step_3a.case_snapshot"]["candidates"]
        return {
            "selected_chain": self.route,
            "control_requirements": {
                "must_preserve": [],
                "may_change": [],
                "temporal_reference_required": self.route == "reference_video",
                "required_image_states": 1,
                "evidence": [],
            },
            "selection_reason": "Integration test selection.",
            "alternative_chain": None,
            "case_snapshot_ref": "replaced-by-executor",
            "case_ids": [
                item["case_id"]
                for item in candidates
                if item["case"]["route_type"] == self.route
            ],
            "risks": [],
        }


class ManualWaitingClient:
    def __init__(self, request_path: Path) -> None:
        self.request_path = request_path

    def generate(self, request: StructuredModelRequest) -> dict:
        raise ManualResultRequired(self.request_path)


class FixedSnapshotRetriever:
    def retrieve(self, step_2_output: dict, snapshot_path: Path) -> dict:
        return {
            "candidates": [
                {
                    "case_id": "single-case",
                    "case": {"route_type": "single_image"},
                }
            ]
        }


class StopAtStep4:
    def execute(self, context: StepContext) -> StepResult:
        return StepResult(
            status="blocked",
            output=None,
            errors=[
                {
                    "code": "integration_stop",
                    "message": "Step 3 integration verified.",
                    "severity": "warning",
                    "step": 4,
                    "recoverable": True,
                    "details": {},
                }
            ],
        )


class DeepSeekClientTests(unittest.TestCase):
    def test_repairs_invalid_json_once_and_validates_output(self) -> None:
        responses = iter(
            [
                {"choices": [{"message": {"content": "not-json"}}]},
                {"choices": [{"message": {"content": '{"ok": true}'}}]},
            ]
        )
        calls: list[dict] = []

        def transport(url, headers, payload, timeout):
            calls.append(dict(payload))
            return next(responses)

        def validator(task_id: str, step: int, output: dict) -> None:
            if output != {"ok": True}:
                raise ValueError("wrong output")

        client = DeepSeekStructuredModelClient(
            api_key="test-key", transport=transport, output_validator=validator
        )
        result = client.generate(
            StructuredModelRequest("task-1", 2, "step_2", "prompt", {"input": 1})
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertIn("Validation error", calls[1]["messages"][-1]["content"])

    def test_invalid_repair_becomes_recoverable_provider_error(self) -> None:
        def transport(url, headers, payload, timeout):
            return {"choices": [{"message": {"content": "[]"}}]}

        client = DeepSeekStructuredModelClient(api_key="test-key", transport=transport)
        with self.assertRaises(ModelExecutionBlocked):
            client.generate(
                StructuredModelRequest("task-1", 2, "step_2", "prompt", {})
            )


class RetrievalTests(unittest.TestCase):
    def test_step3_manual_request_pauses_as_needs_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            request_path = temporary_root / "manual" / "step-3" / "request.json"
            executor = Step3RetrievalSelectionExecutor(
                FixedSnapshotRetriever(), ManualWaitingClient(request_path)
            )
            result = executor.execute(
                StepContext(
                    task_id="manual-step3",
                    step=3,
                    inputs={
                        "workflow.step_1.output": {},
                        "workflow.step_2.output": {},
                    },
                    artifacts={"materials_dir": str(temporary_root / "materials")},
                    resources=load_runtime_resources(ROOT, temporary_root),
                )
            )

            self.assertEqual(result.status, "needs_input")
            self.assertIsNone(result.output)
            self.assertEqual(result.errors[0]["code"], "manual_result_required")
            self.assertTrue(result.errors[0]["recoverable"])

    def test_creates_cross_route_top_six_snapshot_and_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            encoder = FixedEncoder()
            retriever = CaseRetriever(
                ROOT / "rag" / "data" / "cases.jsonl",
                ROOT / "rag" / "case.schema.json",
                encoder,
            )
            snapshot_path = Path(temporary_directory) / "case-snapshot.json"
            step_2 = {
                "primary_selling_point": {
                    "description": "subject performs a recognizable action",
                    "tags": ["action_performance"],
                },
                "secondary_selling_points": [],
            }
            first = retriever.retrieve(step_2, snapshot_path)
            second = retriever.retrieve(step_2, snapshot_path)

            self.assertEqual(encoder.query_calls, 1)
            self.assertEqual(first, second)
            self.assertEqual(len(first["candidates"]), 6)
            routes = {item["case"]["route_type"] for item in first["candidates"]}
            self.assertTrue(routes)
            self.assertTrue(
                routes.issubset(
                    {"single_image", "multi_image", "reference_video"}
                )
            )
            self.assertEqual(first["retrieval"]["embedding_weight"], 0.85)
            self.assertEqual(first["retrieval"]["tag_weight"], 0.15)
            self.assertEqual(len(first["retrieval"]["case_source_sha256"]), 64)
            self.assertTrue(all("case" in item for item in first["candidates"]))

    def test_step3_rejects_case_ids_outside_route_filtered_top_six(self) -> None:
        snapshot = {
            "candidates": [
                {"case_id": "a", "case": {"route_type": "single_image"}},
                {"case_id": "b", "case": {"route_type": "reference_video"}},
            ]
        }
        output = {"selected_chain": "single_image", "case_ids": ["b"]}
        with self.assertRaises(ModelExecutionBlocked):
            Step3RetrievalSelectionExecutor._validate_and_normalize_selection(
                output,
                snapshot,
                {
                    "replication_goal": {
                        "replace": [], "preserve": [], "adapt": [], "optional": []
                    },
                    "control_signals": {},
                },
            )

    def test_step3_accepts_multi_image_cases_from_route_filtered_top_six(self) -> None:
        snapshot = {
            "candidates": [
                {"case_id": "single", "case": {"route_type": "single_image"}},
                {"case_id": "multi-a", "case": {"route_type": "multi_image"}},
                {"case_id": "multi-b", "case": {"route_type": "multi_image"}},
            ]
        }
        output = {
            "selected_chain": "multi_image",
            "case_ids": ["multi-a", "multi-b"],
            "control_requirements": {"must_preserve": []},
        }
        Step3RetrievalSelectionExecutor._validate_and_normalize_selection(
            output,
            snapshot,
            {
                "replication_goal": {
                    "replace": [], "preserve": [], "adapt": [], "optional": []
                },
                "control_signals": {},
            },
        )
        self.assertEqual(output["case_ids"], ["multi-a", "multi-b"])

    def test_step3_accepts_preserve_and_control_signal_sources(self) -> None:
        output = {
            "selected_chain": "single_image",
            "case_ids": ["a"],
            "control_requirements": {
                "must_preserve": [
                    {
                        "requirement": "Preserve the sneeze reversal.",
                        "source_refs": [
                            "replication_goal.preserve.sneeze_reversal",
                            "control_signals.continuous_processes.0",
                        ],
                    }
                ],
                "may_change": [],
                "temporal_reference_required": False,
                "required_image_states": 1,
                "evidence": [],
            },
        }
        Step3RetrievalSelectionExecutor._validate_and_normalize_selection(
            output,
            {"candidates": [{"case_id": "a", "case": {"route_type": "single_image"}}]},
            {
                "replication_goal": {
                    "replace": [],
                    "preserve": [
                        {"id": "sneeze_reversal", "description": "Sneeze reversal."}
                    ],
                    "adapt": [],
                    "optional": [],
                },
                "control_signals": {"continuous_processes": ["Sneeze sequence."]},
            },
        )

    def test_step3_blocks_promotion_of_adapted_subject_attribute(self) -> None:
        output = {
            "selected_chain": "single_image",
            "case_ids": ["a"],
            "control_requirements": {
                "must_preserve": [
                    {
                        "requirement": "The runtime subject must be a baby.",
                        "source_refs": ["replication_goal.preserve.subject_age"],
                    }
                ],
                "may_change": [],
                "temporal_reference_required": False,
                "required_image_states": 1,
                "evidence": [],
            },
        }
        with self.assertRaisesRegex(ModelExecutionBlocked, "policy is adapt"):
            Step3RetrievalSelectionExecutor._validate_and_normalize_selection(
                output,
                {"candidates": [{"case_id": "a", "case": {"route_type": "single_image"}}]},
                {
                    "replication_goal": {
                        "replace": [],
                        "preserve": [],
                        "adapt": [
                            {
                                "id": "subject_age",
                                "description": "Age follows the runtime subject.",
                            }
                        ],
                        "optional": [],
                    },
                    "control_signals": {},
                },
            )

    def test_real_step3_executor_commits_snapshot_and_state_for_both_routes(self) -> None:
        for route in ("single_image", "reference_video"):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as temporary_directory:
                outputs = Path(temporary_directory) / "outputs"
                store = TaskStore(outputs, ROOT / "schemas" / "task-result.schema.json")
                task_id = f"step3-{route}"
                task = store.create_task(task_id, "unused.mp4")
                mock = MockStepExecutor()
                for step in (1, 2):
                    running = store.mark_step_running(task_id, step)
                    context = StepContext(
                        task_id=task_id,
                        step=step,
                        inputs={},
                        artifacts=WorkflowEngine._executor_artifacts(running),
                    )
                    result = mock.execute(context)
                    store.commit_step_result(
                        task_id, step, status="completed", output=result.output
                    )

                retriever = CaseRetriever(
                    ROOT / "rag" / "data" / "cases.jsonl",
                    ROOT / "rag" / "case.schema.json",
                    FixedEncoder(),
                )
                engine = WorkflowEngine(
                    store,
                    {
                        3: Step3RetrievalSelectionExecutor(
                            retriever, RouteSelectionClient(route)
                        ),
                        (4, route): StopAtStep4(),
                    },
                    resources=load_runtime_resources(ROOT, outputs),
                )
                state = engine.run(task_id)
                self.assertEqual(state["current_step"], 4)
                self.assertEqual(state["workflow"]["step_3"]["status"], "completed")
                self.assertEqual(state["workflow"]["step_3"]["main_retrieval_count"], 1)
                snapshot_path = Path(state["artifacts"]["case_snapshot_path"])
                self.assertTrue(snapshot_path.is_file())
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                selected_ids = state["workflow"]["step_3"]["output"]["case_ids"]
                expected_ids = [
                    item["case_id"]
                    for item in snapshot["candidates"]
                    if item["case"]["route_type"] == route
                ]
                self.assertEqual(selected_ids, expected_ids)


if __name__ == "__main__":
    unittest.main()
