from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.executors import build_manual_executors
from effect_generation_agent.materials import MaterialProcessor
from effect_generation_agent.model_execution import ManualExchangeModelClient
from effect_generation_agent.resources import load_runtime_resources
from effect_generation_agent.store import TaskStore
from effect_generation_agent.workflow import StepContext, StepResult, WorkflowEngine


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "task-result.schema.json"


class FixedStep3Executor:
    def __init__(self, selected_chain: str) -> None:
        self.selected_chain = selected_chain

    def execute(self, context: StepContext) -> StepResult:
        task_dir = Path(context.artifacts["materials_dir"]).parent
        snapshot = task_dir / "case-snapshot.json"
        snapshot.write_text(
            json.dumps({"cases": [{"case_id": "case_1", "chain": self.selected_chain}]}),
            encoding="utf-8",
        )
        return StepResult(
            status="completed",
            output={
                "selected_chain": self.selected_chain,
                "control_requirements": {
                    "must_preserve": [],
                    "may_change": [],
                    "temporal_reference_required": self.selected_chain == "reference_video",
                    "required_image_states": 1,
                    "evidence": [],
                },
                "selection_reason": "Fixed integration fixture for downstream verification.",
                "alternative_chain": None,
                "case_snapshot_ref": str(snapshot),
                "case_ids": ["case_1"],
                "risks": [],
            },
            artifact_updates={"case_snapshot_path": str(snapshot)},
        )


