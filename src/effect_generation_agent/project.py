from __future__ import annotations

import os
from pathlib import Path


def find_project_root() -> Path:
    """Find the checkout that owns schemas, skills, and task outputs."""

    configured = os.environ.get("EFFECT_AGENT_PROJECT_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([Path.cwd(), Path(__file__).resolve().parents[2]])
    for candidate in candidates:
        for path in (candidate.resolve(), *candidate.resolve().parents):
            if (path / "schemas" / "task-result.schema.json").exists():
                return path
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = find_project_root()


def scaffold_status() -> dict[str, object]:
    required = {
        "development_guide": PROJECT_ROOT / "docs" / "DEVELOPMENT_GUIDE.md",
        "skill": PROJECT_ROOT / "skills" / "effect-generation-workflow" / "SKILL.md",
        "model_capabilities": PROJECT_ROOT / "config" / "model-capabilities.json",
        "case_data": PROJECT_ROOT / "rag" / "data" / "cases.jsonl",
        "task_store": PROJECT_ROOT / "src" / "effect_generation_agent" / "store.py",
        "workflow_engine": PROJECT_ROOT / "src" / "effect_generation_agent" / "workflow.py",
        "tests": PROJECT_ROOT / "tests",
        "outputs": PROJECT_ROOT / "outputs",
    }
    return {
        "project": "effect-generation-agent",
        "stage": "manual_model_exchange_and_material_mvp_ready",
        "mvp_chains": ["single_image", "reference_video"],
        "paths": {name: path.exists() for name, path in required.items()},
        "next_step": "接入 Step 3/RAG 执行器并用真实 case 跑通人工闭环",
    }
