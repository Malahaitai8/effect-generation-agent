"""Deterministic Step 7 validation and production-plan delivery."""

from __future__ import annotations

import json
import itertools
import os
import tempfile
from pathlib import Path
from typing import Any

from .labels import selling_point_tag_labels_zh
from .risks import merge_workflow_risks
from .workflow import StepContext, StepResult


class ProductionPlanExecutor:
    def execute(self, context: StepContext) -> StepResult:
        step_3 = context.inputs["workflow.step_3.output"]
        step_4 = context.inputs["workflow.step_4.output"]
        step_5 = context.inputs["workflow.step_5.output"]
        step_6 = context.inputs["workflow.step_6.output"]
        step_2 = context.inputs["workflow.step_2.output"]
        problems = self._validate(step_2, step_3, step_4, step_5, step_6)
        if problems:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    {
                        "code": "production_plan_incomplete",
                        "message": "Production plan validation failed.",
                        "severity": "warning",
                        "step": 7,
                        "recoverable": True,
                        "details": {"problems": problems},
                    }
                ],
            )
        task_dir = Path(context.artifacts["materials_dir"]).parent
        plan_path = task_dir / "production-plan.md"
        content = self._render(context)
        self._write_atomic(plan_path, content)
        open_risks = merge_workflow_risks(
            step_3.get("risks"), step_4.get("risks"), step_6.get("coverage_gaps")
        )
        output = {
            "production_plan_ref": str(plan_path),
            "deliverables": ["production_plan", "task_result", "materials"],
            "validation": {
                "nodes_valid": True,
                "materials_ready": True,
                "prompts_complete": True,
                "case_references_valid": True,
            },
            "open_risks": open_risks,
        }
        return StepResult(
            status="completed",
            output=output,
            artifact_updates={"production_plan_path": str(plan_path)},
        )

    @staticmethod
    def _validate(
        step_2: dict[str, Any],
        step_3: dict[str, Any],
        step_4: dict[str, Any],
        step_5: dict[str, Any],
        step_6: dict[str, Any],
    ) -> list[str]:
        problems: list[str] = []
        semantic_validation = step_6.get("semantic_validation")
        if not isinstance(semantic_validation, dict) or semantic_validation.get("status") != "passed":
            problems.append("Step 6 semantic validation has not passed")
        elif not all(semantic_validation.get("checks", {}).values()):
            problems.append("Step 6 semantic validation checks are incomplete")
        nodes = step_4["nodes"]
        if step_3.get("selected_chain") == "multi_image":
            final_nodes = [
                node for node in nodes if "generated_video" in node.get("outputs", [])
            ]
            if len(final_nodes) != 1:
                problems.append(
                    "Multi-image design must have exactly one node producing generated_video"
                )
            else:
                final_node = final_nodes[0]
                if len(final_node.get("inputs", [])) != 2:
                    problems.append(
                        "Multi-image final video node must have exactly two ordered image inputs"
                    )
                if final_node.get("parameters", {}).get("input_mode") != "first_last_frame":
                    problems.append(
                        "Multi-image final video node must declare input_mode first_last_frame"
                    )
                runtime_types = {
                    item["id"]: item["media_type"]
                    for item in step_4.get("runtime_inputs", [])
                }
                fixed_types = {
                    item["id"]: item.get("requirements", {})
                    .get("target", {})
                    .get("media_type")
                    for item in step_4.get("base_materials", [])
                }
                video_inputs = [
                    input_id
                    for input_id in final_node.get("inputs", [])
                    if runtime_types.get(input_id) == "video"
                    or fixed_types.get(input_id) == "video"
                ]
                if video_inputs:
                    problems.append(
                        f"Multi-image final node cannot accept video inputs: {video_inputs}"
                    )
            control_requirements = step_3.get("control_requirements", {})
            if control_requirements.get("required_image_states") != 2:
                problems.append(
                    "Multi-image design requires required_image_states to equal 2"
                )
            if control_requirements.get("temporal_reference_required") is not False:
                problems.append(
                    "Multi-image design cannot require a temporal reference video"
                )
        node_id_list = [node["id"] for node in nodes]
        runtime_id_list = [item["id"] for item in step_4["runtime_inputs"]]
        fixed_id_list = [item["id"] for item in step_4["base_materials"]]
        produced_id_list = [output for node in nodes for output in node["outputs"]]
        prompt_node_id_list = [prompt["node_id"] for prompt in step_6["node_prompts"]]
        for label, identifiers in (
            ("node", node_id_list),
            ("runtime input", runtime_id_list),
            ("fixed material", fixed_id_list),
            ("node output", produced_id_list),
            ("Prompt node", prompt_node_id_list),
        ):
            duplicates = sorted(
                identifier for identifier in set(identifiers) if identifiers.count(identifier) > 1
            )
            if duplicates:
                problems.append(f"Duplicate {label} IDs: {duplicates}")
        node_ids = {node["id"] for node in nodes}
        runtime_ids = {item["id"] for item in step_4["runtime_inputs"]}
        fixed_requirement_ids = {item["id"] for item in step_4["base_materials"]}
        produced_ids = {output for node in nodes for output in node["outputs"]}
        duplicate_ids = (
            (runtime_ids & fixed_requirement_ids)
            | (runtime_ids & produced_ids)
            | (fixed_requirement_ids & produced_ids)
        )
        if duplicate_ids:
            problems.append(f"Input and output IDs are not unique: {sorted(duplicate_ids)}")
        materials = {material["id"]: material for material in step_5["materials"]}
        ready_ids = {
            material_id
            for material_id, material in materials.items()
            if material["status"] == "ready"
            and material.get("path")
            and Path(material["path"]).is_file()
        }
        if not step_5.get("ready_for_prompting"):
            problems.append("Step 5 ready_for_prompting is false")
        required_fixed_ids = {
            item["id"] for item in step_4["base_materials"] if item["required"]
        }
        missing_required = required_fixed_ids - ready_ids
        if missing_required:
            problems.append(f"Required fixed materials are not ready: {sorted(missing_required)}")
        unexpected_materials = set(materials) - fixed_requirement_ids
        if unexpected_materials:
            problems.append(
                f"Step 5 contains non-fixed materials: {sorted(unexpected_materials)}"
            )
        for material_id, material in materials.items():
            if material["status"] == "ready" and material_id not in ready_ids:
                problems.append(f"Ready material {material_id} does not exist on disk")
        for node in nodes:
            unknown_dependencies = set(node["dependencies"]) - node_ids
            if unknown_dependencies:
                problems.append(
                    f"Node {node['id']} has unknown dependencies: {sorted(unknown_dependencies)}"
                )
            unknown_inputs = set(node["inputs"]) - runtime_ids - fixed_requirement_ids - produced_ids
            if unknown_inputs:
                problems.append(
                    f"Node {node['id']} has unknown inputs: {sorted(unknown_inputs)}"
                )
            unavailable_fixed = set(node["inputs"]) & (fixed_requirement_ids - ready_ids)
            if unavailable_fixed:
                problems.append(
                    f"Node {node['id']} has unavailable fixed inputs: {sorted(unavailable_fixed)}"
                )
        declared_dimensions = {
            item["id"]: item
            for item in step_4["prompt_branching"]["dimensions"]
        }
        if step_4["prompt_branching"]["required"] != bool(declared_dimensions):
            problems.append(
                "Step 4 prompt_branching.required must match whether dimensions exist"
            )
        if len(declared_dimensions) != len(step_4["prompt_branching"]["dimensions"]):
            problems.append("Duplicate Step 4 branch dimension IDs")
        appearance = step_4["appearance_strategy"]
        sensitive_elements = appearance["presentation_sensitive_elements"]
        expected_presentation_branch = appearance["mode"] == "presentation_specific_redesign"
        if expected_presentation_branch != ("presentation_type" in declared_dimensions):
            problems.append(
                "Step 4 presentation_type branch must match appearance_strategy"
            )
        if appearance["mode"] != "presentation_specific_redesign" and sensitive_elements:
            problems.append(
                "Step 4 appearance strategy can only list sensitive elements for presentation-specific redesign"
            )
        prompts = {prompt["node_id"]: prompt for prompt in step_6["node_prompts"]}
        case_ids = set(step_3.get("case_ids", []))
        audits = {audit["node_id"]: audit for audit in step_6["prompt_audit"]}
        audit_ids = [audit["node_id"] for audit in step_6["prompt_audit"]]
        if len(audits) != len(audit_ids):
            problems.append("Duplicate Prompt audit node IDs")
        for node in nodes:
            if node.get("model") and node["id"] not in prompts:
                problems.append(f"Model node {node['id']} has no Prompt")
        for node_id, prompt in prompts.items():
            if node_id not in node_ids:
                problems.append(f"Prompt references unknown node: {node_id}")
            else:
                node = next(item for item in nodes if item["id"] == node_id)
                if prompt["model"] != node.get("model"):
                    problems.append(f"Prompt {node_id} model does not match its node")
            routing = node.get("prompt_routing") if node_id in node_ids else None
            expected_conditions: set[tuple[tuple[str, str], ...]]
            if routing:
                routed_dimensions: list[tuple[str, list[str]]] = []
                for dimension in routing["dimensions"]:
                    dimension_id = dimension["dimension_id"]
                    declared = declared_dimensions.get(dimension_id)
                    if declared is None:
                        problems.append(
                            f"Node {node_id} routes on undeclared dimension {dimension_id}"
                        )
                        continue
                    if dimension["values"] != declared["values"]:
                        problems.append(
                            f"Node {node_id} values do not match dimension {dimension_id}"
                        )
                    if dimension["source_ref"] not in runtime_ids | produced_ids:
                        problems.append(
                            f"Node {node_id} branch source is unavailable: "
                            f"{dimension['source_ref']}"
                        )
                    routed_dimensions.append((dimension_id, dimension["values"]))
                expected_conditions = {
                    tuple(sorted(zip((item[0] for item in routed_dimensions), values)))
                    for values in itertools.product(*(item[1] for item in routed_dimensions))
                }
            else:
                expected_conditions = {()}
            variants = prompt["variants"]
            actual_conditions = {
                tuple(sorted(variant["conditions"].items())) for variant in variants
            }
            if len(actual_conditions) != len(variants):
                problems.append(f"Prompt {node_id} has duplicate variant conditions")
            if actual_conditions != expected_conditions:
                problems.append(
                    f"Prompt {node_id} variants do not cover exactly the reachable branches"
                )
            variant_ids = [variant["variant_id"] for variant in variants]
            if len(set(variant_ids)) != len(variant_ids):
                problems.append(f"Prompt {node_id} has duplicate variant IDs")
        for node_id, audit in audits.items():
            if node_id not in prompts:
                problems.append(f"Prompt audit references unknown Prompt node: {node_id}")
            if not set(audit["case_refs"]).issubset(case_ids):
                problems.append(f"Prompt audit {node_id} references cases outside Step 3")
        return problems

    @staticmethod
    def _render(context: StepContext) -> str:
        source = context.inputs["source"]
        step_1 = context.inputs["workflow.step_1.output"]
        step_2 = context.inputs["workflow.step_2.output"]
        step_3 = context.inputs["workflow.step_3.output"]
        step_4 = context.inputs["workflow.step_4.output"]
        step_5 = context.inputs["workflow.step_5.output"]
        step_6 = context.inputs["workflow.step_6.output"]
        prompts = {item["node_id"]: item for item in step_6["node_prompts"]}

        primary = step_2["primary_selling_point"]
        display_tags = selling_point_tag_labels_zh(primary.get("tags", []))
        sections = [
            "# 特效生成链路方案",
            "",
            "## 热点视频与核心卖点",
            "",
            f"- **视频**：{source.get('title') or source['video_uri']}",
            f"- **内容摘要**：{step_1['content_summary']}",
            f"- **核心卖点**：{primary['description']}",
            f"- **卖点标签**：{'、'.join(display_tags) or '无'}",
            "",
            "## 链路选择",
            "",
            f"- **类型**：`{step_3['selected_chain']}`",
            f"- **理由**：{step_3['selection_reason']}",
            "",
            "## 运行时输入槽位",
            "",
        ]
        if step_4["runtime_inputs"]:
            sections.extend(["| ID | 媒体类型 | 用途 | 必需 | 要求 |", "|---|---|---|---|---|"])
            for item in step_4["runtime_inputs"]:
                required_label = "是" if item["required"] else "否"
                sections.append(
                    f"| `{item['id']}` | {item['media_type']} | {item['purpose']} | "
                    f"{required_label} | "
                    f"`{json.dumps(item['requirements'], ensure_ascii=False)}` |"
                )
        else:
            sections.append("无。")

        sections.extend(["", "## 固定素材", ""])
        if step_5["materials"]:
            sections.extend(["| ID | 用途 | 处理 | 状态 | 路径 |", "|---|---|---|---|---|"])
            for item in step_5["materials"]:
                sections.append(
                    f"| `{item['id']}` | {item['purpose']} | {item['operation']} | "
                    f"{item['status']} | {item.get('path') or '-'} |"
                )
        else:
            sections.append("无需预先准备的固定素材。")

        sections.extend(["", "## 执行节点", ""])
        for index, node in enumerate(step_4["nodes"], start=1):
            prompt = prompts.get(node["id"])
            sections.extend(
                [
                    f"### {index}. {node['id']}",
                    "",
                    f"- **职责**：{node['role']}",
                    f"- **模型**：{node.get('model') or '无（确定性处理）'}",
                    f"- **模型选择依据**：{node.get('model_selection_reason') or '-'}",
                    f"- **输入**：{', '.join(f'`{item}`' for item in node['inputs']) or '无'}",
                    f"- **输出**：{', '.join(f'`{item}`' for item in node['outputs']) or '无'}",
                    f"- **依赖**：{', '.join(f'`{item}`' for item in node['dependencies']) or '无'}",
                    f"- **参数**：`{json.dumps(node['parameters'], ensure_ascii=False)}`",
                    f"- **Prompt 路由**：`{json.dumps(node.get('prompt_routing'), ensure_ascii=False)}`",
                    "",
                ]
            )
            if prompt is None:
                sections.extend(["**Prompt**：无", ""])
            else:
                for variant in prompt["variants"]:
                    condition_label = (
                        ", ".join(
                            f"{key}={value}"
                            for key, value in variant["conditions"].items()
                        )
                        or "default"
                    )
                    sections.extend(
                        [
                            f"**Prompt 变体：{variant['variant_id']}**",
                            "",
                            f"- **命中条件**：`{condition_label}`",
                            "",
                            "```text",
                            variant["prompt"],
                            "```",
                            "",
                        ]
                    )
                    sections.append("")

        risks = merge_workflow_risks(
            step_3.get("risks"), step_4.get("risks"), step_6.get("coverage_gaps")
        )
        sections.extend(["## 风险与待确认项", ""])
        sections.extend([f"- {risk}" for risk in risks] or ["无。"])
        sections.extend(["", "## 方案依据与审计附录", ""])
        sections.append(
            f"- **链路选择参考案例**：{', '.join(step_3.get('case_ids', [])) or '无'}"
        )
        audits = {item["node_id"]: item for item in step_6["prompt_audit"]}
        for node_id in [node["id"] for node in step_4["nodes"] if node.get("model")]:
            audit = audits.get(node_id, {"case_refs": [], "notes": []})
            sections.append(
                f"- **`{node_id}` Prompt 依据**："
                f"{', '.join(audit['case_refs']) or '无'}"
            )
            sections.extend(f"  - {note}" for note in audit["notes"])
        for material in step_5["materials"]:
            sections.append(
                f"- **`{material['id']}` 素材验证**："
                f"{'; '.join(material.get('evidence', [])) or '无'}"
            )
        sections.append(
            f"- **历史案例覆盖缺口**："
            f"{'; '.join(step_6.get('coverage_gaps', [])) or '无'}"
        )
        sections.append("")
        return "\n".join(sections)

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