class ManualEndToEndTests(unittest.TestCase):
    def test_single_image_and_reference_video_complete_with_fixed_step_3(self) -> None:
        for chain in ("single_image", "reference_video"):
            with self.subTest(chain=chain), tempfile.TemporaryDirectory() as temporary_directory:
                temporary = Path(temporary_directory)
                outputs = temporary / "outputs"
                source_image, source_video = self._create_media(temporary)
                store = TaskStore(outputs, SCHEMA)
                task_id = f"task-e2e-{chain.replace('_', '-')}"
                store.create_task(
                    task_id,
                    str(source_video),
                    metadata={"materials": [{"id": "subject", "path": str(source_image)}]},
                )
                client = ManualExchangeModelClient(outputs, store.validator.schema_version)
                engine = WorkflowEngine(
                    store,
                    build_manual_executors(
                        ROOT, client, step_3_executor=FixedStep3Executor(chain)
                    ),
                    resources=load_runtime_resources(ROOT, outputs),
                )

                state = engine.run(task_id)
                self.assertEqual((state["current_step"], state["status"]), (1, "needs_input"))
                request = client.pending_request(task_id, 1)
                client.submit(task_id, 1, self._step_1_output(request))

                state = engine.resume(task_id)
                self.assertEqual((state["current_step"], state["status"]), (2, "needs_input"))
                client.submit(task_id, 2, self._step_2_output())

                state = engine.resume(task_id)
                self.assertEqual((state["current_step"], state["status"]), (4, "needs_input"))
                client.submit(task_id, 4, self._step_4_output(chain, source_video))

                state = engine.resume(task_id)
                self.assertEqual((state["current_step"], state["status"]), (6, "needs_input"))
                client.submit(task_id, 6, self._step_6_output(chain))

                completed = engine.resume(task_id)
                self.assertEqual(completed["status"], "completed")
                self.assertTrue(Path(completed["artifacts"]["production_plan_path"]).is_file())
                self.assertTrue(completed["workflow"]["step_5"]["output"]["ready_for_prompting"])

    @staticmethod
    def _create_media(directory: Path) -> tuple[Path, Path]:
        ffmpeg = MaterialProcessor(ROOT)._resolve_ffmpeg()
        image = directory / "subject.jpg"
        video = directory / "source.mp4"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "color=c=blue:s=320x240", "-frames:v", "1", str(image)],
            check=True,
        )
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=size=320x240:rate=10", "-t", "2", "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        return image, video

    @staticmethod
    def _step_1_output(request: dict) -> dict:
        preprocessing = request["inputs"]["video_preprocessing"]
        return {
            "video_preprocessing": {
                key: preprocessing[key]
                for key in ("metadata_ref", "frames_manifest_ref", "timeline_overview_ref", "frames_dir")
            },
            "content_summary": "A subject appears in a short reference clip.",
            "visual_style": {},
            "narrative_structure": "single event",
            "timeline": [],
            "observations": {
                "subjects": [], "scene": {}, "actions": [], "physical_interactions": [],
                "camera_and_composition": [], "visual_effects": [], "state_changes": [],
                "observed_text": [], "audio": {},
            },
            "key_frames": [],
            "screen_recording_artifacts": [],
            "uncertainties": [],
        }

    @staticmethod
    def _step_2_output() -> dict:
        selling_point = {
            "description": "The effect preserves one recognizable subject through the motion.",
            "tags": ["subject_motion"],
            "evidence_event_ids": [],
            "evidence_frame_ids": [],
            "removal_test": "Without the motion there is no effect.",
            "confidence": 0.9,
        }
        return {
            "primary_selling_point": selling_point,
            "secondary_selling_points": [],
            "replication_goal": {
                "replace": [],
                "preserve": [{"id": "subject_identity", "description": "subject"}],
                "adapt": [],
                "optional": [],
            },
            "control_signals": {
                "critical_visual_states": [], "continuous_processes": [], "physical_interactions": [],
                "camera_requirements": [], "text_requirements": [], "audio_requirements": [],
            },
            "alternative_interpretations": [],
            "uncertainties": [],
        }

    @staticmethod
    def _step_4_output(chain: str, source_video: Path) -> dict:
        if chain == "single_image":
            nodes = [{
                "id": "generate_video", "role": "Generate video from one image", "model": "video-model",
                "model_selection_reason": "Accepts one image", "inputs": ["user_image"],
                "outputs": ["generated_video"], "dependencies": [], "parameters": {},
                "prompt_routing": None,
            }]
            runtime_inputs = [{
                "id": "user_image", "media_type": "image",
                "purpose": "Subject image supplied when the effect runs", "required": True,
                "requirements": {"subject_clear": True},
            }]
            materials = []
        else:
            nodes = [{
                "id": "generate_video", "role": "Generate video from reference motion", "model": "reference-model",
                "model_selection_reason": "Accepts reference video and subject image",
                "inputs": ["reference_video", "subject_image"], "outputs": ["generated_video"],
                "dependencies": [], "parameters": {},
                "prompt_routing": None,
            }]
            materials = [
                {
                    "id": "reference_video", "purpose": "Motion reference", "required": True,
                    "requirements": {
                        "source": {"path": str(source_video)}, "operation": "direct",
                        "target": {"media_type": "video", "format": "mp4", "width": 320, "height": 240},
                    },
                },
            ]
            runtime_inputs = [{
                "id": "subject_image", "media_type": "image",
                "purpose": "Replacement subject supplied when the effect runs", "required": True,
                "requirements": {"subject_clear": True},
            }]
        return {
            "nodes": nodes,
            "runtime_inputs": runtime_inputs,
            "base_materials": materials,
            "unresolved_materials": [],
            "appearance_strategy": {
                "mode": "preserve_input",
                "reason": "The test keeps the supplied appearance.",
                "presentation_sensitive_elements": [],
                "shared_elements": ["action", "camera"],
            },
            "prompt_branching": {
                "required": False,
                "reason": "No varying appearance elements.",
                "dimensions": [],
            },
            "risks": [],
        }

    @staticmethod
    def _step_6_output(chain: str) -> dict:
        return {
            "node_prompts": [{
                "node_id": "generate_video",
                "model": "video-model" if chain == "single_image" else "reference-model",
                "variants": [{
                    "variant_id": "default",
                    "conditions": {},
                    "prompt": "Preserve the subject and reproduce the selected motion.",
                }],
            }],
            "prompt_audit": [{"node_id": "generate_video", "case_refs": ["case_1"], "notes": []}],
            "case_snapshot_ref": "case-snapshot.json",
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
        }


if __name__ == "__main__":
    unittest.main()
