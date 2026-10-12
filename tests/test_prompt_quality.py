from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from effect_generation_agent.model_execution import ModelExecutionBlocked, StructuredModelRequest
from effect_generation_agent.prompt_quality import (
    Step4ValidatedDesignExecutor,
    Step6ValidatedPromptExecutor,
)
from effect_generation_agent.workflow import RuntimeResources, StepContext


class QueueClient:
    model = "test-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests: list[StructuredModelRequest] = []

    def generate(self, request):
        self.requests.append(request)
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class SnapshotReader:
    def __init__(self, prompt: str):
        self.prompt = prompt

    def read(self, reference: str):
        return {
            "candidates": [{
                "case_id": "history_case",
                "case": {
                    "case_id": "history_case",
                    "nodes": [{"prompts": [{"text": self.prompt}]}],
                },
            }]
        }


def step6_output(prompt: str, note: str = "Learned timing structure.") -> dict:
    return {
        "node_prompts": [{
            "node_id": "generate_video", "model": "video-model",
            "variants": [{"variant_id": "default", "conditions": {}, "prompt": prompt}],
        }],
        "prompt_audit": [{"node_id": "generate_video", "case_refs": ["history_case"], "notes": [note]}],
        "case_snapshot_ref": "snapshot.json",
        "coverage_gaps": [],
    }


def review(status: str, issue: str | None = None) -> dict:
    passed = status == "passed"
    return {
        "status": status,
        "checks": {
            "task_alignment": passed,
            "node_alignment": True,
            "input_alignment": True,
            "case_copy_safe": passed,
            "branch_compliance": True,
        },
        "issues": [] if passed else [issue or "Prompt is unrelated to the task."],
    }


