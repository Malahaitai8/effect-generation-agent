"""Step 6 generation, anti-copy checks, semantic review, and one repair."""

from __future__ import annotations

import copy
import difflib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .model_execution import (
    ManualResultRequired,
    ModelExecutionBlocked,
    StructuredModelClient,
    StructuredModelRequest,
    StructuredPromptExecutor,
)
from .workflow import StepContext, StepResult


class Step4ValidatedDesignExecutor:
    """Generate a chain design, independently review its appearance mode, and repair once."""

    def __init__(self, prompt_key: str, client: StructuredModelClient) -> None:
        self.prompt_key = prompt_key
        self.client = client
        self.base_executor = StructuredPromptExecutor(prompt_key, client)

    def execute(self, context: StepContext) -> StepResult:
        try:
            request = self.base_executor.build_request(context)
            candidate = self._generate(request)
            review = self._review(context, request.inputs, candidate)
            review = self._apply_model_input_guard(
                review, candidate, context.resources.model_capabilities
            )
            if review["status"] != "passed":
                candidate = self._repair(
                    context,
                    request.inputs,
                    candidate,
                    review["issues"],
                    review["expected_mode"],
                    review["facts"]["hotspot_visual_anchor_required"],
                )
                review = self._validate_frozen_facts(candidate, review["facts"])
                review = self._apply_model_input_guard(
                    review, candidate, context.resources.model_capabilities
                )
            if review["status"] != "passed":
                raise ModelExecutionBlocked(
                    "Step 4 appearance validation failed after one repair: "
                    + "; ".join(review["issues"])
                )
            return StepResult(status="completed", output=candidate)
        except ModelExecutionBlocked as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[self._issue(context, "appearance_strategy_validation_failed", str(error))],
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[self._issue(context, "appearance_strategy_validation_invalid", f"{type(error).__name__}: {error}")],
            )

    def _generate(self, request: StructuredModelRequest) -> dict[str, Any]:
        output = self.client.generate(request)
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Step 4 generator must return a JSON object")
        return copy.deepcopy(dict(output))

    def _review(
        self,
        context: StepContext,
        runtime_inputs: Mapping[str, Any],
        candidate: Mapping[str, Any],
        frozen_facts: Mapping[str, bool] | None = None,
    ) -> dict[str, Any]:
        output = self.client.generate(
            StructuredModelRequest(
                task_id=context.task_id,
                step=4,
                prompt_key="step_4.appearance_review",
                prompt=Step6ValidatedPromptExecutor._load_prompt(context, "step_4.appearance_review"),
                inputs={
                    "task": Step6ValidatedPromptExecutor._task_facts(runtime_inputs),
                    "generated_step_4_output": copy.deepcopy(dict(candidate)),
                },
                validate_as_step_output=False,
            )
        )
        if frozen_facts is not None:
            output = {**dict(output), "facts": dict(frozen_facts)}
        return self._validate_review(output, candidate)

    @classmethod
    def _validate_frozen_facts(
        cls,
        candidate: Mapping[str, Any],
        facts: Mapping[str, bool],
    ) -> dict[str, Any]:
        return cls._validate_review(
            {
                "status": "passed",
                "facts": dict(facts),
                "checks": {
                    "source_semantics": True,
                    "mode_consistency": True,
                    "branch_consistency": True,
                    "visual_reference_consistency": True,
                },
                "issues": [],
            },
            candidate,
        )

    def _repair(
        self,
        context: StepContext,
        runtime_inputs: Mapping[str, Any],
        candidate: Mapping[str, Any],
        issues: list[str],
        expected_mode: str,
        hotspot_visual_anchor_required: bool,
    ) -> dict[str, Any]:
        output = self.client.generate(
            StructuredModelRequest(
                task_id=context.task_id,
                step=4,
                prompt_key="step_4.appearance_repair",
                prompt=Step6ValidatedPromptExecutor._load_prompt(context, "step_4.appearance_repair"),
                inputs={
                    "task": Step6ValidatedPromptExecutor._task_facts(runtime_inputs),
                    "invalid_step_4_output": copy.deepcopy(dict(candidate)),
                    "validation_issues": issues,
                    "required_appearance_mode": expected_mode,
                    "hotspot_visual_anchor_required": hotspot_visual_anchor_required,
                },
                validate_as_step_output=True,
            )
        )
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Step 4 repair must return a JSON object")
        return copy.deepcopy(dict(output))

    @staticmethod
    def _validate_review(
        output: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Step 4 reviewer must return a JSON object")
        status = output.get("status")
        checks = output.get("checks")
        facts = output.get("facts")
        issues = output.get("issues")
        expected = {
            "source_semantics",
            "mode_consistency",
            "branch_consistency",
            "visual_reference_consistency",
        }
        expected_facts = {
            "explicit_preserve_required",
            "adult_human_presentation",
            "authored_subject_styling",
            "styling_optional",
            "hotspot_visual_anchor_required",
            "usable_step1_frame_available",
        }
        if status not in {"passed", "failed"}:
            raise ModelExecutionBlocked("Step 4 review status must be passed or failed")
        if not isinstance(checks, Mapping) or set(checks) != expected:
            raise ModelExecutionBlocked("Step 4 review checks are incomplete")
        if not isinstance(facts, Mapping) or set(facts) != expected_facts:
            raise ModelExecutionBlocked("Step 4 review facts are incomplete")
        if not all(isinstance(value, bool) for value in facts.values()):
            raise ModelExecutionBlocked("Step 4 review facts must be booleans")
        if not all(isinstance(value, bool) for value in checks.values()):
            raise ModelExecutionBlocked("Step 4 review checks must be booleans")
        if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
            raise ModelExecutionBlocked("Step 4 review issues must be strings")
        expected_mode = "preserve_input"
        if not facts["explicit_preserve_required"] and facts["authored_subject_styling"] and not facts["styling_optional"]:
            expected_mode = (
                "presentation_specific_redesign"
                if facts["adult_human_presentation"]
                else "uniform_redesign"
            )
        actual_mode = candidate.get("appearance_strategy", {}).get("mode")
        declared_dimensions = {
            item.get("id")
            for item in candidate.get("prompt_branching", {}).get("dimensions", [])
            if isinstance(item, Mapping)
        }
        expected_branch = expected_mode == "presentation_specific_redesign"
        formula_issues: list[str] = []
        if actual_mode != expected_mode:
            checks = {**checks, "mode_consistency": False}
            formula_issues.append(
                f"appearance mode must be {expected_mode} from extracted facts, got {actual_mode}"
            )
        if expected_branch != ("presentation_type" in declared_dimensions):
            checks = {**checks, "branch_consistency": False}
            formula_issues.append(
                "presentation_type branch does not match the computed appearance mode"
            )
        if facts["hotspot_visual_anchor_required"] and facts["usable_step1_frame_available"]:
            step1_material_ids = {
                item.get("id")
                for item in candidate.get("base_materials", [])
                if isinstance(item, Mapping)
                and item.get("requirements", {}).get("source", {}).get("kind") == "step1_frame"
            }
            runtime_image_ids = {
                item.get("id")
                for item in candidate.get("runtime_inputs", [])
                if isinstance(item, Mapping) and item.get("media_type") == "image"
            }
            nodes_with_both = [
                node
                for node in candidate.get("nodes", [])
                if isinstance(node, Mapping)
                and set(node.get("inputs", [])) & step1_material_ids
                and set(node.get("inputs", [])) & runtime_image_ids
            ]
            if not step1_material_ids or not nodes_with_both:
                checks = {**checks, "visual_reference_consistency": False}
                formula_issues.append(
                    "a usable Step 1 frame must be a fixed image input to the first-frame node alongside the runtime identity image"
                )
        issues = [*issues, *formula_issues]
        status = "passed" if all(checks.values()) and not issues else "failed"
        if status == "passed" and (issues or not all(checks.values())):
            raise ModelExecutionBlocked("A passed Step 4 review must have all checks true")
        if status == "failed" and not issues:
            raise ModelExecutionBlocked("A failed Step 4 review must explain its issues")
        return {
            "status": status,
            "checks": dict(checks),
            "facts": dict(facts),
            "expected_mode": expected_mode,
            "issues": list(issues),
        }

    def _issue(self, context: StepContext, code: str, message: str) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "severity": "warning",
            "step": context.step,
            "recoverable": True,
            "details": {"prompt_key": self.prompt_key},
        }

    @staticmethod
    def _apply_model_input_guard(
        review: dict[str, Any],
        candidate: Mapping[str, Any],
        capabilities: Mapping[str, Any],
    ) -> dict[str, Any]:
        models = capabilities.get("models", {})
        display_capabilities = {
            value.get("display_name"): value
            for value in models.values()
            if isinstance(value, Mapping)
        }
        runtime_image_ids = {
            item.get("id")
            for item in candidate.get("runtime_inputs", [])
            if isinstance(item, Mapping) and item.get("media_type") == "image"
        }
        fixed_reference_ids = {
            item.get("id")
            for item in candidate.get("base_materials", [])
            if isinstance(item, Mapping)
            and item.get("requirements", {}).get("source", {}).get("kind") == "step1_frame"
        }
        problems: list[str] = []
        for node in candidate.get("nodes", []):
            if not isinstance(node, Mapping):
                continue
            inputs = set(node.get("inputs", []))
            if not (inputs & runtime_image_ids and inputs & fixed_reference_ids):
                continue
            model = node.get("model")
            capability = display_capabilities.get(model)
            if not capability or capability.get("supports_multi_reference_images") is not True:
                problems.append(
                    f"node {node.get('id')} uses identity and hotspot reference images, but model {model!r} is not configured for multiple reference images"
                )
        if not problems:
            return review
        checks = {**review["checks"], "visual_reference_consistency": False}
        return {
            **review,
            "status": "failed",
            "checks": checks,
            "issues": [*review["issues"], *problems],
        }


