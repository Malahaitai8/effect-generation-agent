from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from effect_generation_agent.materials import (
    GeneratedMaterial,
    MaterialProcessor,
    Step5MaterialExecutor,
)
from effect_generation_agent.workflow import StepContext


ROOT = Path(__file__).resolve().parents[1]


class MaterialProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.task_dir = self.root / "outputs" / "task-materials"
        self.materials_dir = self.task_dir / "materials"
        self.materials_dir.mkdir(parents=True)
        self.processor = MaterialProcessor(ROOT)
        self.ffmpeg = self.processor._resolve_ffmpeg()
        self.image = self.root / "source.jpg"
        self.video = self.root / "source.mp4"
        subprocess.run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=320x240", "-frames:v", "1",
                str(self.image),
            ],
            check=True,
        )
        subprocess.run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "2",
                "-pix_fmt", "yuv420p", str(self.video),
            ],
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def context(self, requirements: list[dict]) -> StepContext:
        return StepContext(
            task_id="task-materials",
            step=5,
            inputs=MappingProxyType(
                {
                    "source": {
                        "video_uri": str(self.video),
                        "metadata": {
                            "materials": [{"id": "user_image", "path": str(self.image)}]
                        },
                    },
                    "workflow.step_1.output": {
                        "key_frames": [],
                        "video_preprocessing": {
                            "frames_manifest_ref": str(self.root / "unused.json")
                        },
                    },
                    "workflow.step_4.output": {
                        "runtime_inputs": [],
                        "base_materials": requirements,
                    },
                    "artifacts.materials_dir": str(self.materials_dir),
                }
            ),
            artifacts=MappingProxyType({"materials_dir": str(self.materials_dir)}),
        )

    def test_direct_copy_and_image_transform_are_idempotent(self) -> None:
        requirements = [
            {
                "id": "direct_image",
                "purpose": "direct input",
                "required": True,
                "requirements": {
                    "source": {"path": str(self.image)},
                    "operation": "direct",
                    "target": {"media_type": "image", "format": "jpg", "width": 320, "height": 240},
                },
            },
            {
                "id": "square_image",
                "purpose": "resized input",
                "required": True,
                "requirements": {
                    "source": {"path": str(self.image)},
                    "operation": "transform",
                    "target": {"media_type": "image", "format": "png", "width": 128, "height": 128},
                },
            },
            {
                "id": "cropped_image",
                "purpose": "cropped input",
                "required": True,
                "requirements": {
                    "source": {"path": str(self.image)},
                    "operation": "crop",
                    "crop": {"x": 40, "y": 20, "width": 200, "height": 200},
                    "target": {"media_type": "image", "format": "jpg", "width": 100, "height": 100},
                },
            },
        ]
        executor = Step5MaterialExecutor(self.processor)

        first = executor.execute(self.context(requirements))
        second = executor.execute(self.context(requirements))

        self.assertEqual(first.status, "completed")
        self.assertTrue(first.output["ready_for_prompting"])
        self.assertEqual(second.status, "completed")
        self.assertTrue((self.materials_dir / "direct_image.jpg").is_file())
        self.assertTrue((self.materials_dir / "square_image.png").is_file())
        self.assertTrue((self.materials_dir / "cropped_image.jpg").is_file())

    def test_runtime_user_input_does_not_require_a_current_file(self) -> None:
        context = self.context([])
        inputs = dict(context.inputs)
        inputs["source"] = {"video_uri": str(self.video), "metadata": {}}
        inputs["workflow.step_4.output"] = {
            "runtime_inputs": [
                {
                    "id": "user_image",
                    "media_type": "image",
                    "purpose": "Future effect user identity",
                    "required": True,
                    "requirements": {"subject_clear": True},
                }
            ],
            "base_materials": [],
        }
        result = Step5MaterialExecutor(self.processor).execute(
            StepContext(
                task_id=context.task_id,
                step=context.step,
                inputs=MappingProxyType(inputs),
                artifacts=context.artifacts,
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["materials"], [])
        self.assertTrue(result.output["ready_for_prompting"])

    def test_video_clip_and_targeted_frame_extraction(self) -> None:
        requirements = [
            {
                "id": "clip",
                "purpose": "short reference",
                "required": True,
                "requirements": {
                    "source": {"kind": "source_video"},
                    "operation": "transform",
                    "clip": {"start_seconds": 0.25, "duration_seconds": 1.0},
                    "target": {
                        "media_type": "video", "format": "mp4", "width": 160,
                        "height": 120, "duration_seconds": 1.0,
                    },
                },
            },
            {
                "id": "exception_frame",
                "purpose": "exception-only targeted extraction",
                "required": True,
                "requirements": {
                    "source": {"kind": "source_video"},
                    "operation": "transform",
                    "timestamp_seconds": 0.5,
                    "target": {"media_type": "image", "format": "jpg", "width": 160, "height": 120},
                },
            },
        ]

        result = Step5MaterialExecutor(self.processor).execute(self.context(requirements))

        self.assertEqual(result.status, "completed")
        self.assertTrue((self.materials_dir / "clip.mp4").is_file())
        self.assertTrue((self.materials_dir / "exception_frame.jpg").is_file())
        self.assertFalse((self.task_dir / "video" / "frames.json").exists())

    def test_image_generation_blocks_when_generator_is_unavailable(self) -> None:
        requirement = {
            "id": "generated_first_frame",
            "purpose": "styled first frame",
            "required": True,
            "requirements": {
                "source": {"path": str(self.image)},
                "operation": "image_to_image",
                "description": "Preserve subject and apply the target style.",
                "target": {"media_type": "image", "format": "png", "width": 128, "height": 128},
            },
        }
        executor = Step5MaterialExecutor(self.processor)

        blocked = executor.execute(self.context([requirement]))

        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.errors[0]["code"], "image_generation_unavailable")
        self.assertEqual(blocked.output["unresolved_materials"], ["generated_first_frame"])
        self.assertFalse((self.task_dir / "manual" / "image-generation").exists())

    def test_missing_business_asset_blocks_without_designer_request(self) -> None:
        requirement = {
            "id": "brand_logo",
            "purpose": "official brand asset",
            "required": True,
            "requirements": {
                "source": {"kind": "business_asset", "id": "brand_logo"},
                "operation": "direct",
                "target": {"media_type": "image", "format": "png"},
            },
        }

        result = Step5MaterialExecutor(self.processor).execute(self.context([requirement]))

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.errors[0]["code"], "material_source_missing")
        self.assertEqual(result.output["unresolved_materials"], ["brand_logo"])

    def test_image_generation_uses_automatic_generator(self) -> None:
        test_case = self

        class FakeGenerator:
            def generate(self, **kwargs):
                subprocess.run(
                    [
                        test_case.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(test_case.image), "-vf", "scale=128:128",
                        str(kwargs["output_path"]),
                    ],
                    check=True,
                )
                return GeneratedMaterial(
                    path=kwargs["output_path"],
                    model="fake-image-model",
                    evidence=("Generated image matches the requested style.",),
                )

        requirement = {
            "id": "generated_first_frame",
            "purpose": "styled first frame",
            "required": True,
            "requirements": {
                "source": {"path": str(self.image)},
                "operation": "image_to_image",
                "description": "Preserve subject and apply the target style.",
                "target": {"media_type": "image", "format": "png", "width": 128, "height": 128},
            },
        }
        result = Step5MaterialExecutor(MaterialProcessor(ROOT, FakeGenerator())).execute(
            self.context([requirement])
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.output["ready_for_prompting"])
        self.assertIn("generator_model:fake-image-model", result.output["materials"][0]["evidence"])


if __name__ == "__main__":
    unittest.main()
