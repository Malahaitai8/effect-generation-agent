"""Explicit task-state migrations between incompatible schema versions."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import TaskValidationError
from .validation import TaskValidator


def migrate_task_040_to_050(
    task_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    """Migrate one persisted v0.4 task without silently accepting mixed contracts."""

    try:
        original = json.loads(task_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TaskValidationError(f"Cannot read task state {task_path}: {error}") from error
    if original.get("schema_version") != "0.4.0":
        raise TaskValidationError(
            f"Migration requires schema_version 0.4.0, got {original.get('schema_version')!r}"
        )

    task = copy.deepcopy(original)
    task["schema_version"] = "0.9.0"
    workflow = task["workflow"]

    step_2 = workflow["step_2"].get("output")
    legacy_branching = {
        "required": False,
        "reason": "Legacy task did not declare Prompt branching.",
        "dimensions": [],
    }
    legacy_appearance = {
        "mode": "preserve_input",
        "reason": "Legacy task did not declare appearance redesign.",
        "presentation_sensitive_elements": [],
        "shared_elements": [],
    }
    if step_2 is not None:
        for policy in ("replace", "preserve", "adapt", "optional"):
            step_2["replication_goal"][policy] = [
                {"id": f"legacy_{policy}_{index + 1}", "description": description}
                for index, description in enumerate(step_2["replication_goal"][policy])
            ]
        legacy_branching = step_2.pop("prompt_branching", legacy_branching)
        presentation_dimensions = [
            item for item in legacy_branching.get("dimensions", [])
            if item.get("id") == "presentation_type"
        ]
        legacy_appearance = {
            "mode": ("presentation_specific_redesign" if presentation_dimensions else "preserve_input"),
            "reason": "Migrated from the legacy presentation branch declaration.",
            "presentation_sensitive_elements": (["legacy presentation design"] if presentation_dimensions else []),
            "shared_elements": [],
        }

    step_3 = workflow["step_3"].get("output")
    if step_3 is not None:
        requirements = step_3["control_requirements"]
        preserve_constraints = step_2["replication_goal"]["preserve"] if step_2 else []
        migrated_requirements = []
        for index, requirement in enumerate(requirements.get("must_preserve", [])):
            if index < len(preserve_constraints):
                constraint = preserve_constraints[index]
            else:
                constraint = {
                    "id": f"legacy_preserve_{len(preserve_constraints) + 1}",
                    "description": requirement,
                }
                preserve_constraints.append(constraint)
            migrated_requirements.append(
                {
                    "requirement": requirement,
                    "source_refs": [f"replication_goal.preserve.{constraint['id']}"],
                }
            )
        requirements["must_preserve"] = migrated_requirements
    for step_name in ("step_4", "step_5"):
        output = workflow[step_name].get("output")
        if output is not None:
            output["unresolved_materials"] = output.pop("missing_materials", [])
            if step_name == "step_4":
                output["appearance_strategy"] = legacy_appearance
                output["prompt_branching"] = legacy_branching
            if step_name == "step_5":
                for material in output["materials"]:
                    if material.get("operation") == "user_provided":
                        material["operation"] = "direct"

    step_6 = workflow["step_6"].get("output")
    if step_6 is not None:
        audits: list[dict[str, Any]] = []
        for node_prompt in step_6["node_prompts"]:
            case_refs: list[str] = []
            notes: list[str] = []
            for variant in node_prompt["variants"]:
                variant.pop("negative_prompt", None)
                for case_id in variant.pop("case_refs", []):
                    if case_id not in case_refs:
                        case_refs.append(case_id)
                variant.pop("material_refs", None)
                constraints = variant.pop("constraints", [])
                if constraints:
                    variant["prompt"] += "\n\nRequirements:\n" + "\n".join(
                        f"- {constraint}" for constraint in constraints
                    )
                    notes.append(
                        f"Migrated legacy constraints into variant {variant['variant_id']} Prompt."
                    )
            audits.append(
                {"node_id": node_prompt["node_id"], "case_refs": case_refs, "notes": notes}
            )
        step_6["prompt_audit"] = audits

        # Legacy Prompt output has never passed the v0.7 semantic review.
        # Do not fabricate a successful review; resume safely from Step 6.
        workflow["step_6"].update(
            {
                "status": "pending",
                "attempt": 0,
                "started_at": None,
                "completed_at": None,
                "output": None,
                "errors": [],
            }
        )
        workflow["step_7"].update(
            {
                "status": "pending",
                "attempt": 0,
                "started_at": None,
                "completed_at": None,
                "output": None,
                "errors": [],
            }
        )
        task["status"] = "initialized"
        task["current_step"] = 6
        task["artifacts"]["production_plan_path"] = None

    TaskValidator(schema_path).validate(task)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=task_path.parent,
            prefix=f".{task_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(task, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, task_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return task
