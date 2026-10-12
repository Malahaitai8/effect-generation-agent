"""Offline evaluation helpers that never influence production Step inputs."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from .model_execution import StructuredModelClient, StructuredModelRequest


class Step12TrialEvaluator:
    """Compare completed Step 1–2 outputs with a human trial baseline."""

    def __init__(
        self,
        client: StructuredModelClient,
        prompt_path: Path,
    ) -> None:
        self.client = client
        self.prompt_path = prompt_path

    def compare(
        self,
        task: Mapping[str, Any],
        baseline_path: Path,
    ) -> Mapping[str, Any]:
        step_1 = task["workflow"]["step_1"]
        step_2 = task["workflow"]["step_2"]
        if step_1["status"] != "completed" or step_2["status"] != "completed":
            raise ValueError("Step 1 and Step 2 must complete before baseline comparison")
        request = StructuredModelRequest(
            task_id=task["task_id"],
            step=2,
            prompt_key="eval.step_1_2",
            prompt=self.prompt_path.read_text(encoding="utf-8"),
            inputs={
                "step_1_output": copy.deepcopy(step_1["output"]),
                "step_2_output": copy.deepcopy(step_2["output"]),
                "human_trial_baseline": baseline_path.read_text(encoding="utf-8"),
                "baseline_path": str(baseline_path),
            },
        )
        result = self.client.generate(request)
        if not isinstance(result, Mapping):
            raise TypeError("Evaluation result must be a JSON object")
        return copy.deepcopy(dict(result))
