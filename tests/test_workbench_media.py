from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from effect_generation_agent.workbench_server import WorkbenchApplication


class WorkbenchMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.outputs = Path(self.temp.name) / "outputs"
        self.outputs.mkdir()
        self.application = WorkbenchApplication(self.outputs)
        self.task_id = "task-media"
        self.task_dir = self.outputs / self.task_id
        self.task_dir.mkdir()
        analysis = self.task_dir / "video-analysis"
        frames = analysis / "frames"
        frames.mkdir(parents=True)
        (frames / "frame_0001.jpg").write_bytes(b"jpeg-one")
        (frames / "frame_0002.jpg").write_bytes(b"jpeg-two")
        manifest = {
            "frames": [
                {"frame_id": "frame_0001", "timestamp_seconds": 0.0, "file_ref": "frames/frame_0001.jpg"},
                {"frame_id": "frame_0002", "timestamp_seconds": 1.0, "file_ref": "frames/frame_0002.jpg"},
            ]
        }
        (analysis / "frames.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.video = self.task_dir / "source.mov"
        task = {
            "task_id": self.task_id, "status": "completed", "current_step": 7,
            "source": {"video_uri": str(self.video), "title": "媒体测试"},
            "workflow": {"step_1": {"output": {
                "content_summary": "测试视频",
                "video_preprocessing": {
                    "frames_manifest_ref": str(analysis / "frames.json"),
                    "frames_dir": str(frames),
                },
                "key_frames": [
                    {"frame_id": "frame_0001", "file_ref": "outputs/old-task/frame_0001.jpg", "timestamp_seconds": 0.0, "content_description": "起始帧"},
                    {"frame_id": "frame_0002", "file_ref": "outputs/old-task/frame_0002.jpg", "timestamp_seconds": 1.0, "content_description": "结束帧"},
                ],
            }}},
            "artifacts": {}, "issues": [],
        }
        (self.task_dir / "task-result.json").write_text(json.dumps(task), encoding="utf-8")
        self.application.workbench.create_batch(
            {"batch_id": "batch-media", "name": "媒体测试"}, [{"task_id": self.task_id}]
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reference_frames_use_manifest_when_historical_refs_are_stale(self) -> None:
        frames = self.application.reference_frames(self.task_id)
        self.assertEqual([item["frame_id"] for item in frames], ["frame_0001", "frame_0002"])
        self.assertEqual(
            self.application.reference_frame_path(self.task_id, "frame_0001"),
            (self.task_dir / "video-analysis" / "frames" / "frame_0001.jpg").resolve(),
        )

    def test_mov_is_cached_as_browser_mp4(self) -> None:
        ffmpeg = self.application._resolve_ffmpeg()
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x96:d=0.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.video)],
            check=True,
        )
        first = self.application.browser_media(self.task_id)
        second = self.application.browser_media(self.task_id)
        self.assertEqual(first, second)
        self.assertEqual(first.suffix, ".mp4")
        self.assertTrue(first.is_file())

    def test_invalid_frame_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(Exception, "参考帧 ID 无效"):
            self.application.reference_frame_path(self.task_id, "../secret")


if __name__ == "__main__":
    unittest.main()
