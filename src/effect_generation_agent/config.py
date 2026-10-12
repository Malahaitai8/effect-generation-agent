"""Small local configuration loader for the CLI runtime."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(project_root: Path) -> dict[str, str]:
    """Load ``.env.local`` without overriding the launching environment.

    The parser intentionally supports only ordinary ``KEY=VALUE`` entries.  It
    never evaluates shell expressions, so secrets remain data rather than code.
    """

    path = project_root.resolve() / ".env.local"
    if not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid .env.local entry on line {line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            raise ValueError(f"Invalid .env.local key on line {line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
