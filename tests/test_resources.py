from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.resources import JsonCaseSnapshotReader, load_runtime_resources


ROOT = Path(__file__).resolve().parents[1]


class RuntimeResourcesTests(unittest.TestCase):
    def test_default_resources_expose_prompts_and_model_capabilities(self) -> None:
        resources = load_runtime_resources(ROOT)

        self.assertTrue(Path(resources.prompt_paths["step_4.single_image"]).is_file())
        self.assertTrue(Path(resources.prompt_paths["step_4.multi_image"]).is_file())
        self.assertTrue(Path(resources.prompt_paths["step_6.multi_image"]).is_file())
        self.assertTrue(resources.model_capabilities)
        self.assertEqual(resources.model_capabilities["reference_type"], "case_observed")
        models = resources.model_capabilities["models"]
        self.assertIn("kling_video_3_0_omni", models)
        self.assertEqual(models["kling_video_3_0_omni"]["category"], "video_generation")
        self.assertIn("参考视频", models["kling_video_3_0_omni"]["observed_inputs"])
        self.assertEqual(models["image_2"]["confidence"], "low")
        self.assertEqual(models["kling_video_2_5_pro"]["confidence"], "low")
        self.assertEqual(models["kling_video_3_0_pro"]["confidence"], "low")
        self.assertIn("uncertainty_rule", resources.model_capabilities["usage_policy"])
        with self.assertRaises(TypeError):
            resources.prompt_paths["new"] = "not-allowed"  # type: ignore[index]

    def test_case_snapshot_reader_accepts_configured_outputs_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outputs_root = Path(temporary_directory) / "outputs"
            outputs_root.mkdir()
            snapshot_path = outputs_root / "case-snapshot.json"
            snapshot_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
            reader = JsonCaseSnapshotReader(ROOT, outputs_root)

            self.assertEqual(dict(reader.read(str(snapshot_path))), {"cases": []})

    def test_case_observed_models_have_designer_reference_fields(self) -> None:
        resources = load_runtime_resources(ROOT)

        for model_id, model in resources.model_capabilities["models"].items():
            with self.subTest(model_id=model_id):
                self.assertTrue(model["display_name"])
                self.assertIn(model["category"], {"image_generation", "video_generation"})
                self.assertIsInstance(model["aliases"], list)
                self.assertTrue(model["observed_uses"])
                self.assertIsInstance(model["observed_inputs"], list)
                self.assertTrue(model["observed_outputs"])
                self.assertTrue(model["reference_cases"])
                self.assertIn(model["confidence"], {"high", "medium", "low"})
                self.assertTrue(model["notes"])

    def test_case_snapshot_reader_rejects_unconfigured_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            outputs_root = temporary_root / "outputs"
            outputs_root.mkdir()
            outside_path = temporary_root / "outside.json"
            outside_path.write_text("{}", encoding="utf-8")
            reader = JsonCaseSnapshotReader(ROOT, outputs_root)

            with self.assertRaises(ValueError):
                reader.read(str(outside_path))


if __name__ == "__main__":
    unittest.main()