class Step6ValidatedPromptExecutor:
    """Generate task prompts and commit them only after semantic validation."""

    def __init__(self, prompt_key: str, client: StructuredModelClient) -> None:
        self.prompt_key = prompt_key
        self.client = client
        self.base_executor = StructuredPromptExecutor(prompt_key, client)

    def execute(self, context: StepContext) -> StepResult:
        try:
            base_request = self.base_executor.build_request(context)
            candidate = self._generate(base_request)
            candidate = self._apply_reference_role_preamble(candidate, base_request.inputs)
            issues = self._copy_issues(candidate, base_request.inputs)
            review = self._review(context, base_request.inputs, candidate, issues)
            repair_attempted = bool(issues) or review["status"] != "passed"
            if repair_attempted:
                combined_issues = [*issues, *review["issues"]]
                candidate = self._repair(
                    context, base_request.inputs, candidate, combined_issues
                )
                candidate = self._apply_reference_role_preamble(candidate, base_request.inputs)
                issues = self._copy_issues(candidate, base_request.inputs)
                review = self._review(context, base_request.inputs, candidate, issues)
            if issues or review["status"] != "passed":
                final_issues = [*issues, *review["issues"]]
                raise ModelExecutionBlocked(
                    "Step 6 Prompt semantic validation failed after one repair: "
                    + "; ".join(final_issues or ["unknown semantic mismatch"])
                )
            candidate["semantic_validation"] = {
                "status": "passed",
                "review_model": str(getattr(self.client, "model", "structured-model")),
                "repair_attempted": repair_attempted,
                "checks": review["checks"],
                "issues": [],
            }
            return StepResult(status="completed", output=candidate)
        except ManualResultRequired as error:
            return StepResult(
                status="needs_input",
                output=None,
                errors=[self._issue(context, "manual_result_required", str(error), "info")],
            )
        except ModelExecutionBlocked as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[self._issue(context, "prompt_semantic_validation_failed", str(error))],
            )
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    self._issue(
                        context,
                        "prompt_semantic_validation_invalid",
                        f"{type(error).__name__}: {error}",
                    )
                ],
            )

    def _generate(self, request: StructuredModelRequest) -> dict[str, Any]:
        output = self.client.generate(
            StructuredModelRequest(
                **{
                    **request.__dict__,
                    "validate_as_step_output": False,
                }
            )
        )
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Step 6 generator must return a JSON object")
        candidate = copy.deepcopy(dict(output))
        candidate.pop("semantic_validation", None)
        return candidate

    def _review(
        self,
        context: StepContext,
        runtime_inputs: Mapping[str, Any],
        candidate: Mapping[str, Any],
        deterministic_issues: list[str],
    ) -> dict[str, Any]:
        prompt = self._load_prompt(context, "step_6.semantic_review")
        output = self.client.generate(
            StructuredModelRequest(
                task_id=context.task_id,
                step=6,
                prompt_key="step_6.semantic_review",
                prompt=prompt,
                inputs={
                    "task": self._task_facts(runtime_inputs),
                    "generated_step_6_output": copy.deepcopy(dict(candidate)),
                    "deterministic_issues": deterministic_issues,
                },
                validate_as_step_output=False,
            )
        )
        return self._validate_review(output)

    def _repair(
        self,
        context: StepContext,
        runtime_inputs: Mapping[str, Any],
        candidate: Mapping[str, Any],
        issues: list[str],
    ) -> dict[str, Any]:
        prompt = self._load_prompt(context, "step_6.semantic_repair")
        output = self.client.generate(
            StructuredModelRequest(
                task_id=context.task_id,
                step=6,
                prompt_key="step_6.semantic_repair",
                prompt=prompt,
                inputs={
                    "task": self._task_facts(runtime_inputs),
                    "invalid_step_6_output": copy.deepcopy(dict(candidate)),
                    "validation_issues": issues,
                },
                validate_as_step_output=False,
            )
        )
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Step 6 repair must return a JSON object")
        repaired = copy.deepcopy(dict(output))
        repaired.pop("semantic_validation", None)
        return repaired

    @staticmethod
    def _task_facts(runtime_inputs: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in runtime_inputs.items()
            if key != "_runtime"
        }

    @staticmethod
    def _apply_reference_role_preamble(
        candidate: Mapping[str, Any], runtime_inputs: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(candidate))
        step_4 = runtime_inputs.get("workflow.step_4.output", {})
        runtime_images = {
            item.get("id"): item
            for item in step_4.get("runtime_inputs", [])
            if isinstance(item, Mapping) and item.get("media_type") == "image"
        }
        fixed_references = {
            item.get("id"): item
            for item in step_4.get("base_materials", [])
            if isinstance(item, Mapping)
            and item.get("requirements", {}).get("source", {}).get("kind") == "step1_frame"
        }
        nodes = {
            node.get("id"): node
            for node in step_4.get("nodes", [])
            if isinstance(node, Mapping)
        }
        prompts = {
            prompt.get("node_id"): prompt
            for prompt in result.get("node_prompts", [])
            if isinstance(prompt, Mapping)
        }
        for node_id, node in nodes.items():
            inputs = set(node.get("inputs", []))
            identity_ids = sorted(inputs & set(runtime_images))
            reference_ids = sorted(inputs & set(fixed_references))
            node_prompt = prompts.get(node_id)
            if not identity_ids or not reference_ids or not node_prompt:
                continue
            identity_text = "、".join(identity_ids)
            reference_text = "、".join(reference_ids)
            preamble = (
                f"输入图职责：{identity_text} 是目标主体身份的唯一来源；"
                f"{reference_text} 只提供热点场景、构图、姿态、景别、道具和空间关系参考。"
                "用目标主体替换热点参考图中的原主体，最终画面只保留一个目标主体，不得混合身份或生成双主体。"
            )
            for variant in node_prompt.get("variants", []):
                prompt_text = variant.get("prompt")
                if isinstance(prompt_text, str) and not prompt_text.startswith("输入图职责："):
                    variant["prompt"] = preamble + "\n" + prompt_text
        return result

    @staticmethod
    def _validate_review(output: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(output, Mapping):
            raise ModelExecutionBlocked("Semantic reviewer must return a JSON object")
        status = output.get("status")
        checks = output.get("checks")
        issues = output.get("issues")
        expected_checks = {
            "task_alignment",
            "node_alignment",
            "input_alignment",
            "case_copy_safe",
            "branch_compliance",
        }
        if status not in {"passed", "failed"}:
            raise ModelExecutionBlocked("Semantic review status must be passed or failed")
        if not isinstance(checks, Mapping) or set(checks) != expected_checks:
            raise ModelExecutionBlocked("Semantic review checks are incomplete")
        if not all(isinstance(value, bool) for value in checks.values()):
            raise ModelExecutionBlocked("Semantic review checks must be booleans")
        if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
            raise ModelExecutionBlocked("Semantic review issues must be strings")
        if status == "passed" and (issues or not all(checks.values())):
            raise ModelExecutionBlocked("A passed semantic review must have all checks true")
        if status == "failed" and not issues:
            raise ModelExecutionBlocked("A failed semantic review must explain its issues")
        return {"status": status, "checks": dict(checks), "issues": list(issues)}

    @classmethod
    def _copy_issues(
        cls, candidate: Mapping[str, Any], runtime_inputs: Mapping[str, Any]
    ) -> list[str]:
        generated = cls._generated_prompts(candidate)
        historical = cls._historical_prompts(runtime_inputs)
        issues: list[str] = []
        for node_id, variant_id, prompt in generated:
            normalized_prompt = cls._normalize(prompt)
            for case_id, historical_prompt in historical:
                normalized_case = cls._normalize(historical_prompt)
                if min(len(normalized_prompt), len(normalized_case)) < 120:
                    continue
                matcher = difflib.SequenceMatcher(None, normalized_prompt, normalized_case)
                match = matcher.find_longest_match(
                    0, len(normalized_prompt), 0, len(normalized_case)
                )
                shorter = min(len(normalized_prompt), len(normalized_case))
                if matcher.ratio() >= 0.72 or (
                    match.size >= 240 and match.size / shorter >= 0.45
                ):
                    issues.append(
                        f"Prompt {node_id}/{variant_id} copies too much text from case {case_id}"
                    )
                    break
        for audit in candidate.get("prompt_audit", []):
            for note in audit.get("notes", []):
                normalized_note = str(note).lower()
                denied_reuse = any(
                    phrase in normalized_note
                    for phrase in ("未直接复用", "没有直接复用", "不直接复用", "不得直接复用")
                )
                denied_reuse = denied_reuse or any(
                    phrase in normalized_note
                    for phrase in ("did not directly reuse", "do not directly reuse", "must not directly reuse")
                )
                if not denied_reuse and ("直接复用" in normalized_note or "directly reuse" in normalized_note):
                    issues.append(
                        f"Prompt audit {audit.get('node_id')} claims direct case Prompt reuse"
                    )
        return issues

    @staticmethod
    def _generated_prompts(candidate: Mapping[str, Any]) -> list[tuple[str, str, str]]:
        values: list[tuple[str, str, str]] = []
        for node_prompt in candidate.get("node_prompts", []):
            for variant in node_prompt.get("variants", []):
                text = variant.get("prompt")
                if isinstance(text, str):
                    values.append(
                        (
                            str(node_prompt.get("node_id", "unknown")),
                            str(variant.get("variant_id", "unknown")),
                            text,
                        )
                    )
        return values

    @staticmethod
    def _historical_prompts(runtime_inputs: Mapping[str, Any]) -> list[tuple[str, str]]:
        snapshot = runtime_inputs.get("_runtime", {}).get("case_snapshot")
        if not isinstance(snapshot, Mapping):
            return []
        cases: list[Mapping[str, Any]] = []
        for candidate in snapshot.get("candidates", []):
            if isinstance(candidate, Mapping) and isinstance(candidate.get("case"), Mapping):
                cases.append(candidate["case"])
        cases.extend(case for case in snapshot.get("cases", []) if isinstance(case, Mapping))
        values: list[tuple[str, str]] = []
        for case in cases:
            case_id = str(case.get("case_id", "unknown"))
            for node in case.get("nodes", []):
                if not isinstance(node, Mapping):
                    continue
                for prompt in node.get("prompts", []):
                    if isinstance(prompt, Mapping) and isinstance(prompt.get("text"), str):
                        values.append((case_id, prompt["text"]))
        return values

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())

    @staticmethod
    def _load_prompt(context: StepContext, key: str) -> str:
        path = context.resources.prompt_paths.get(key)
        if not path:
            raise ModelExecutionBlocked(f"Prompt resource is not configured: {key}")
        return Path(path).read_text(encoding="utf-8")

    def _issue(
        self,
        context: StepContext,
        code: str,
        message: str,
        severity: str = "warning",
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "severity": severity,
            "step": context.step,
            "recoverable": True,
            "details": {"prompt_key": self.prompt_key},
        }
