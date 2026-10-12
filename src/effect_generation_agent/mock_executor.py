"""Deterministic mock outputs for exercising the seven-Step runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .workflow import StepContext, StepResult


class MockStepExecutor:
    """Return schema-valid placeholder results without external side effects."""

    def __init__(
        self,
        statuses: Mapping[int, str] | None = None,
        *,
        selected_chain: str = "single_image",
        ready_for_prompting: bool = True,
        route_chain: str | None = None,
    ) -> None:
        self.statuses = dict(statuses or {})
        self.selected_chain = selected_chain
        self.ready_for_prompting = ready_for_prompting
        self.route_chain = route_chain

    def execute(self, context: StepContext) -> StepResult:
        status = self.statuses.get(context.step, "completed")
        if status != "completed":
            issue = {
                "code": f"mock_{status}",
                "message": f"Mock Step {context.step} returned {status}.",
                "severity": "warning" if status in {"needs_input", "blocked"} else "error",
                "step": context.step,
                "recoverable": status in {"needs_input", "blocked"},
                "details": {},
            }
            return StepResult(status=status, output=None, errors=[issue])

        output = self._output(context)
        artifact_updates: dict[str, str | None] = {}
        if context.step == 3:
            artifact_updates["case_snapshot_path"] = output["case_snapshot_ref"]
        if context.step == 7:
            artifact_updates["production_plan_path"] = output["production_plan_ref"]
        return StepResult(
            status="completed",
            output=output,
            artifact_updates=artifact_updates,
        )

    def _output(self, context: StepContext) -> dict[str, Any]:
        task_root = Path(context.artifacts["materials_dir"]).parent.as_posix()
        if context.step == 1:
            return {
                "video_preprocessing": {
                    "metadata_ref": f"{task_root}/video/metadata.json",
                    "frames_manifest_ref": f"{task_root}/video/frames-manifest.json",
                    "timeline_overview_ref": f"{task_root}/video/timeline-overview.json",
                    "frames_dir": f"{task_root}/video/frames",
                },
                "content_summary": "Mock video observation.",
                "visual_style": {},
                "narrative_structure": "single_event",
                "timeline": [
                    {
                        "event_id": "evt_001",
                        "start_seconds": 0,
                        "end_seconds": 1,
                        "observable_facts": ["Mock observable event."],
                        "evidence_frame_ids": ["frame_001"],
                    }
                ],
                "observations": {
                    "subjects": [],
                    "scene": {},
                    "actions": [],
                    "physical_interactions": [],
                    "camera_and_composition": [],
                    "visual_effects": [],
                    "state_changes": [],
                    "observed_text": [],
                    "audio": {},
                },
                "key_frames": [
                    {
                        "frame_id": "frame_001",
                        "file_ref": f"{task_root}/video/frames/frame_001.jpg",
                        "timestamp_seconds": 0,
                        "event_ids": ["evt_001"],
                        "content_description": "Mock frame.",
                        "state_description": "Initial state.",
                        "selection_reason": "Runtime verification fixture.",
                        "keep_for_downstream": True,
                        "downstream_value": "Provides a mock first-frame candidate.",
                        "quality_issues": [],
                    }
                ],
                "screen_recording_artifacts": [],
                "uncertainties": [],
            }
        if context.step == 2:
            selling_point = {
                "description": "Mock selling point.",
                "tags": ["mock_effect"],
                "evidence_event_ids": ["evt_001"],
                "evidence_frame_ids": ["frame_001"],
                "removal_test": "Removing the event removes the mock concept.",
                "confidence": 1,
            }
            return {
                "primary_selling_point": selling_point,
                "secondary_selling_points": [],
                "replication_goal": {
                    "replace": [],
                    "preserve": [
                        {"id": "mock_concept", "description": "Mock concept."}
                    ],
                    "adapt": [],
                    "optional": [],
                },
                "control_signals": {
                    "critical_visual_states": ["initial state"],
                    "continuous_processes": [],
                    "physical_interactions": [],
                    "camera_requirements": [],
                    "text_requirements": [],
                    "audio_requirements": [],
                },
                "alternative_interpretations": [],
                "uncertainties": [],
            }
        if context.step == 3:
            selection_reasons = {
                "single_image": "Mock final video call accepts one image.",
                "reference_video": "Mock final video call accepts a reference video.",
                "multi_image": "Mock final video call requires multiple images.",
                "unsupported": "Mock requirement is outside the current MVP.",
            }
            return {
                "selected_chain": self.selected_chain,
                "control_requirements": {
                    "must_preserve": [
                        {
                            "requirement": "Preserve the mock concept.",
                            "source_refs": ["replication_goal.preserve.mock_concept"],
                        }
                    ],
                    "may_change": [],
                    "temporal_reference_required": self.selected_chain == "reference_video",
                    "required_image_states": 2 if self.selected_chain == "multi_image" else 1,
                    "evidence": [],
                },
                "selection_reason": selection_reasons[self.selected_chain],
                "alternative_chain": None,
                "case_snapshot_ref": f"{task_root}/case-snapshot.json",
                "case_ids": ["mock_case"],
                "risks": [],
            }
        if context.step == 4:
            appearance_strategy = {
                "mode": "preserve_input",
                "reason": "Mock design preserves the runtime appearance.",
                "presentation_sensitive_elements": [],
                "shared_elements": ["action", "camera", "effects"],
            }
            prompt_branching = {
                "required": False,
                "reason": "Mock design has no varying appearance elements.",
                "dimensions": [],
            }
            if self.route_chain == "reference_video":
                return {
                    "nodes": [
                        {
                            "id": "generate_video",
                            "role": "Generate a mock video using a reference video.",
                            "model": "mock-reference-video-model",
                            "model_selection_reason": "Runtime routing verification only.",
                            "inputs": ["reference_video", "subject_image"],
                            "outputs": ["generated_video"],
                            "dependencies": [],
                            "parameters": {},
                            "prompt_routing": None,
                        }
                    ],
                    "runtime_inputs": [
                        {
                            "id": "subject_image",
                            "media_type": "image",
                            "purpose": "Replacement subject supplied when the effect runs.",
                            "required": True,
                            "requirements": {"subject_clear": True},
                        }
                    ],
                    "base_materials": [
                        {
                            "id": "reference_video",
                            "purpose": "Motion and timing reference.",
                            "required": True,
                            "requirements": {},
                        },
                    ],
                    "unresolved_materials": [],
                    "appearance_strategy": appearance_strategy,
                    "prompt_branching": prompt_branching,
                    "risks": [],
                }
            if self.route_chain == "multi_image":
                return {
                    "nodes": [
                        {
                            "id": "generate_video",
                            "role": "Interpolate from the ordered start state to the end state.",
                            "model": "mock-multi-image-video-model",
                            "model_selection_reason": "Runtime routing verification only.",
                            "inputs": ["start_frame", "end_frame"],
                            "outputs": ["generated_video"],
                            "dependencies": [],
                            "parameters": {"input_mode": "first_last_frame"},
                            "prompt_routing": None,
                        }
                    ],
                    "runtime_inputs": [
                        {
                            "id": "start_frame",
                            "media_type": "image",
                            "purpose": "Ordered starting state supplied when the effect runs.",
                            "required": True,
                            "requirements": {"subject_clear": True},
                        },
                        {
                            "id": "end_frame",
                            "media_type": "image",
                            "purpose": "Ordered ending state supplied when the effect runs.",
                            "required": True,
                            "requirements": {"subject_clear": True},
                        },
                    ],
                    "base_materials": [],
                    "unresolved_materials": [],
                    "appearance_strategy": appearance_strategy,
                    "prompt_branching": prompt_branching,
                    "risks": ["Mock multi-image interface requires a real trial."],
                }
            return {
                "nodes": [
                    {
                        "id": "generate_video",
                        "role": "Generate a mock video from one first frame.",
                        "model": "mock-video-model",
                        "model_selection_reason": "Runtime verification only.",
                        "inputs": ["user_image"],
                        "outputs": ["generated_video"],
                        "dependencies": [],
                        "parameters": {},
                        "prompt_routing": None,
                    }
                ],
                "runtime_inputs": [
                    {
                        "id": "user_image",
                        "media_type": "image",
                        "purpose": "Final video image input supplied when the effect runs.",
                        "required": True,
                        "requirements": {"subject_clear": True},
                    }
                ],
                "base_materials": [],
                "unresolved_materials": [],
                "appearance_strategy": appearance_strategy,
                "prompt_branching": prompt_branching,
                "risks": [],
            }
        if context.step == 5:
            base_materials = context.inputs["workflow.step_4.output"]["base_materials"]
            return {
                "materials": [
                    {
                        "id": material["id"],
                        "source": "mock input",
                        "operation": "direct",
                        "purpose": material["purpose"],
                        "path": f"{task_root}/materials/{material['id']}",
                        "status": "ready" if self.ready_for_prompting else "missing",
                        "evidence": [],
                    }
                    for material in base_materials
                ],
                "unresolved_materials": (
                    []
                    if self.ready_for_prompting
                    else [material["id"] for material in base_materials if material["required"]]
                ),
                "ready_for_prompting": self.ready_for_prompting,
            }
        if context.step == 6:
            if self.route_chain == "reference_video":
                return {
                    "node_prompts": [
                        {
                            "node_id": "generate_video",
                            "model": "mock-reference-video-model",
                            "variants": [{
                                "variant_id": "default",
                                "conditions": {},
                                "prompt": "Replace the reference subject while preserving motion and timing.",
                            }],
                        }
                    ],
                    "prompt_audit": [{"node_id": "generate_video", "case_refs": ["mock_case"], "notes": []}],
                    "case_snapshot_ref": f"{task_root}/case-snapshot.json",
                    "coverage_gaps": [],
                    "semantic_validation": {
                        "status": "passed",
                        "review_model": "mock-reviewer",
                        "repair_attempted": False,
                        "checks": {
                            "task_alignment": True,
                            "node_alignment": True,
                            "input_alignment": True,
                            "case_copy_safe": True,
                            "branch_compliance": True,
                        },
                        "issues": [],
                    },
                }
            if self.route_chain == "multi_image":
                return {
                    "node_prompts": [
                        {
                            "node_id": "generate_video",
                            "model": "mock-multi-image-video-model",
                            "variants": [{
                                "variant_id": "default",
                                "conditions": {},
                                "prompt": "Begin at start_frame and transition continuously to end_frame.",
                            }],
                        }
                    ],
                    "prompt_audit": [{"node_id": "generate_video", "case_refs": ["mock_case"], "notes": []}],
                    "case_snapshot_ref": f"{task_root}/case-snapshot.json",
                    "coverage_gaps": [],
                    "semantic_validation": {
                        "status": "passed",
                        "review_model": "mock-reviewer",
                        "repair_attempted": False,
                        "checks": {
                            "task_alignment": True,
                            "node_alignment": True,
                            "input_alignment": True,
                            "case_copy_safe": True,
                            "branch_compliance": True,
                        },
                        "issues": [],
                    },
                }
            return {
                "node_prompts": [
                    {
                        "node_id": "generate_video",
                        "model": "mock-video-model",
                        "variants": [{
                            "variant_id": "default",
                            "conditions": {},
                            "prompt": "Generate a mock video while preserving the subject.",
                        }],
                    }
                ],
                "prompt_audit": [{"node_id": "generate_video", "case_refs": ["mock_case"], "notes": []}],
                "case_snapshot_ref": f"{task_root}/case-snapshot.json",
                "coverage_gaps": [],
                "semantic_validation": {
                    "status": "passed",
                    "review_model": "mock-reviewer",
                    "repair_attempted": False,
                    "checks": {
                        "task_alignment": True,
                        "node_alignment": True,
                        "input_alignment": True,
                        "case_copy_safe": True,
                        "branch_compliance": True,
                    },
                    "issues": [],
                },
            }
        if context.step == 7:
            return {
                "production_plan_ref": f"{task_root}/production-plan.md",
                "deliverables": ["production_plan"],
                "validation": {"schema_valid": True, "mock": True},
                "open_risks": [],
            }
        raise ValueError(f"Unsupported mock Step: {context.step}")


def build_mock_executors(
    statuses: Mapping[int, str] | None = None,
    *,
    selected_chain: str = "single_image",
    ready_for_prompting: bool = True,
) -> dict[int | tuple[int, str], MockStepExecutor]:
    common = MockStepExecutor(
        statuses=statuses,
        selected_chain=selected_chain,
        ready_for_prompting=ready_for_prompting,
    )
    executors: dict[int | tuple[int, str], MockStepExecutor] = {
        step: common for step in (1, 2, 3, 5, 7)
    }
    for chain in ("single_image", "reference_video", "multi_image"):
        routed = MockStepExecutor(
            statuses=statuses,
            selected_chain=selected_chain,
            ready_for_prompting=ready_for_prompting,
            route_chain=chain,
        )
        executors[(4, chain)] = routed
        executors[(6, chain)] = routed
    return executors
