from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "task-result.schema.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "minimal-task-result.json"


class TaskResultSchemaTests(unittest.TestCase):
    def test_schema_and_fixture_are_valid_json(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(fixture["schema_version"], "0.9.0")

    def test_fixture_contains_all_steps(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(fixture["workflow"]), {f"step_{index}" for index in range(1, 8)})

    def test_main_retrieval_is_bounded_by_schema(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        definition = schema["$defs"]["step_3"]["allOf"][1]["properties"]["main_retrieval_count"]
        self.assertEqual(definition["maximum"], 1)

    def test_mvp_chain_values_are_explicit(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        values = schema["$defs"]["step_3"]["allOf"][1]["properties"]["output"]["anyOf"][1]["properties"]["selected_chain"]["enum"]
        self.assertEqual(values, ["single_image", "reference_video", "multi_image", "unsupported"])

    def test_prompt_variant_contains_only_execution_prompt_fields(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        definition = schema["$defs"]["prompt_variant"]
        self.assertEqual(definition["required"], ["variant_id", "conditions", "prompt"])
        self.assertNotIn("material_refs", definition["properties"])
        self.assertNotIn("case_refs", definition["properties"])
        self.assertNotIn("constraints", definition["properties"])
        self.assertNotIn("negative_prompt", definition["properties"])


if __name__ == "__main__":
    unittest.main()
