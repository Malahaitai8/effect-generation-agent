from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def scaffold_status() -> dict[str, object]:
    required = {
        "implementation_plan": PROJECT_ROOT / "docs" / "IMPLEMENTATION_PLAN.md",
        "skill": PROJECT_ROOT / "skills" / "effect-generation-workflow" / "SKILL.md",
        "model_capabilities": PROJECT_ROOT / "config" / "model-capabilities.json",
        "case_data": PROJECT_ROOT / "rag" / "data" / "cases.jsonl",
        "tests": PROJECT_ROOT / "tests",
        "outputs": PROJECT_ROOT / "outputs",
    }
    return {
        "project": "effect-generation-agent",
        "stage": "scaffold_ready",
        "mvp_chains": ["single_image", "reference_video"],
        "paths": {name: path.exists() for name, path in required.items()},
        "next_step": "固定任务结果 schema",
    }

