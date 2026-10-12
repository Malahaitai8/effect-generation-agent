"""Deterministic Step 5 material processing and validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .workflow import StepContext, StepResult


DIMENSIONS_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class MaterialProcessingError(RuntimeError):
    pass


class MaterialBlocked(MaterialProcessingError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any]) -> None:
        self.code = code
        self.details = dict(details)
        super().__init__(message)


@dataclass(frozen=True)
class GeneratedMaterial:
    path: Path
    model: str
    evidence: tuple[str, ...]


class MaterialGenerator(Protocol):
    """Generate one fixed material without involving the designer."""

    def generate(
        self,
        *,
        material_id: str,
        purpose: str,
        requirements: Mapping[str, Any],
        source_path: Path | None,
        output_path: Path,
    ) -> GeneratedMaterial: ...


@dataclass(frozen=True)
class MaterialProcessor:
    project_root: Path
    generator: MaterialGenerator | None = None

    def process(
        self,
        requirement: Mapping[str, Any],
        context: StepContext,
    ) -> dict[str, Any]:
        material_id = str(requirement["id"])
        if not SAFE_ID_RE.fullmatch(material_id):
            raise MaterialProcessingError(f"Unsafe material id: {material_id!r}")
        requirements = dict(requirement.get("requirements") or {})
        operation = str(requirements.get("operation", "direct"))
        if operation not in {
            "direct",
            "crop",
            "transform",
            "image_to_image",
            "generate",
        }:
            raise MaterialProcessingError(
                f"Unsupported material operation for {material_id}: {operation}"
            )
        materials_dir = Path(context.inputs["artifacts.materials_dir"]).resolve()
        materials_dir.mkdir(parents=True, exist_ok=True)
        target = dict(requirements.get("target") or {})
        source_spec = dict(requirements.get("source") or {})
        source_path = self._resolve_source(source_spec, context)
        output_path = self._output_path(material_id, target, source_path, materials_dir)
        generated: GeneratedMaterial | None = None

        if operation in {"image_to_image", "generate"}:
            if self.generator is None:
                raise MaterialBlocked(
                    "image_generation_unavailable",
                    f"Automatic image generation is unavailable for material {material_id}",
                    {"material_id": material_id, "expected_output_path": str(output_path)},
                )
            generated = self.generator.generate(
                material_id=material_id,
                purpose=str(requirement.get("purpose", "")),
                requirements=requirements,
                source_path=source_path,
                output_path=output_path,
            )
            if generated.path.resolve() != output_path.resolve():
                raise MaterialProcessingError(
                    f"Generator returned an unexpected output path for {material_id}"
                )
        elif source_path is None or not source_path.is_file():
            raise MaterialBlocked(
                "material_source_missing",
                f"Source material is missing for {material_id}",
                {"material_id": material_id, "source": source_spec},
            )
        elif not output_path.exists():
            if operation == "direct":
                if source_path != output_path:
                    self._copy_atomic(source_path, output_path)
            else:
                self._run_ffmpeg(source_path, output_path, requirements, operation)

        try:
            evidence = self._validate(output_path, target)
        except MaterialProcessingError as error:
            if operation not in {"image_to_image", "generate"}:
                raise
            raise MaterialBlocked(
                "image_generation_invalid",
                f"Generated image is not yet acceptable for {material_id}: {error}",
                {
                    "material_id": material_id,
                    "expected_output_path": str(output_path),
                    "validation_error": str(error),
                },
            ) from error
        if generated is not None:
            evidence.append(f"generator_model:{generated.model}")
            evidence.extend(f"content_evidence:{item}" for item in generated.evidence)
        return {
            "id": material_id,
            "source": str(source_path) if source_path else "automatic_generation",
            "operation": operation,
            "purpose": str(requirement.get("purpose", "")),
            "path": str(output_path),
            "status": "ready",
            "evidence": evidence,
        }

    def _resolve_source(
        self,
        source: Mapping[str, Any],
        context: StepContext,
    ) -> Path | None:
        explicit_path = source.get("path")
        if explicit_path:
            return self._resolve_input_path(str(explicit_path))
        kind = source.get("kind")
        if kind == "source_video":
            return self._resolve_input_path(context.inputs["source"]["video_uri"])
        if kind == "step1_frame":
            frame_id = source.get("frame_id")
            step_1 = context.inputs["workflow.step_1.output"]
            for frame in step_1.get("key_frames", []):
                if frame.get("frame_id") == frame_id:
                    return self._resolve_input_path(frame["file_ref"])
            manifest_path = Path(step_1["video_preprocessing"]["frames_manifest_ref"])
            with manifest_path.open(encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
            analysis_dir = manifest_path.parent
            for frame in manifest.get("frames", []):
                if frame.get("frame_id") == frame_id:
                    return (analysis_dir / frame["file_ref"]).resolve()
            return None
        if kind in {"generated", "business_asset", None}:
            return None
        raise MaterialProcessingError(f"Unsupported material source kind: {kind}")

    def _resolve_input_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    @staticmethod
    def _output_path(
        material_id: str,
        target: Mapping[str, Any],
        source_path: Path | None,
        materials_dir: Path,
    ) -> Path:
        requested_format = str(target.get("format", "")).lstrip(".").lower()
        suffix = f".{requested_format}" if requested_format else ""
        if not suffix and source_path is not None:
            suffix = source_path.suffix.lower()
        if not suffix:
            suffix = ".png"
        output_path = (materials_dir / f"{material_id}{suffix}").resolve()
        try:
            output_path.relative_to(materials_dir)
        except ValueError as error:
            raise MaterialProcessingError("Material output escaped the task directory") from error
        return output_path

    def _run_ffmpeg(
        self,
        source_path: Path,
        output_path: Path,
        requirements: Mapping[str, Any],
        operation: str,
    ) -> None:
        ffmpeg = self._resolve_ffmpeg()
        target = dict(requirements.get("target") or {})
        crop = dict(requirements.get("crop") or {})
        clip = dict(requirements.get("clip") or {})
        timestamp = requirements.get("timestamp_seconds")
        filters: list[str] = []
        if crop:
            filters.append(
                "crop={width}:{height}:{x}:{y}".format(
                    width=int(crop["width"]),
                    height=int(crop["height"]),
                    x=int(crop.get("x", 0)),
                    y=int(crop.get("y", 0)),
                )
            )
        width, height = target.get("width"), target.get("height")
        if width and height:
            if target.get("fit") == "contain":
                filters.append(
                    f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=decrease,"
                    f"pad={int(width)}:{int(height)}:(ow-iw)/2:(oh-ih)/2:color=black"
                )
            else:
                filters.append(f"scale={int(width)}:{int(height)}")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        if timestamp is not None:
            command.extend(["-ss", str(float(timestamp))])
        elif clip.get("start_seconds") is not None:
            command.extend(["-ss", str(float(clip["start_seconds"]))])
        command.extend(["-i", str(source_path)])
        if clip.get("duration_seconds") is not None:
            command.extend(["-t", str(float(clip["duration_seconds"]))])
        if filters:
            command.extend(["-vf", ",".join(filters)])
        if timestamp is not None or target.get("media_type") == "image":
            command.extend(["-frames:v", "1"])
        temporary_path = self._temporary_output(output_path)
        command.append(str(temporary_path))
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            temporary_path.unlink(missing_ok=True)
            raise MaterialProcessingError(
                f"FFmpeg material processing failed: {result.stderr.strip()}"
            )
        os.replace(temporary_path, output_path)

    def _validate(self, path: Path, target: Mapping[str, Any]) -> list[str]:
        if not path.is_file() or path.stat().st_size == 0:
            raise MaterialProcessingError(f"Material output is empty or missing: {path}")
        metadata = self._inspect(path)
        expected_width, expected_height = target.get("width"), target.get("height")
        if expected_width and metadata.get("width") != int(expected_width):
            raise MaterialProcessingError(f"Unexpected material width: {metadata}")
        if expected_height and metadata.get("height") != int(expected_height):
            raise MaterialProcessingError(f"Unexpected material height: {metadata}")
        expected_format = str(target.get("format", "")).lstrip(".").lower()
        if expected_format and path.suffix.lower() != f".{expected_format}":
            raise MaterialProcessingError(f"Unexpected material format: {path.suffix}")
        expected_media_type = target.get("media_type")
        if expected_media_type == "video" and metadata.get("duration_seconds") is None:
            raise MaterialProcessingError(f"Expected video material, got still media: {path}")
        expected_duration = target.get("duration_seconds")
        if expected_duration is not None:
            actual_duration = metadata.get("duration_seconds")
            tolerance = float(target.get("duration_tolerance_seconds", 0.15))
            if actual_duration is None or abs(actual_duration - float(expected_duration)) > tolerance:
                raise MaterialProcessingError(
                    f"Unexpected material duration: expected {expected_duration}, got {actual_duration}"
                )
        evidence = [f"file_exists:{path.stat().st_size}_bytes"]
        if metadata.get("width") and metadata.get("height"):
            evidence.append(f"dimensions:{metadata['width']}x{metadata['height']}")
        if metadata.get("duration_seconds") is not None:
            evidence.append(f"duration_seconds:{metadata['duration_seconds']}")
        return evidence

    def _inspect(self, path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [self._resolve_ffmpeg(), "-hide_banner", "-i", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        dimensions = DIMENSIONS_RE.search(result.stderr)
        duration = DURATION_RE.search(result.stderr)
        metadata: dict[str, Any] = {}
        if dimensions:
            metadata.update(width=int(dimensions.group(1)), height=int(dimensions.group(2)))
        if duration:
            hours, minutes, seconds = duration.groups()
            metadata["duration_seconds"] = round(
                int(hours) * 3600 + int(minutes) * 60 + float(seconds), 6
            )
        return metadata

    @staticmethod
    def _resolve_ffmpeg() -> str:
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError) as error:
            executable = shutil.which("ffmpeg")
            if executable:
                return executable
            raise MaterialProcessingError("FFmpeg is not available") from error

    @staticmethod
    def _copy_atomic(source: Path, output: Path) -> None:
        temporary_path = MaterialProcessor._temporary_output(output)
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, output)

    @staticmethod
    def _temporary_output(output: Path) -> Path:
        descriptor, value = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.stem}.",
            suffix=output.suffix,
        )
        os.close(descriptor)
        temporary_path = Path(value)
        temporary_path.unlink(missing_ok=True)
        return temporary_path

class Step5MaterialExecutor:
    def __init__(self, processor: MaterialProcessor) -> None:
        self.processor = processor

    def execute(self, context: StepContext) -> StepResult:
        requirements = context.inputs["workflow.step_4.output"]["base_materials"]
        materials: list[dict[str, Any]] = []
        missing: list[str] = []
        issues: list[dict[str, Any]] = []
        terminal_status: str | None = None
        for requirement in requirements:
            try:
                materials.append(self.processor.process(requirement, context))
            except MaterialBlocked as error:
                material_id = str(requirement["id"])
                missing.append(material_id)
                materials.append(
                    {
                        "id": material_id,
                        "source": json.dumps(error.details, ensure_ascii=False),
                        "operation": str(
                            requirement.get("requirements", {}).get("operation", "direct")
                        ),
                        "purpose": str(requirement.get("purpose", "")),
                        "path": error.details.get("expected_output_path"),
                        "status": "planned" if error.code.startswith("image_generation_") else "missing",
                        "evidence": [],
                    }
                )
                issues.append(self._issue(context.step, error.code, str(error), error.details))
                if requirement.get("required", False):
                    terminal_status = "blocked"
            except MaterialProcessingError as error:
                material_id = str(requirement["id"])
                missing.append(material_id)
                materials.append(
                    {
                        "id": material_id,
                        "source": "processing_error",
                        "operation": str(
                            requirement.get("requirements", {}).get("operation", "direct")
                        ),
                        "purpose": str(requirement.get("purpose", "")),
                        "path": None,
                        "status": "failed",
                        "evidence": [],
                    }
                )
                issues.append(
                    self._issue(
                        context.step,
                        "material_processing_failed",
                        str(error),
                        {"material_id": material_id},
                    )
                )
                if requirement.get("required", False):
                    terminal_status = "blocked"
        output = {
            "materials": materials,
            "unresolved_materials": missing,
            "ready_for_prompting": terminal_status is None,
        }
        return StepResult(
            status=terminal_status or "completed",
            output=output,
            errors=issues,
        )

    @staticmethod
    def _issue(
        step: int,
        code: str,
        message: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "severity": "warning",
            "step": step,
            "recoverable": True,
            "details": dict(details),
        }
