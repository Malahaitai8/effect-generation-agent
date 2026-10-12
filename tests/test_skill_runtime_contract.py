from __future__ import annotations

import unittest
from pathlib import Path

from effect_generation_agent.store import STEP_INPUT_REFS


ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = ROOT / "skills" / "effect-generation-workflow" / "prompts"
CURRENT_STEP_PROMPTS = (
    "vlm-observation.md",
    "selling-point.md",
    "case-retrieval.md",
    "chain-selection.md",
    "chain-single-image-design.md",
    "chain-reference-video-design.md",
    "material-preparation.md",
    "chain-single-image-prompt.md",
    "chain-reference-video-prompt.md",
)


class SkillRuntimeContractTests(unittest.TestCase):
    def test_business_prompts_do_not_access_the_task_state_file(self) -> None:
        for filename in CURRENT_STEP_PROMPTS:
            with self.subTest(filename=filename):
                content = (PROMPT_ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("task-result.json", content)

    def test_runtime_declares_complete_downstream_state_inputs(self) -> None:
        self.assertEqual(
            set(STEP_INPUT_REFS[4]),
            {
                "source",
                "workflow.step_1.output",
                "workflow.step_2.output",
                "workflow.step_3.output",
                "artifacts.case_snapshot_path",
            },
        )
        self.assertEqual(
            set(STEP_INPUT_REFS[5]),
            {
                "source",
                "workflow.step_1.output",
                "workflow.step_4.output",
                "artifacts.materials_dir",
            },
        )
        self.assertEqual(
            set(STEP_INPUT_REFS[6]),
            {
                "workflow.step_1.output",
                "workflow.step_2.output",
                "workflow.step_3.output",
                "workflow.step_4.output",
                "workflow.step_5.output",
                "artifacts.case_snapshot_path",
            },
        )

    def test_chain_selection_does_not_equate_continuous_action_with_video_reference(self) -> None:
        content = (PROMPT_ROOT / "chain-selection.md").read_text(encoding="utf-8")
        self.assertIn("精心设计首图 + 时序 Prompt", content)
        self.assertIn("有连续动作", content)
        self.assertIn("持水枪喷射", content)
        self.assertIn("输入更少、链路更简单", content)

    def test_step_5_and_6_use_the_050_product_contract(self) -> None:
        material_prompt = (PROMPT_ROOT / "material-preparation.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Agent 从热点视频", material_prompt)
        self.assertIn("unresolved_materials", material_prompt)
        self.assertNotIn("人工生成请求", material_prompt)
        for filename in ("chain-single-image-prompt.md", "chain-reference-video-prompt.md", "chain-multi-image-prompt.md"):
            content = (PROMPT_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("prompt_audit", content)
            self.assertNotIn("material_refs", content)
            self.assertNotIn('"constraints"', content)

    def test_reference_video_subject_strategy_preserves_step_boundaries(self) -> None:
        design = (PROMPT_ROOT / "chain-reference-video-design.md").read_text(
            encoding="utf-8"
        )
        prompt = (PROMPT_ROOT / "chain-reference-video-prompt.md").read_text(
            encoding="utf-8"
        )
        selection = (PROMPT_ROOT / "chain-selection.md").read_text(encoding="utf-8")
        self.assertIn("主体输入策略", design)
        self.assertIn("身份参考", design)
        self.assertIn("预先建立目标视觉状态", design)
        self.assertIn("默认直接使用运行时图片", design)
        self.assertIn("不得绕过 Step 4 自行增加、删除或合并生图节点", prompt)
        self.assertIn("两种结构都属于 `reference_video`", selection)

    def test_source_subject_attributes_are_not_implicit_replication_requirements(self) -> None:
        selling_point = (PROMPT_ROOT / "selling-point.md").read_text(encoding="utf-8")
        self.assertIn("源视频中观察到的主体属性", selling_point)
        self.assertIn("不自动成为复刻要求", selling_point)
        self.assertIn("年龄化、宠物化或采用特定造型", selling_point)

    def test_human_presentation_branch_is_node_scoped(self) -> None:
        selling_point = (PROMPT_ROOT / "selling-point.md").read_text(encoding="utf-8")
        self.assertIn("不预测生产方案", selling_point)
        self.assertIn("由 Step 4", selling_point)

        for filename in (
            "chain-single-image-design.md",
            "chain-reference-video-design.md",
            "chain-multi-image.md",
        ):
            design = (PROMPT_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("appearance_strategy", design)
            self.assertIn("presentation_sensitive_elements", design)
            self.assertIn("preserve_input", design)
            self.assertIn("uniform_redesign", design)
            self.assertIn("presentation_specific_redesign", design)
            self.assertIn("真正受影响", design)

        for filename in (
            "chain-single-image-prompt.md",
            "chain-reference-video-prompt.md",
            "chain-multi-image-prompt.md",
        ):
            prompt = (PROMPT_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("presentation_type", prompt)
            self.assertIn("中性表达", prompt)


if __name__ == "__main__":
    unittest.main()
