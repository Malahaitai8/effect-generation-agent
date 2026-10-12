"""Step 3 orchestration: retrieve cases, then select the execution route."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from .model_execution import (
    ManualResultRequired,
    ModelExecutionBlocked,
    StructuredModelClient,
    StructuredModelRequest,
)
from .retrieval import CaseRetriever
from .workflow import StepContext, StepResult


class Step3RetrievalSelectionExecutor:
    def __init__(self, retriever: CaseRetriever, client: StructuredModelClient) -> None:
        self.retriever = retriever
        self.client = client

    def execute(self, context: StepContext) -> StepResult:
        try:
            step_1 = context.inputs["workflow.step_1.output"]
            step_2 = context.inputs["workflow.step_2.output"]
            materials_dir = context.artifacts.get("materials_dir")
            if not materials_dir:
                raise ModelExecutionBlocked("Task materials directory is unavailable")
            snapshot_path = Path(materials_dir).resolve().parent / "case-snapshot.json"
            snapshot = self.retriever.retrieve(step_2, snapshot_path)
            prompt_path = context.resources.prompt_paths.get("step_3_selection")
            if not prompt_path:
                raise ModelExecutionBlocked("Step 3 selection prompt is not configured")
            prompt = Path(prompt_path).read_text(encoding="utf-8")
            output = dict(
                self.client.generate(
                    StructuredModelRequest(
                        task_id=context.task_id,
                        step=3,
                        prompt_key="step_3_selection",
                        prompt=prompt,
                        inputs={
                            "workflow.step_1.output": copy.deepcopy(step_1),
                            "workflow.step_2.output": copy.deepcopy(step_2),
                            "step_3a.case_snapshot": copy.deepcopy(snapshot),
                        },
                    )
                )
            )
            self._validate_and_normalize_selection(output, snapshot, step_2)
            output["case_snapshot_ref"] = str(snapshot_path)
            return StepResult(
                status="completed",
                output=output,
                artifact_updates={"case_snapshot_path": str(snapshot_path)},
            )
        except ManualResultRequired as error:
            return StepResult(
                status="needs_input",
                output=None,
                errors=[
                    {
                        "code": "manual_result_required",
                        "message": str(error),
                        "severity": "info",
                        "step": 3,
                        "recoverable": True,
                        "details": {},
                    }
                ],
            )
        except ModelExecutionBlocked as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    {
                        "code": "step_3_blocked",
                        "message": str(error),
                        "severity": "warning",
                        "step": 3,
                        "recoverable": True,
                        "details": {},
                    }
                ],
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    {
                        "code": "step_3_invalid_data",
                        "message": f"{type(error).__name__}: {error}",
                        "severity": "warning",
                        "step": 3,
                        "recoverable": True,
                        "details": {},
                    }
                ],
            )

    @staticmethod
    def _validate_and_normalize_selection(
        output: dict[str, Any],
        snapshot: Mapping[str, Any],
        step_2: Mapping[str, Any],
    ) -> None:
        selected_chain = output.get("selected_chain")
        if selected_chain not in {
            "single_image",
            "reference_video",
            "multi_image",
            "unsupported",
        }:
            raise ModelExecutionBlocked(f"Invalid selected_chain: {selected_chain}")
        candidates = snapshot.get("candidates")
        if not isinstance(candidates, list):
            raise ModelExecutionBlocked("Case snapshot has no candidates")
        expected = [
            item["case_id"]
            for item in candidates
            if selected_chain in {"single_image", "reference_video", "multi_image"}
            and item.get("case", {}).get("route_type") == selected_chain
        ]
        supplied = output.get("case_ids")
        if not isinstance(supplied, list) or set(supplied) != set(expected):
            raise ModelExecutionBlocked(
                "Step 3 case_ids must equal the Top 6 candidates matching selected_chain"
            )
        output["case_ids"] = expected
        Step3RetrievalSelectionExecutor._validate_preserve_sources(output, step_2)

    @staticmethod
    def _validate_preserve_sources(
        output: Mapping[str, Any], step_2: Mapping[str, Any]
    ) -> None:
        """Prevent Step 3 from promoting replace/adapt facts into hard constraints."""

        replication_goal = step_2.get("replication_goal")
        control_signals = step_2.get("control_signals")
        if not isinstance(replication_goal, Mapping) or not isinstance(control_signals, Mapping):
            raise ModelExecutionBlocked("Step 2 replication goals or control signals are invalid")

        constraint_owners: dict[str, str] = {}
        for policy in ("replace", "preserve", "adapt", "optional"):
            constraints = replication_goal.get(policy)
            if not isinstance(constraints, list):
                raise ModelExecutionBlocked(f"Step 2 replication_goal.{policy} must be an array")
            for constraint in constraints:
                if not isinstance(constraint, Mapping) or not isinstance(constraint.get("id"), str):
                    raise ModelExecutionBlocked(
                        f"Step 2 replication_goal.{policy} contains a constraint without an id"
                    )
                constraint_id = constraint["id"]
                if constraint_id in constraint_owners:
                    raise ModelExecutionBlocked(
                        f"Duplicate Step 2 replication constraint id: {constraint_id}"
                    )
                constraint_owners[constraint_id] = policy

        requirements = output.get("control_requirements")
        if not isinstance(requirements, Mapping):
            raise ModelExecutionBlocked("Step 3 control_requirements must be an object")
        must_preserve = requirements.get("must_preserve")
        if not isinstance(must_preserve, list):
            raise ModelExecutionBlocked("Step 3 must_preserve must be an array")

        for item in must_preserve:
            if not isinstance(item, Mapping) or not isinstance(item.get("source_refs"), list):
                raise ModelExecutionBlocked(
                    "Each Step 3 must_preserve item must include source_refs"
                )
            for source_ref in item["source_refs"]:
                if not isinstance(source_ref, str):
                    raise ModelExecutionBlocked("Step 3 source_refs must contain strings")
                preserve_prefix = "replication_goal.preserve."
                if source_ref.startswith(preserve_prefix):
                    constraint_id = source_ref[len(preserve_prefix) :]
                    owner = constraint_owners.get(constraint_id)
                    if owner != "preserve":
                        actual = owner or "missing"
                        raise ModelExecutionBlocked(
                            f"Step 3 cannot preserve {constraint_id!r}; Step 2 policy is {actual}"
                        )
                    continue
                if source_ref.startswith("control_signals."):
                    parts = source_ref.split(".")
                    if len(parts) != 3 or not parts[2].isdigit():
                        raise ModelExecutionBlocked(
                            f"Invalid control signal source reference: {source_ref}"
                        )
                    values = control_signals.get(parts[1])
                    index = int(parts[2])
                    if not isinstance(values, list) or index >= len(values):
                        raise ModelExecutionBlocked(
                            f"Control signal source reference does not exist: {source_ref}"
                        )
                    continue
                raise ModelExecutionBlocked(
                    "Step 3 must_preserve source_refs may only reference "
                    "replication_goal.preserve.<id> or control_signals.<field>.<index>"
                )
