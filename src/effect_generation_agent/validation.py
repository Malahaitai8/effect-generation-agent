"""JSON Schema loading and task-state validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import TaskValidationError


class TaskValidator:
    """Validate complete task snapshots against one loaded schema version."""

    def __init__(self, schema_path: Path) -> None:
        self.schema_path = schema_path
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        self._validator = Draft202012Validator(
            self.schema,
            format_checker=FormatChecker(),
        )

    @property
    def schema_version(self) -> str:
        version = self.schema.get("properties", {}).get("schema_version", {}).get("const")
        if not isinstance(version, str) or not version:
            raise TaskValidationError("Schema must define properties.schema_version.const")
        return version

    def validate(self, task: dict[str, Any]) -> None:
        errors = sorted(
            self._validator.iter_errors(task),
            key=lambda error: tuple(str(part) for part in error.path),
        )
        if not errors:
            return

        messages = []
        for error in errors[:8]:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            messages.append(f"{location}: {error.message}")
        if len(errors) > len(messages):
            messages.append(f"... and {len(errors) - len(messages)} more validation errors")
        raise TaskValidationError("Task state is invalid: " + "; ".join(messages))
