#!/usr/bin/env python3
"""Create one reusable analysis-frame set for a source video.

The script is deliberately semantic-free: it records metadata, extracts a
bounded set of original-resolution candidate frames, and builds a compact
timeline overview. A VLM later decides which candidates are meaningful.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VIDEO_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})(?:[^\n]*?([0-9.]+)\s*fps)?")
PTS_RE = re.compile(r"pts_time:([0-9.eE+-]+)")


class PreprocessingError(RuntimeError):
    pass


def parse_ffmpeg_metadata(stderr: str) -> dict[str, object]:
    duration_match = DURATION_RE.search(stderr)
    video_match = VIDEO_RE.search(stderr)
    if not duration_match or not video_match:
        raise PreprocessingError("FFmpeg output did not contain readable duration and video dimensions")

    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    fps = float(video_match.group(3)) if video_match.group(3) else None
    width, height = int(video_match.group(1)), int(video_match.group(2))
    return {
        "duration_seconds": round(duration, 6),
        "width": width,
        "height": height,
        "frame_rate": fps,
        "aspect_ratio": f"{width}:{height}",
        "has_audio": "Audio:" in stderr,
    }


def sampling_interval(duration: float, target_fps: float, max_frames: int) -> float:
    if duration <= 0:
        raise PreprocessingError("Video duration must be positive")
    if target_fps <= 0:
        raise PreprocessingError("target_fps must be positive")
    if max_frames < 2:
        raise PreprocessingError("max_frames must be at least 2")
    return max(1.0 / target_fps, duration / (max_frames - 1))


def resolve_ffmpeg(explicit: str | None) -> str:
    packaged = None
    try:
        import imageio_ffmpeg

        packaged = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass
    candidates = [
        explicit,
        os.environ.get("EFFECT_GENERATION_FFMPEG"),
        packaged,
        shutil.which("ffmpeg"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise PreprocessingError(
        "FFmpeg was not found. Install the project dependency imageio-ffmpeg, pass "
        "--ffmpeg /absolute/path/to/ffmpeg, or set EFFECT_GENERATION_FFMPEG."
    )


def run(command: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 and not allow_failure:
        detail = result.stderr.strip().splitlines()[-8:]
        raise PreprocessingError("FFmpeg command failed:\n" + "\n".join(detail))
    return result


def inspect_video(ffmpeg: str, video: Path) -> dict[str, object]:
    result = run([ffmpeg, "-hide_banner", "-i", str(video)], allow_failure=True)
    return parse_ffmpeg_metadata(result.stderr)


def extract_candidates(
    ffmpeg: str,
    video: Path,
    frames_dir: Path,
    *,
    interval: float,
    scene_threshold: float,
    max_frames: int,
) -> tuple[list[Path], list[float]]:
    output_pattern = frames_dir / "frame_%04d.jpg"
    select = (
        "select='eq(n,0)+gte(t-prev_selected_t,"
        f"{interval:.6f})+gt(scene,{scene_threshold:.3f})',showinfo"
    )
    result = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(video),
            "-vf",
            select,
            "-vsync",
            "vfr",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "2",
            str(output_pattern),
        ]
    )
    paths = sorted(frames_dir.glob("frame_*.jpg"))
    if not paths:
        raise PreprocessingError("FFmpeg completed without producing candidate frames")
    timestamps = [float(value) for value in PTS_RE.findall(result.stderr)]
    if len(timestamps) < len(paths):
        timestamps = [index * interval for index in range(len(paths))]
    return paths, timestamps[: len(paths)]


def append_tail_frame(
    ffmpeg: str,
    video: Path,
    frames_dir: Path,
    paths: list[Path],
    timestamps: list[float],
    *,
    duration: float,
    max_frames: int,
) -> tuple[list[Path], list[float]]:
    if len(paths) >= max_frames or duration - timestamps[-1] <= 0.05:
        return paths, timestamps
    tail_temp = frames_dir / "tail.jpg"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-sseof",
            f"-{min(0.5, duration):.6f}",
            "-i",
            str(video),
            "-update",
            "1",
            "-pix_fmt",
            "yuvj420p",
            "-q:v",
            "2",
            "-threads",
            "1",
            str(tail_temp),
        ]
    )
    if not tail_temp.is_file():
        raise PreprocessingError("FFmpeg did not produce the reserved tail frame")
    final_path = frames_dir / f"frame_{len(paths) + 1:04d}.jpg"
    tail_temp.replace(final_path)
    return [*paths, final_path], [*timestamps, duration]


def create_overview(ffmpeg: str, frames_dir: Path, output_path: Path, frame_count: int) -> bool:
    columns = 5
    rows = max(1, math.ceil(frame_count / columns))
    labeled_filter = (
        "scale=320:-2,"
        "drawtext=text='frame_%{eif\\:n+1\\:d\\:4}':x=8:y=h-th-8:"
        "fontsize=20:fontcolor=white:box=1:boxcolor=black@0.65,"
        f"tile={columns}x{rows}:padding=4:margin=4:color=black"
    )
    base = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        "1",
        "-i",
        str(frames_dir / "frame_%04d.jpg"),
        "-frames:v",
        "1",
    ]
    labeled = run(base[:-2] + ["-vf", labeled_filter] + base[-2:] + [str(output_path)], allow_failure=True)
    if labeled.returncode == 0 and output_path.exists():
        return True
    plain_filter = f"scale=320:-2,tile={columns}x{rows}:padding=4:margin=4:color=black"
    run(base[:-2] + ["-vf", plain_filter] + base[-2:] + [str(output_path)])
    return False


def existing_result(output_dir: Path, video: Path) -> dict[str, object] | None:
    metadata_path = output_dir / "metadata.json"
    manifest_path = output_dir / "frames.json"
    overview_path = output_dir / "timeline-overview.jpg"
    if not (metadata_path.exists() and manifest_path.exists() and overview_path.exists()):
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if metadata.get("source_video") != str(video.resolve()):
        return None
    if not all((output_dir / item["file_ref"]).is_file() for item in manifest.get("frames", [])):
        return None
    return {
        "reused": True,
        "metadata_ref": str(metadata_path.resolve()),
        "frames_manifest_ref": str(manifest_path.resolve()),
        "timeline_overview_ref": str(overview_path.resolve()),
        "frames_dir": str((output_dir / "frames").resolve()),
        "frame_count": len(manifest["frames"]),
    }


def preprocess(args: argparse.Namespace) -> dict[str, object]:
    video = Path(args.video).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not video.is_file():
        raise PreprocessingError(f"Video does not exist: {video}")

    if output_dir.exists():
        reused = existing_result(output_dir, video)
        if reused:
            return reused
        if any(output_dir.iterdir()):
            raise PreprocessingError(
                f"Output directory is non-empty but not reusable: {output_dir}. Choose a new task output directory."
            )

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    metadata = inspect_video(ffmpeg, video)
    interval = sampling_interval(float(metadata["duration_seconds"]), args.target_fps, args.max_frames)
    paths, timestamps = extract_candidates(
        ffmpeg,
        video,
        frames_dir,
        interval=interval,
        scene_threshold=args.scene_threshold,
        max_frames=args.max_frames - 1,
    )
    paths, timestamps = append_tail_frame(
        ffmpeg,
        video,
        frames_dir,
        paths,
        timestamps,
        duration=float(metadata["duration_seconds"]),
        max_frames=args.max_frames,
    )
    overview_path = output_dir / "timeline-overview.jpg"
    overview_labeled = create_overview(ffmpeg, frames_dir, overview_path, len(paths))

    metadata.update(
        {
            "source_video": str(video),
            "ffmpeg_path": ffmpeg,
            "sampling": {
                "target_fps": args.target_fps,
                "effective_interval_seconds": round(interval, 6),
                "scene_threshold": args.scene_threshold,
                "max_frames": args.max_frames,
                "single_preprocessing_run": True,
            },
            "timeline_overview_has_frame_labels": overview_labeled,
        }
    )
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    frames = []
    for index, (path, timestamp) in enumerate(zip(paths, timestamps), start=1):
        frames.append(
            {
                "frame_id": f"frame_{index:04d}",
                "timestamp_seconds": round(timestamp, 6),
                "file_ref": str(path.relative_to(output_dir)),
                "selection_source": (
                    "video_tail"
                    if index == len(paths) and abs(timestamp - float(metadata["duration_seconds"])) <= 0.05
                    else "uniform_interval_or_scene_change"
                ),
            }
        )
    manifest = {
        "source_video": str(video),
        "frame_count": len(frames),
        "frames": frames,
    }
    manifest_path = output_dir / "frames.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "reused": False,
        "metadata_ref": str(metadata_path),
        "frames_manifest_ref": str(manifest_path),
        "timeline_overview_ref": str(overview_path),
        "frames_dir": str(frames_dir),
        "frame_count": len(frames),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="Source video path")
    parser.add_argument("--output", required=True, help="Empty or reusable task video-analysis directory")
    parser.add_argument("--ffmpeg", help="Explicit FFmpeg executable path")
    parser.add_argument("--target-fps", type=float, default=2.0, help="Requested timeline sampling rate")
    parser.add_argument("--max-frames", type=int, default=40, help="Hard upper bound for candidates")
    parser.add_argument("--scene-threshold", type=float, default=0.35, help="FFmpeg scene-change threshold")
    return parser


def main() -> int:
    try:
        result = preprocess(build_parser().parse_args())
    except (OSError, ValueError, json.JSONDecodeError, PreprocessingError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
