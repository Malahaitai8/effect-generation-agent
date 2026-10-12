from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from effect_generation_agent.delivery import ProductionPlanExecutor
from effect_generation_agent.workflow import StepContext


class ProductionPlanTests(unittest.TestCase):
    def context(
        self,
        task_dir: Path,
        *,
        prompt: bool = True,
        material_exists: bool = True,
    ) -> StepContext:
        material_path = task_dir / "materials" / "reference_video.mp4"
        material_path.parent.mkdir(parents=True, exist_ok=True)
        if material_exists:
            material_path.write_bytes(b"ready")
        values = {
            1: {"content_summary": "A subject performs a recognizable motion."},
            2: {
                "primary_selling_point": {"description": "Replace the subject while preserving motion.", "tags": ["action_performance"]},
            },
            3: {"selected_chain": "reference_video", "selection_reason": "Motion timing is essential.", "case_ids": ["case_1"], "risks": []},
            4: {
                "nodes": [{
                    "id": "generate_video", "role": "Replace subject and preserve motion",
                    "model": "video-model", "model_selection_reason": "Observed in similar cases",
                    "inputs": ["reference_video", "user_image"],
                    "outputs": ["generated_video"], "dependencies": [], "parameters": {},
                    "prompt_routing": None,
                }],
                "runtime_inputs": [{
                    "id": "user_image", "media_type": "image", "purpose": "Runtime subject identity",
                    "required": True, "requirements": {"subject_clear": True},
                }],
                "base_materials": [{
                    "id": "reference_video", "purpose": "Fixed motion reference",
                    "required": True, "requirements": {},
                }],
                "appearance_strategy": {
                    "mode": "preserve_input",
                    "reason": "The test keeps the supplied appearance.",
                    "presentation_sensitive_elements": [],
                    "shared_elements": ["motion", "camera"],
                },
                "prompt_branching": {"required": False, "reason": "The test design is neutral.", "dimensions": []},
                "risks": [],
            },
            5: {
                "materials": [{
                    "id": "reference_video", "source": "source video", "operation": "direct",
                    "purpose": "Fixed motion reference", "status": "ready", "path": str(material_path),
                    "evidence": [],
                }],
                "ready_for_prompting": True,
            },
            6: {
                "node_prompts": ([{
                    "node_id": "generate_video", "model": "video-model",
                    "variants": [{
                        "variant_id": "default", "conditions": {}, "prompt": "animate",
                    }],
                }] if prompt else []),
                "prompt_audit": ([{"node_id": "generate_video", "case_refs": ["case_1"], "notes": []}] if prompt else []),
                "coverage_gaps": [],
                "semantic_validation": {
                    "status": "passed", "review_model": "test-reviewer",
                    "repair_attempted": False,
                    "checks": {
                        "task_alignment": True, "node_alignment": True,
                        "input_alignment": True, "case_copy_safe": True,
                        "branch_compliance": True,
                    },
                    "issues": [],
                },
            },
        }
        return StepContext(
            task_id="task-delivery",
            step=7,
            inputs=MappingProxyType(
                {
                    "source": {"video_uri": "hotspot.mov", "title": "Hotspot", "metadata": {}},
                    **{f"workflow.step_{step}.output": output for step, output in values.items()},
                }
            ),
            artifacts=MappingProxyType({"materials_dir": str(task_dir / "materials")}),
        )

    def test_generates_plan_after_deterministic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            task_dir = Path(temporary_directory) / "task"
            result = ProductionPlanExecutor().execute(self.context(task_dir))

            self.assertEqual(result.status, "completed")
            self.assertTrue((task_dir / "production-plan.md").is_file())
            self.assertEqual(
                result.artifact_updates["production_plan_path"],
                str(task_dir / "production-plan.md"),
            )
            plan = (task_dir / "production-plan.md").read_text(encoding="utf-8")
            self.assertIn("## 执行节点", plan)
            self.assertIn("**卖点标签**：动作表演", plan)
            self.assertNotIn("**卖点标签**：action_performance", plan)
            self.assertIn("**Prompt 变体：default**", plan)
            self.assertIn("animate", plan)
            self.assertIn("## 方案依据与审计附录", plan)
            self.assertNotIn("**Prompt 输入引用**", plan)
            self.assertNotIn("**案例依据**", plan)
            self.assertNotIn("## Step 1", plan)

    def test_missing_semantic_validation_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            del context.inputs["workflow.step_6.output"]["semantic_validation"]
            result = ProductionPlanExecutor().execute(context)
            self.assertEqual(result.status, "blocked")
            self.assertIn(
                "Step 6 semantic validation has not passed",
                result.errors[0]["details"]["problems"],
            )

    def test_multi_image_delivery_accepts_two_ordered_image_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            step_3 = context.inputs["workflow.step_3.output"]
            step_3.update({
                "selected_chain": "multi_image",
                "control_requirements": {
                    "required_image_states": 2,
                    "temporal_reference_required": False,
                },
            })
            step_4 = context.inputs["workflow.step_4.output"]
            step_4["nodes"][0].update({
                "role": "Transition between ordered visual states",
                "inputs": ["start_frame", "end_frame"],
                "parameters": {"input_mode": "first_last_frame"},
            })
            step_4["runtime_inputs"] = [
                {"id": frame_id, "media_type": "image", "purpose": frame_id,
                 "required": True, "requirements": {}}
                for frame_id in ("start_frame", "end_frame")
            ]
            step_4["base_materials"] = []
            context.inputs["workflow.step_5.output"]["materials"] = []

            result = ProductionPlanExecutor().execute(context)

            self.assertEqual(result.status, "completed")

    def test_multi_image_delivery_rejects_missing_order_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            context.inputs["workflow.step_3.output"].update({
                "selected_chain": "multi_image",
                "control_requirements": {
                    "required_image_states": 2,
                    "temporal_reference_required": False,
                },
            })
            result = ProductionPlanExecutor().execute(context)

            self.assertEqual(result.status, "blocked")
            self.assertIn(
                "input_mode first_last_frame",
                " ".join(result.errors[0]["details"]["problems"]),
            )

    def test_missing_prompt_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = ProductionPlanExecutor().execute(
                self.context(Path(temporary_directory) / "task", prompt=False)
            )

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.errors[0]["code"], "production_plan_incomplete")

    def test_missing_ready_material_file_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = ProductionPlanExecutor().execute(
                self.context(
                    Path(temporary_directory) / "task",
                    material_exists=False,
                )
            )

            self.assertEqual(result.status, "blocked")
            self.assertIn(
                "does not exist on disk",
                " ".join(result.errors[0]["details"]["problems"]),
            )

    def test_prompt_audit_case_outside_selection_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            context.inputs["workflow.step_6.output"]["prompt_audit"][0]["case_refs"].append(
                "unknown_case"
            )

            result = ProductionPlanExecutor().execute(context)

            self.assertEqual(result.status, "blocked")
            self.assertIn(
                "references cases outside Step 3",
                " ".join(result.errors[0]["details"]["problems"]),
            )

    def test_duplicate_runtime_input_id_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            runtime_inputs = context.inputs["workflow.step_4.output"]["runtime_inputs"]
            runtime_inputs.append(dict(runtime_inputs[0]))

            result = ProductionPlanExecutor().execute(context)

            self.assertEqual(result.status, "blocked")
            self.assertIn(
                "Duplicate runtime input IDs",
                " ".join(result.errors[0]["details"]["problems"]),
            )

    def test_generic_branch_routing_requires_exact_variant_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = self.context(Path(temporary_directory) / "task")
            context.inputs["workflow.step_4.output"]["prompt_branching"] = {
                "required": True,
                "reason": "A runtime-observed profile changes the generation strategy.",
                "dimensions": [{
                    "id": "profile_kind",
                    "purpose": "Choose a compatible presentation strategy.",
                    "values": ["compact", "extended"],
                    "affected_stages": ["video_generation"],
                }],
            }
            nodes = context.inputs["workflow.step_4.output"]["nodes"]
            nodes.insert(0, {
                "id": "detect_profile",
                "role": "Derive a runtime profile.",
                "model": None,
                "model_selection_reason": "Deterministic test classifier.",
                "inputs": ["user_image"],
                "outputs": ["profile_kind"],
                "dependencies": [],
                "parameters": {},
                "prompt_routing": None,
            })
            nodes[1]["dependencies"] = ["detect_profile"]
            nodes[1]["prompt_routing"] = {
                "dimensions": [{
                    "dimension_id": "profile_kind",
                    "source_ref": "profile_kind",
                    "values": ["compact", "extended"],
                }]
            }
            variants = context.inputs["workflow.step_6.output"]["node_prompts"][0]["variants"]
            variants[0].update({
                "variant_id": "compact",
                "conditions": {"profile_kind": "compact"},
            })

            blocked = ProductionPlanExecutor().execute(context)
            self.assertEqual(blocked.status, "blocked")
            self.assertIn(
                "do not cover exactly the reachable branches",
                " ".join(blocked.errors[0]["details"]["problems"]),
            )

            variants.append({
                **variants[0],
                "variant_id": "extended",
                "conditions": {"profile_kind": "extended"},
                "prompt": "animate with the extended strategy",
            })
            completed = ProductionPlanExecutor().execute(context)
            self.assertEqual(completed.status, "completed")
            plan = (Path(temporary_directory) / "task" / "production-plan.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("profile_kind=compact", plan)
            self.assertIn("profile_kind=extended", plan)


if __name__ == "__main__":
    unittest.main()
