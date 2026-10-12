from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "skills" / "effect-generation-workflow" / "scripts" / "extract-video.py"
SPEC = importlib.util.spec_from_file_location("extract_video", SCRIPT_PATH)
assert SPEC and SPEC.loader
extract_video = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract_video)


class ExtractVideoTests(unittest.TestCase):
    def test_parses_ffmpeg_metadata(self) -> None:
        output = """
Duration: 00:00:08.94, start: 0.000000, bitrate: 9000 kb/s
Stream #0:0: Video: h264, yuv420p, 1080x1920, 30 fps, 30 tbr
Stream #0:1: Audio: aac, 44100 Hz, stereo
"""
        metadata = extract_video.parse_ffmpeg_metadata(output)
        self.assertEqual(metadata["duration_seconds"], 8.94)
        self.assertEqual((metadata["width"], metadata["height"]), (1080, 1920))
        self.assertEqual(metadata["frame_rate"], 30.0)
        self.assertTrue(metadata["has_audio"])

    def test_sampling_interval_respects_frame_cap(self) -> None:
        self.assertEqual(extract_video.sampling_interval(10, 2, 40), 0.5)
        self.assertAlmostEqual(extract_video.sampling_interval(100, 2, 40), 100 / 39)

    def test_sampling_requires_room_for_first_and_tail_frames(self) -> None:
        with self.assertRaises(extract_video.PreprocessingError):
            extract_video.sampling_interval(10, 2, 1)


if __name__ == "__main__":
    unittest.main()
