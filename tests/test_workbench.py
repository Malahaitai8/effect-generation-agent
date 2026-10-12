from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from effect_generation_agent.workbench import (
    RevisionConflict,
    WorkbenchError,
    WorkbenchStore,
    validate_plan,
)


def completed_task(task_id: str) -> dict:
    return {
        "task_id": task_id, "status": "completed", "current_step": 7,
        "updated_at": "2026-08-26T00:00:00+00:00",
        "source": {"video_uri": f"/{task_id}.mov", "title": "测试热点"},
        "workflow": {
            "step_1": {"output": {"content_summary": "人物触发视觉变身"}},
            "step_2": {"output": {"primary_selling_point": {"description": "一秒变身", "tags": ["state_transformation"], "confidence": .9}, "secondary_selling_points": [], "replication_goal": {"preserve": [], "replace": [], "adapt": [], "optional": []}}},
            "step_3": {"output": {"selected_chain": "single_image", "selection_reason": "最终模型只需一张首图", "case_ids": ["case-1"], "risks": ["身份可能漂移"]}},
            "step_4": {"output": {"runtime_inputs": [{"id": "user_image", "description": "用户图"}], "base_materials": [], "nodes": [{"id": "generate_video", "model": "Kling", "inputs": ["user_image"], "outputs": ["result_video"], "dependencies": [], "parameters": {}}], "risks": []}},
            "step_5": {"output": {}},
            "step_6": {"output": {"node_prompts": [{"node_id": "generate_video", "model": "Kling", "variants": [{"variant_id": "default", "conditions": {}, "prompt": "保持人物身份，全程避免闪烁"}]}], "coverage_gaps": []}},
            "step_7": {"output": {}},
        }, "artifacts": {}, "issues": [],
    }


class WorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.outputs = Path(self.temp.name) / "outputs"
        self.outputs.mkdir()
        self.store = WorkbenchStore(self.outputs)
        task_dir = self.outputs / "task-demo"
        task_dir.mkdir()
        (task_dir / "task-result.json").write_text(json.dumps(completed_task("task-demo"), ensure_ascii=False), encoding="utf-8")
        self.store.create_batch({"batch_id": "batch-demo", "name": "热点批次", "creator": "caoying07"}, [{"task_id": "task-demo", "priority": "high"}])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_agent_result_is_projected_without_mutation(self) -> None:
        original = (self.outputs / "task-demo" / "task-result.json").read_text(encoding="utf-8")
        work = self.store.get_work_item("task-demo")
        self.assertEqual(work["business_status"], "pending_review")
        self.assertEqual(work["plan"]["selected_chain"], "single_image")
        self.assertEqual(work["validation"], [])
        self.assertEqual(work["uploader"], "caoying07")
        self.assertEqual(work["uploaded_at"], work["created_at"])
        self.assertEqual((self.outputs / "task-demo" / "task-result.json").read_text(encoding="utf-8"), original)

    def test_incomplete_custom_node_is_not_deliverable(self) -> None:
        plan = self.store.get_work_item("task-demo")["plan"]
        plan["nodes"].append({
            "id": "custom_node_1", "display_name": "新生成节点", "model": "",
            "inputs": [], "outputs": [], "dependencies": [], "needs_input": True,
        })
        issues = validate_plan(plan)
        codes = {issue["code"] for issue in issues}
        self.assertIn("missing_node_input", codes)
        self.assertIn("missing_node_output", codes)

    def test_blank_prompt_is_not_deliverable(self) -> None:
        plan = self.store.get_work_item("task-demo")["plan"]
        plan["node_prompts"][0]["variants"][0]["prompt"] = ""
        self.assertIn(
            "missing_prompt_text",
            {issue["code"] for issue in validate_plan(plan)},
        )

    def test_multi_image_completed_task_is_reviewable(self) -> None:
        task = completed_task("task-multi")
        task["workflow"]["step_3"]["output"]["selected_chain"] = "multi_image"
        task_dir = self.outputs / "task-multi"
        task_dir.mkdir()
        (task_dir / "task-result.json").write_text(
            json.dumps(task, ensure_ascii=False), encoding="utf-8"
        )
        self.store.create_batch(
            {"batch_id": "batch-multi", "name": "多图批次"},
            [{"task_id": "task-multi"}],
        )

        work = self.store.get_work_item("task-multi")

        self.assertEqual(work["business_status"], "pending_review")
        self.assertNotIn("unsupported_chain", {item["code"] for item in work["validation"]})

    def test_revision_uses_optimistic_lock_and_audit(self) -> None:
        work = self.store.get_work_item("task-demo")
        plan = work["plan"]
        plan["primary_selling_point"]["description"] = "设计师修正卖点"
        saved = self.store.save_revision("task-demo", plan, actor="Alice", reason="修正误判", expected_version=1)
        self.assertEqual(saved["item"]["version"], 2)
        self.assertEqual(saved["revision"]["reason"], "修正误判")
        with self.assertRaises(RevisionConflict):
            self.store.save_revision("task-demo", plan, actor="Bob", reason="并发修改", expected_version=1)

    def test_broken_node_reference_blocks_delivery(self) -> None:
        work = self.store.get_work_item("task-demo")
        work["plan"]["nodes"][0]["inputs"] = ["missing_input"]
        issues = validate_plan(work["plan"])
        self.assertIn("broken_input", {issue["code"] for issue in issues})
        self.store.save_revision("task-demo", work["plan"], actor="Alice", reason="测试", expected_version=1)
        with self.assertRaises(WorkbenchError):
            self.store.submit_review("task-demo", 2)

    def test_delivery_is_frozen_and_export_contains_four_sheets(self) -> None:
        submitted = self.store.submit_review("task-demo", 1)
        delivered = self.store.confirm_delivery("task-demo", submitted["version"], "Alice")
        markdown = Path(delivered["markdown_path"])
        self.assertTrue(markdown.exists())
        self.assertIn("未经真实模型跑片验证", markdown.read_text(encoding="utf-8"))
        exported = self.store.export_batch("batch-demo")
        with zipfile.ZipFile(exported["xlsx"]) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
            for name in ("任务汇总", "节点明细", "Prompt明细", "素材与风险"):
                self.assertIn(name, workbook_xml)
        with zipfile.ZipFile(exported["zip"]) as archive:
            self.assertIn("plans/task-demo.md", archive.namelist())
            self.assertIn("FAILED.txt", archive.namelist())


if __name__ == "__main__":
    unittest.main()
