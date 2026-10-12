"""Build read-only resources used by real or deterministic Step executors."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .workflow import RuntimeResources


PROMPT_FILES = {
    "step_1": "vlm-observation.md",
    "step_2": "selling-point.md",
    "step_3_retrieval": "case-retrieval.md",
    "step_3_selection": "chain-selection.md",
    "step_4.single_image": "chain-single-image-design.md",
    "step_4.reference_video": "chain-reference-video-design.md",
    "step_4.multi_image": "chain-multi-image.md",
    "step_4.appearance_review": "chain-appearance-review.md",
    "step_4.appearance_repair": "chain-appearance-repair.md",
    "step_5": "material-preparation.md",
    "step_6.single_image": "chain-single-image-prompt.md",
    "step_6.reference_video": "chain-reference-video-prompt.md",
    "step_6.multi_image": "chain-multi-image-prompt.md",
    "step_6.semantic_review": "prompt-semantic-review.md",
    "step_6.semantic_repair": "prompt-semantic-repair.md",
}


class JsonCaseSnapshotReader:
    """Read snapshots only from configured project or task-output roots."""

    def __init__(self, project_root: Path, outputs_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.allowed_roots = (self.project_root, outputs_root.resolve())

    def read(self, reference: str) -> Mapping[str, Any]:
        path = Path(reference)
        if not path.is_absolute():
            path = self.project_root / path
        resolved = path.resolve()
        if not any(_is_relative_to(resolved, root) for root in self.allowed_roots):
            raise ValueError(f"Case snapshot is outside the configured roots: {reference}")
        with resolved.open(encoding="utf-8") as snapshot_file:
            value = json.load(snapshot_file)
        if not isinstance(value, dict):
            raise ValueError(f"Case snapshot must be a JSON object: {reference}")
        return MappingProxyType(value)


def load_runtime_resources(
    project_root: Path,
    outputs_root: Path | None = None,
) -> RuntimeResources:
    """Load canonical prompt paths and model capabilities for executor injection."""

    root = project_root.resolve()
    prompt_root = root / "skills" / "effect-generation-workflow" / "prompts"
    prompt_paths = MappingProxyType(
        {
            **{
                key: str(prompt_root / filename)
                for key, filename in PROMPT_FILES.items()
            },
            "eval.step_1_2": str(root / "evals" / "step1-step2-comparison.md"),
        }
    )
    capabilities_path = root / "config" / "model-capabilities.json"
    with capabilities_path.open(encoding="utf-8") as capabilities_file:
        capabilities = json.load(capabilities_file)
    if not isinstance(capabilities, dict):
        raise ValueError("Model capabilities must be a JSON object")
    return RuntimeResources(
        prompt_paths=prompt_paths,
        model_capabilities=MappingProxyType(capabilities),
        case_snapshot_reader=JsonCaseSnapshotReader(
            root,
            outputs_root or root / "outputs",
        ),
        adapters=MappingProxyType({}),
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
