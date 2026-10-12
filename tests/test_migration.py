from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.migration import migrate_task_040_to_050


ROOT = Path(__file__).resolve().parents[1]


class TaskMigrationTests(unittest.TestCase):
    def test_migrates_real_040_task_to_050_contract(self) -> None:
        source = ROOT / "outputs" / "trial-pool-water-gun-v04" / "task-result.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "task-result.json"
            shutil.copy2(source, target)

            migrated = migrate_task_040_to_050(
                target, ROOT / "schemas" / "task-result.schema.json"
            )

            self.assertEqual(migrated["schema_version"], "0.9.0")
            self.assertIn(
                "unresolved_materials", migrated["workflow"]["step_4"]["output"]
            )
            self.assertEqual(migrated["current_step"], 6)
            self.assertEqual(migrated["workflow"]["step_6"]["status"], "pending")
            self.assertIsNone(migrated["workflow"]["step_6"]["output"])
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8"))["schema_version"],
                "0.9.0",
            )


if __name__ == "__main__":
    unittest.main()
