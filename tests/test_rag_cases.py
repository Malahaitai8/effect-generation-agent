from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "rag" / "case.schema.json"
CASES_PATH = ROOT / "rag" / "data" / "cases.jsonl"


class RagCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.cases = [
            json.loads(line)
            for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_all_non_empty_mvp_cases_are_valid(self) -> None:
        validator = Draft202012Validator(
            self.schema,
            format_checker=FormatChecker(),
        )
        self.assertEqual(len(self.cases), 45)
        for case in self.cases:
            with self.subTest(case_id=case.get("case_id")):
                validator.validate(case)

    def test_case_ids_are_unique(self) -> None:
        case_ids = [case["case_id"] for case in self.cases]
        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_formal_cases_have_at_least_one_generation_prompt(self) -> None:
        for case in self.cases:
            generation_prompts = [
                prompt
                for node in case["nodes"]
                if node["node_type"] in {"image_generation", "video_generation"}
                for prompt in node["prompts"]
            ]
            if not generation_prompts:
                self.assertTrue(
                    any("无需 Prompt" in note for note in case["source_notes"]),
                    case["case_id"],
                )

    def test_classification_nodes_have_no_prompts(self) -> None:
        for case in self.cases:
            for node in case["nodes"]:
                if node["node_type"] == "classification":
                    self.assertEqual(node["prompts"], [], case["case_id"])

    def test_node_graph_materials_and_prompts_are_valid(self) -> None:
        for case in self.cases:
            node_ids = {node["id"] for node in case["nodes"]}
            material_by_id = {material["id"]: material for material in case["materials"]}
            self.assertEqual(len(node_ids), len(case["nodes"]))
            self.assertEqual(
                [node["order"] for node in case["nodes"]],
                list(range(1, len(case["nodes"]) + 1)),
            )
            for node in case["nodes"]:
                with self.subTest(case_id=case["case_id"], node_id=node["id"]):
                    self.assertTrue(set(node["dependencies"]).issubset(node_ids))
                    self.assertNotIn(node["id"], node["dependencies"])
                    self.assertTrue(set(node["inputs"]).issubset(material_by_id))
                    self.assertTrue(set(node["outputs"]).issubset(material_by_id))
                    for output in node["outputs"]:
                        self.assertEqual(material_by_id[output]["source_type"], "node_output")
                    if node["prompts"]:
                        self.assertIn(
                            node["node_type"],
                            {"prompt_generation", "image_generation", "video_generation"},
                        )
                        self.assertIsNotNone(node["model"])

            visiting: set[str] = set()
            visited: set[str] = set()
            dependencies = {node["id"]: set(node["dependencies"]) for node in case["nodes"]}

            def visit(node_id: str) -> None:
                self.assertNotIn(node_id, visiting, f"dependency cycle in {case['case_id']}")
                if node_id in visited:
                    return
                visiting.add(node_id)
                for dependency in dependencies[node_id]:
                    visit(dependency)
                visiting.remove(node_id)
                visited.add(node_id)

            for node_id in node_ids:
                visit(node_id)

    def test_final_video_input_matches_route_type(self) -> None:
        for case in self.cases:
            final_nodes = [node for node in case["nodes"] if node["is_final_video_node"]]
            self.assertEqual(len(final_nodes), 1, case["case_id"])
            final_node = final_nodes[0]
            self.assertEqual(final_node["node_type"], "video_generation")
            material_types = {
                material["id"]: material["media_type"] for material in case["materials"]
            }
            input_types = [material_types[material_id] for material_id in final_node["inputs"]]
            if case["route_type"] == "single_image":
                self.assertEqual(input_types.count("image"), 1)
                self.assertEqual(input_types.count("video"), 0)
            elif case["route_type"] == "multi_image":
                self.assertGreaterEqual(input_types.count("image"), 2)
                self.assertEqual(input_types.count("video"), 0)
            else:
                self.assertGreaterEqual(input_types.count("video"), 1)

    def test_cases_store_references_not_media_files(self) -> None:
        forbidden_keys = {
            "video_file",
            "image_file",
            "media_file",
            "attachment",
            "binary",
        }

        def visit(value: object) -> None:
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        for case in self.cases:
            visit(case)

    def test_reference_video_cases_cover_direct_and_prepared_subject_inputs(self) -> None:
        direct_cases: list[str] = []
        prepared_cases: list[str] = []
        for case in self.cases:
            if case["route_type"] != "reference_video":
                continue
            materials = {material["id"]: material for material in case["materials"]}
            final_node = next(node for node in case["nodes"] if node["is_final_video_node"])
            image_sources = {
                materials[input_id]["source_type"]
                for input_id in final_node["inputs"]
                if materials[input_id]["media_type"] == "image"
            }
            if "user_input" in image_sources:
                direct_cases.append(case["case_id"])
            if "node_output" in image_sources:
                prepared_cases.append(case["case_id"])

        self.assertTrue(direct_cases, "案例库缺少用户图直入参考视频节点的案例")
        self.assertTrue(prepared_cases, "案例库缺少先生成主体图再进入参考视频节点的案例")
        for case_id in direct_cases + prepared_cases:
            case = next(case for case in self.cases if case["case_id"] == case_id)
            self.assertEqual(case["route_type"], "reference_video")


if __name__ == "__main__":
    unittest.main()
