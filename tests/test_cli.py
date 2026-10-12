from __future__ import annotations

import io
import json
import tempfile
import unittest
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from effect_generation_agent.cli import main
from effect_generation_agent.mock_executor import build_mock_executors
from effect_generation_agent.materials import MaterialProcessor
from effect_generation_agent.store import TaskStore
from effect_generation_agent.workflow import WorkflowEngine


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "task-result.schema.json"


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.outputs_root = Path(self.temporary_directory.name) / "outputs"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def call(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(list(arguments))
        return exit_code, json.loads(stdout.getvalue())

    def test_cli_create_show_and_run(self) -> None:
        base = ("task", "--outputs-dir", str(self.outputs_root))
        code, created = self.call(
            *base,
            "create",
            "--task-id",
            "task-cli-001",
            "--video-uri",
            "inputs/example.mp4",
        )
        self.assertEqual(code, 0)
        self.assertEqual(created["status"], "initialized")

        code, shown = self.call(*base, "show", "task-cli-001")
        self.assertEqual(code, 0)
        self.assertEqual(shown["task_id"], "task-cli-001")

        code, completed = self.call(*base, "run", "task-cli-001", "--mock")
        self.assertEqual(code, 0)
        self.assertEqual(completed["status"], "completed")

    def test_cli_resume_uses_same_runtime_path(self) -> None:
        store = TaskStore(self.outputs_root, SCHEMA_PATH)
        store.create_task("task-cli-resume", "inputs/example.mp4")
        WorkflowEngine(store, build_mock_executors({1: "blocked"})).run(
            "task-cli-resume"
        )

        code, completed = self.call(
            "task",
            "--outputs-dir",
            str(self.outputs_root),
            "resume",
            "task-cli-resume",
            "--mock",
        )

        self.assertEqual(code, 0)
        self.assertEqual(completed["status"], "completed")

    def test_cli_batch_create_run_and_show(self) -> None:
        manifest_path = Path(self.temporary_directory.name) / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                [
                    {"task_id": "cli-batch-a", "video_uri": "a.mp4"},
                    {"task_id": "cli-batch-b", "video_uri": "b.mp4"},
                ]
            ),
            encoding="utf-8",
        )
        base = ("batch", "--outputs-dir", str(self.outputs_root))
        code, created = self.call(
            *base, "create", "--batch-id", "cli-batch", "--manifest", str(manifest_path)
        )
        self.assertEqual(code, 0)
        self.assertEqual(created["status"], "initialized")
        code, completed = self.call(
            *base, "run", "cli-batch", "--mock", "--max-concurrency", "2"
        )
        self.assertEqual(code, 0)
        self.assertEqual(completed["status"], "completed")
        code, shown = self.call(*base, "show", "cli-batch")
        self.assertEqual(code, 0)
        self.assertEqual(shown["status"], "completed")

    def test_manual_run_exports_step_1_and_submit_advances_to_step_2(self) -> None:
        ffmpeg = MaterialProcessor(ROOT)._resolve_ffmpeg()
        video = Path(self.temporary_directory.name) / "manual.mp4"
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", "testsrc=size=160x120:rate=5", "-t", "1", "-pix_fmt", "yuv420p",
                str(video),
            ],
            check=True,
        )
        base = ("task", "--outputs-dir", str(self.outputs_root))
        self.call(
            *base, "create", "--task-id", "task-cli-manual", "--video-uri", str(video)
        )

        code, waiting = self.call(*base, "run", "task-cli-manual", "--manual")

        self.assertEqual(code, 0)
        self.assertEqual(waiting["status"], "needs_input")
        code, request = self.call(*base, "pending-request", "task-cli-manual")
        self.assertEqual(code, 0)
        self.assertEqual(request["step"], 1)
        self.assertTrue(request["media_refs"])
        preprocessing = request["inputs"]["video_preprocessing"]
        result = {
            "video_preprocessing": {
                key: preprocessing[key]
                for key in (
                    "metadata_ref", "frames_manifest_ref", "timeline_overview_ref", "frames_dir"
                )
            },
            "content_summary": "Manual observation.",
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
        result_path = Path(self.temporary_directory.name) / "step1.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")

        code, step_2_waiting = self.call(
            *base, "submit", "task-cli-manual", "--result", str(result_path)
        )

        self.assertEqual(code, 0)
        self.assertEqual(step_2_waiting["status"], "needs_input")
        self.assertEqual(step_2_waiting["current_step"], 2)
        self.assertEqual(step_2_waiting["workflow"]["step_1"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
