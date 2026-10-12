"""Connect the deterministic video extraction script to Step 1 execution."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .model_execution import (
    ModelExecutionBlocked,
    ManualResultRequired,
    StructuredModelClient,
    StructuredModelRequest,
)
from .workflow import StepContext, StepResult


class VideoPreprocessor(Protocol):
    def preprocess(self, video_uri: str, output_dir: Path) -> Mapping[str, Any]:
        """Create or reuse one semantic-free candidate-frame set."""


@dataclass(frozen=True)
class ScriptVideoPreprocessor:
    """Invoke the existing extract-video.py command and parse its JSON result."""

    project_root: Path

    def preprocess(self, video_uri: str, output_dir: Path) -> Mapping[str, Any]:
        source_path = Path(video_uri).expanduser()
        if not source_path.is_absolute():
            source_path = self.project_root / source_path
        script_path = (
            self.project_root
            / "skills"
            / "effect-generation-workflow"
            / "scripts"
            / "extract-video.py"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--video",
                str(source_path.resolve()),
                "--output",
                str(output_dir.resolve()),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ModelExecutionBlocked(f"Video preprocessing failed: {detail}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ModelExecutionBlocked(
                "Video preprocessing did not return valid JSON"
            ) from error
        if payload.get("status") != "completed":
            raise ModelExecutionBlocked(
                f"Video preprocessing did not complete: {payload}"
            )
        return payload


class Step1VideoUnderstandingExecutor:
    """Preprocess once, then ask a media-capable model for Step 1 JSON."""

    def __init__(
        self,
        preprocessor: VideoPreprocessor,
        client: StructuredModelClient,
    ) -> None:
        self.preprocessor = preprocessor
        self.client = client

    def execute(self, context: StepContext) -> StepResult:
        source = context.inputs["source"]
        materials_dir = Path(context.artifacts["materials_dir"])
        analysis_dir = materials_dir.parent / "video-analysis"
        try:
            preprocessing = self.preprocessor.preprocess(
                source["video_uri"],
                analysis_dir,
            )
            request = self._build_request(context, preprocessing, analysis_dir)
            model_output = self.client.generate(request)
        except ManualResultRequired as error:
            return StepResult(
                status="needs_input",
                output=None,
                errors=[
                    {
                        "code": "manual_result_required",
                        "message": str(error),
                        "severity": "info",
                        "step": 1,
                        "recoverable": True,
                        "details": {"request_path": str(error.request_path)},
                    }
                ],
            )
        except ModelExecutionBlocked as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    {
                        "code": "step_1_execution_blocked",
                        "message": str(error),
                        "severity": "warning",
                        "step": 1,
                        "recoverable": True,
                        "details": {},
                    }
                ],
            )
        if not isinstance(model_output, Mapping):
            raise TypeError("Step 1 model output must be a JSON object")
        output = copy.deepcopy(dict(model_output))
        output["video_preprocessing"] = {
            "metadata_ref": preprocessing["metadata_ref"],
            "frames_manifest_ref": preprocessing["frames_manifest_ref"],
            "timeline_overview_ref": preprocessing["timeline_overview_ref"],
            "frames_dir": preprocessing["frames_dir"],
        }
        return StepResult(status="completed", output=output)

    @staticmethod
    def _build_request(
        context: StepContext,
        preprocessing: Mapping[str, Any],
        analysis_dir: Path,
    ) -> StructuredModelRequest:
        try:
            prompt_path = context.resources.prompt_paths["step_1"]
        except KeyError as error:
            raise ModelExecutionBlocked("Step 1 Prompt resource is not configured") from error
        with open(prompt_path, encoding="utf-8") as prompt_file:
            prompt = prompt_file.read()
        manifest_path = Path(preprocessing["frames_manifest_ref"])
        with manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        with Path(preprocessing["metadata_ref"]).open(encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        frame_refs = tuple(
            str((analysis_dir / frame["file_ref"]).resolve())
            for frame in manifest["frames"]
        )
        source = copy.deepcopy(context.inputs["source"])
        prompt_inputs = {
            "source": source,
            "video_preprocessing": {
                "metadata_ref": preprocessing["metadata_ref"],
                "frames_manifest_ref": preprocessing["frames_manifest_ref"],
                "timeline_overview_ref": preprocessing["timeline_overview_ref"],
                "frames_dir": preprocessing["frames_dir"],
                "reused": preprocessing["reused"],
                "frame_count": preprocessing["frame_count"],
            },
        }
        return StructuredModelRequest(
            task_id=context.task_id,
            step=1,
            prompt_key="step_1",
            prompt=prompt,
            inputs=prompt_inputs,
            media_refs=(
                metadata["source_video"],
                preprocessing["timeline_overview_ref"],
                *frame_refs,
            ),
        )
