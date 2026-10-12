from __future__ import annotations

import unittest

from effect_generation_agent.risks import canonicalize_risks, merge_workflow_risks


class WorkflowRiskTests(unittest.TestCase):
    def test_step_3_owns_chain_fallback_risk(self) -> None:
        risks = merge_workflow_risks(
            ["案例覆盖不足", "若动作时序不稳定，可能需要升级为 reference_video"],
            ["image2 模型可信度较低", "动作时序依赖 Prompt，生成不稳定时需要升级为 reference_video"],
            [],
        )
        self.assertEqual(
            risks,
            ["案例覆盖不足", "若动作时序不稳定，可能需要升级为 reference_video", "image2 模型可信度较低"],
        )

    def test_exact_duplicates_are_removed_across_steps(self) -> None:
        self.assertEqual(
            merge_workflow_risks(["身份一致性待验证"], ["身份一致性待验证"], []),
            ["身份一致性待验证"],
        )

    def test_distinct_model_risks_are_preserved(self) -> None:
        self.assertEqual(
            merge_workflow_risks([], ["图像模型待确认", "视频模型待确认"], []),
            ["图像模型待确认", "视频模型待确认"],
        )

    def test_historical_flattened_risks_keep_one_chain_fallback(self) -> None:
        self.assertEqual(
            canonicalize_risks(
                [
                    "不稳定时需要升级为 reference_video",
                    "图像模型待确认",
                    "生成失败时改用参考视频驱动",
                    "视频模型待确认",
                ]
            ),
            ["不稳定时需要升级为 reference_video", "图像模型待确认", "视频模型待确认"],
        )


if __name__ == "__main__":
    unittest.main()