class PromptQualityTests(unittest.TestCase):
    def context(self, root: Path, historical_prompt: str) -> StepContext:
        generation = root / "generation.md"
        semantic_review = root / "review.md"
        semantic_repair = root / "repair.md"
        for path in (generation, semantic_review, semantic_repair):
            path.write_text("Return JSON.", encoding="utf-8")
        return StepContext(
            task_id="prompt-quality-task",
            step=6,
            inputs=MappingProxyType({
                "workflow.step_2.output": {"primary_selling_point": {"description": "Eat noodles."}},
                "workflow.step_3.output": {"case_ids": ["history_case"]},
                "workflow.step_4.output": {"nodes": [{"id": "generate_video", "role": "Animate eating noodles."}]},
                "workflow.step_5.output": {"ready_for_prompting": True},
                "artifacts.case_snapshot_path": "snapshot.json",
            }),
            artifacts=MappingProxyType({"materials_dir": str(root / "materials")}),
            resources=RuntimeResources(
                prompt_paths=MappingProxyType({
                    "step_6.single_image": str(generation),
                    "step_6.semantic_review": str(semantic_review),
                    "step_6.semantic_repair": str(semantic_repair),
                }),
                case_snapshot_reader=SnapshotReader(historical_prompt),
            ),
        )

    def test_direct_case_copy_is_repaired_before_commit(self) -> None:
        historical = "hairdresser wraps a black cape and applies hair cream " * 20
        repaired = step6_output("The subject eats noodles, reacts, and reveals a noodle at the nose.")
        client = QueueClient([
            step6_output(historical, "Directly reuse the historical Prompt."),
            review("failed", "The Prompt copies a hairdressing case."),
            repaired,
            review("passed"),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            result = Step6ValidatedPromptExecutor(
                "step_6.single_image", client
            ).execute(self.context(Path(temporary), historical))
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.output["semantic_validation"]["repair_attempted"])
        self.assertIn("eats noodles", result.output["node_prompts"][0]["variants"][0]["prompt"])

    def test_semantically_unrelated_repair_blocks_step_6(self) -> None:
        client = QueueClient([
            step6_output("A chef paints a wall."),
            review("failed"),
            step6_output("A barber cuts hair."),
            review("failed"),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            result = Step6ValidatedPromptExecutor(
                "step_6.single_image", client
            ).execute(self.context(Path(temporary), "A dancer turns around."))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0]["code"], "prompt_semantic_validation_failed")

    def test_reviewer_unavailable_blocks_step_6(self) -> None:
        client = QueueClient([
            step6_output("The subject eats noodles."),
            ModelExecutionBlocked("review service unavailable"),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            result = Step6ValidatedPromptExecutor(
                "step_6.single_image", client
            ).execute(self.context(Path(temporary), "A dancer turns around."))
        self.assertEqual(result.status, "blocked")

    def test_task_specific_prompt_does_not_trigger_copy_guard(self) -> None:
        issues = Step6ValidatedPromptExecutor._copy_issues(
            step6_output("The subject eats noodles and then reacts with surprise."),
            {"_runtime": {"case_snapshot": SnapshotReader("A dancer turns around.").read("x")}},
        )
        self.assertEqual(issues, [])

    def test_negated_direct_reuse_audit_is_not_flagged(self) -> None:
        candidate = step6_output(
            "The subject completes the current task-specific action.",
            "仅借鉴控制方式，未直接复用历史案例 Prompt。",
        )
        issues = Step6ValidatedPromptExecutor._copy_issues(
            candidate,
            {"_runtime": {"case_snapshot": SnapshotReader("A different historical action.").read("x")}},
        )
        self.assertEqual(issues, [])

    def test_step6_prepends_identity_and_hotspot_reference_roles(self) -> None:
        candidate = {
            "node_prompts": [{
                "node_id": "generate_first_frame",
                "model": "图片 3.0 Omni",
                "variants": [{
                    "variant_id": "default",
                    "conditions": {},
                    "prompt": "生成目标首帧。",
                }],
            }],
            "prompt_audit": [],
            "case_snapshot_ref": "snapshot.json",
            "coverage_gaps": [],
        }
        runtime_inputs = {
            "workflow.step_4.output": {
                "runtime_inputs": [{
                    "id": "user_image", "media_type": "image",
                }],
                "base_materials": [{
                    "id": "hotspot_visual_reference",
                    "requirements": {"source": {"kind": "step1_frame", "frame_id": "frame_0001"}},
                }],
                "nodes": [{
                    "id": "generate_first_frame",
                    "inputs": ["user_image", "hotspot_visual_reference"],
                }],
            }
        }

        result = Step6ValidatedPromptExecutor._apply_reference_role_preamble(
            candidate, runtime_inputs
        )
        prompt = result["node_prompts"][0]["variants"][0]["prompt"]
        self.assertTrue(prompt.startswith("输入图职责："))
        self.assertIn("user_image 是目标主体身份的唯一来源", prompt)
        self.assertIn("hotspot_visual_reference 只提供热点场景", prompt)
        self.assertIn("不得混合身份或生成双主体", prompt)

    def test_step4_multi_reference_node_requires_configured_model_capability(self) -> None:
        candidate = {
            "runtime_inputs": [{"id": "user_image", "media_type": "image"}],
            "base_materials": [{
                "id": "hotspot_visual_reference",
                "requirements": {"source": {"kind": "step1_frame", "frame_id": "frame_0001"}},
            }],
            "nodes": [{
                "id": "generate_first_frame",
                "model": "可图 2.1 人像参考",
                "inputs": ["user_image", "hotspot_visual_reference"],
            }],
        }
        base_review = {
            "status": "passed",
            "checks": {
                "source_semantics": True,
                "mode_consistency": True,
                "branch_consistency": True,
                "visual_reference_consistency": True,
            },
            "facts": {},
            "expected_mode": "uniform_redesign",
            "issues": [],
        }
        capabilities = {"models": {
            "single": {
                "display_name": "可图 2.1 人像参考",
                "supports_multi_reference_images": False,
            },
            "multi": {
                "display_name": "图片 3.0 Omni",
                "supports_multi_reference_images": True,
            },
        }}

        rejected = Step4ValidatedDesignExecutor._apply_model_input_guard(
            base_review, candidate, capabilities
        )
        self.assertEqual(rejected["status"], "failed")
        self.assertFalse(rejected["checks"]["visual_reference_consistency"])

        candidate["nodes"][0]["model"] = "图片 3.0 Omni"
        accepted = Step4ValidatedDesignExecutor._apply_model_input_guard(
            base_review, candidate, capabilities
        )
        self.assertEqual(accepted["status"], "passed")

    def test_step4_appearance_mismatch_is_repaired_once(self) -> None:
        candidate = {
            "nodes": [],
            "runtime_inputs": [],
            "base_materials": [],
            "unresolved_materials": [],
            "appearance_strategy": {
                "mode": "preserve_input",
                "reason": "Misread adapt as preserve.",
                "presentation_sensitive_elements": [],
                "shared_elements": [],
            },
            "prompt_branching": {"required": False, "reason": "None", "dimensions": []},
            "risks": [],
        }
        repaired = {
            **candidate,
            "appearance_strategy": {
                "mode": "presentation_specific_redesign",
                "reason": "The human role has an authored themed appearance.",
                "presentation_sensitive_elements": ["服装"],
                "shared_elements": ["动作"],
            },
            "prompt_branching": {
                "required": True,
                "reason": "The authored human styling needs complete variants.",
                "dimensions": [{
                    "id": "presentation_type",
                    "purpose": "Route authored appearance",
                    "values": ["female", "male"],
                    "affected_stages": ["image_generation"],
                }],
            },
        }
        failed_review = {
            "status": "failed",
            "facts": {
                "explicit_preserve_required": False,
                "adult_human_presentation": True,
                "authored_subject_styling": True,
                "styling_optional": False,
                "hotspot_visual_anchor_required": False,
                "usable_step1_frame_available": True,
            },
            "checks": {
                "source_semantics": False,
                "mode_consistency": False,
                "branch_consistency": True,
                "visual_reference_consistency": True,
            },
            "issues": ["adapt was incorrectly treated as preserve"],
        }
        passed_review = {
            "status": "passed",
            "facts": {
                "explicit_preserve_required": False,
                "adult_human_presentation": True,
                "authored_subject_styling": True,
                "styling_optional": False,
                "hotspot_visual_anchor_required": False,
                "usable_step1_frame_available": True,
            },
            "checks": {
                "source_semantics": True,
                "mode_consistency": True,
                "branch_consistency": True,
                "visual_reference_consistency": True,
            },
            "issues": [],
        }
        client = QueueClient([candidate, failed_review, repaired])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for key, name in {
                "step_4.single_image": "design.md",
                "step_4.appearance_review": "review.md",
                "step_4.appearance_repair": "repair.md",
            }.items():
                path = root / name
                path.write_text("Return JSON.", encoding="utf-8")
                paths[key] = str(path)
            context = StepContext(
                task_id="step4-quality-task",
                step=4,
                inputs=MappingProxyType({
                    "workflow.step_1.output": {"visual_style": {"palette": "authored outfit"}},
                    "workflow.step_2.output": {"replication_goal": {"preserve": [], "adapt": []}},
                    "workflow.step_3.output": {"selected_chain": "single_image"},
                }),
                artifacts=MappingProxyType({"materials_dir": str(root / "materials")}),
                resources=RuntimeResources(prompt_paths=MappingProxyType(paths)),
            )
            result = Step4ValidatedDesignExecutor(
                "step_4.single_image", client
            ).execute(context)
        self.assertEqual(result.status, "completed")
        self.assertEqual(
            result.output["appearance_strategy"]["mode"],
            "presentation_specific_redesign",
        )
        self.assertEqual(len(client.requests), 3)

    def test_step4_requires_real_step1_frame_input_when_visual_anchor_is_needed(self) -> None:
        facts = {
            "explicit_preserve_required": True,
            "adult_human_presentation": True,
            "authored_subject_styling": False,
            "styling_optional": True,
            "hotspot_visual_anchor_required": True,
            "usable_step1_frame_available": True,
        }
        review_output = {
            "status": "passed",
            "facts": facts,
            "checks": {
                "source_semantics": True,
                "mode_consistency": True,
                "branch_consistency": True,
                "visual_reference_consistency": True,
            },
            "issues": [],
        }
        candidate = {
            "appearance_strategy": {
                "mode": "preserve_input",
                "presentation_sensitive_elements": [],
            },
            "prompt_branching": {"dimensions": []},
            "runtime_inputs": [{"id": "user_image", "media_type": "image"}],
            "base_materials": [],
            "nodes": [{"id": "generate_first_frame", "inputs": ["user_image"]}],
        }
        invalid = Step4ValidatedDesignExecutor._validate_review(review_output, candidate)
        self.assertEqual(invalid["status"], "failed")
        self.assertFalse(invalid["checks"]["visual_reference_consistency"])

        candidate["base_materials"] = [{
            "id": "hotspot_visual_reference",
            "requirements": {"source": {"kind": "step1_frame", "frame_id": "frame_1"}},
        }]
        candidate["nodes"][0]["inputs"].append("hotspot_visual_reference")
        valid = Step4ValidatedDesignExecutor._validate_review(review_output, candidate)
        self.assertEqual(valid["status"], "passed")


if __name__ == "__main__":
    unittest.main()
