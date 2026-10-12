from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.store import TaskStore


ROOT = Path(__file__).resolve().parents[1]
TEST_CASES_DIR = ROOT / "测试用例"
SCHEMA_PATH = ROOT / "schemas" / "task-result.schema.json"
LEAK_LABELS = ("单图驱动", "参考视频", "single_image", "reference_video")


class BlindEvaluationInputTests(unittest.TestCase):
    def test_test_video_filenames_do_not_contain_route_labels(self) -> None:
        video_names = [path.name for path in TEST_CASES_DIR.glob("*.mov")]
        self.assertEqual(len(video_names), 9)
        for name in video_names:
            with self.subTest(name=name):
                self.assertFalse(any(label in name for label in LEAK_LABELS))

    def test_neutral_task_identity_does_not_reintroduce_route_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TaskStore(Path(temp_dir), SCHEMA_PATH)
            task = store.create_task(
                "blind-case-001",
                str(TEST_CASES_DIR / "泡面奇遇.mov"),
                title=None,
            )
            serialized = json.dumps(
                {
                    "task_id": task["task_id"],
                    "source": task["source"],
                    "task_dir": str(Path(temp_dir) / task["task_id"]),
                },
                ensure_ascii=False,
            )
            self.assertFalse(any(label in serialized for label in LEAK_LABELS))


if __name__ == "__main__":
    unittest.main()
