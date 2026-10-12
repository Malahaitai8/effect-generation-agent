"""Business workspace layered on top of immutable Agent task results."""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from .risks import canonicalize_risks, merge_workflow_risks


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
BUSINESS_STATUSES = {
    "pending", "analyzing", "needs_input", "pending_review", "editing",
    "deliverable", "completed", "failed", "unsupported",
}


class WorkbenchError(RuntimeError):
    pass


class RevisionConflict(WorkbenchError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def agent_status_to_business(task: dict[str, Any], review_status: str | None = None) -> str:
    if review_status in {"editing", "deliverable", "completed"}:
        return review_status
    status = task.get("status", "initialized")
    if status == "completed":
        route = ((task.get("workflow", {}).get("step_3", {}).get("output") or {})
                 .get("selected_chain"))
        return "unsupported" if route == "unsupported" else "pending_review"
    return {
        "initialized": "pending", "running": "analyzing", "needs_input": "needs_input",
        "blocked": "unsupported", "failed": "failed",
    }.get(status, "pending")


class WorkbenchStore:
    """Persists collaboration metadata without mutating task-result.json."""

    def __init__(self, outputs_root: Path) -> None:
        self.outputs_root = outputs_root.resolve()
        self.root = self.outputs_root / ".workbench"
        self.batches_root = self.root / "batches"
        self.items_root = self.root / "items"
        self.exports_root = self.root / "exports"
        for path in (self.batches_root, self.items_root, self.exports_root):
            path.mkdir(parents=True, exist_ok=True)

    def create_batch(self, metadata: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
        batch_id = str(metadata.get("batch_id") or f"batch-{uuid.uuid4().hex[:10]}")
        self._validate_id(batch_id)
        if not tasks:
            raise WorkbenchError("批次至少需要一条视频")
        batch_path = self.batches_root / f"{batch_id}.json"
        if batch_path.exists():
            raise WorkbenchError(f"批次已存在：{batch_id}")
        task_ids: list[str] = []
        for index, definition in enumerate(tasks, 1):
            task_id = str(definition.get("task_id") or f"task-{uuid.uuid4().hex[:12]}")
            self._validate_id(task_id)
            if task_id in task_ids or self._item_path(task_id).exists():
                raise WorkbenchError(f"任务 ID 重复：{task_id}")
            task_ids.append(task_id)
            item = {
                "task_id": task_id, "batch_id": batch_id, "version": 1,
                "assignee": definition.get("assignee"),
                "priority": definition.get("priority", "normal"),
                "deadline": definition.get("deadline"),
                "source_url": definition.get("source_url"),
                "notes": definition.get("notes", ""),
                "review_status": None, "revision_count": 0,
                "created_at": utc_now(), "updated_at": utc_now(),
            }
            self._write_json(self._item_path(task_id), item)
        now = utc_now()
        batch = {
            "batch_id": batch_id, "name": metadata.get("name") or batch_id,
            "source": metadata.get("source", ""), "campaign": metadata.get("campaign", ""),
            "creator": metadata.get("creator", ""), "task_ids": task_ids,
            "created_at": now, "updated_at": now,
        }
        self._write_json(batch_path, batch)
        return self.get_batch(batch_id)

    def list_batches(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted(self.batches_root.glob("*.json"), reverse=True):
            batch = self._read_json(path)
            result.append(self._decorate_batch(batch))
        return result

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        self._validate_id(batch_id)
        path = self.batches_root / f"{batch_id}.json"
        if not path.exists():
            raise WorkbenchError(f"批次不存在：{batch_id}")
        return self._decorate_batch(self._read_json(path))

    def get_work_item(self, task_id: str) -> dict[str, Any]:
        item = self._read_item(task_id)
        batch = self.get_batch(item["batch_id"])
        task = self._load_task(task_id)
        revision = self._latest_revision(task_id)
        plan = copy.deepcopy(revision.get("plan")) if revision else self._plan_from_task(task)
        plan["risks"] = canonicalize_risks(plan.get("risks"))
        validation = validate_plan(plan)
        return {
            **item, "business_status": agent_status_to_business(task, item.get("review_status")),
            "uploader": batch.get("creator", ""), "uploaded_at": item.get("created_at"),
            "agent_task": task, "plan": plan, "validation": validation,
            "revisions": self.list_revisions(task_id),
        }

    def update_assignment(self, task_id: str, changes: dict[str, Any], expected_version: int) -> dict[str, Any]:
        item = self._read_item(task_id)
        if item["version"] != expected_version:
            raise RevisionConflict("任务已被其他人更新，请刷新后重试")
        for key in ("assignee", "priority", "deadline", "notes"):
            if key in changes:
                item[key] = changes[key]
        item["version"] += 1
        item["updated_at"] = utc_now()
        self._write_json(self._item_path(task_id), item)
        return item

    def save_revision(
        self, task_id: str, plan: dict[str, Any], *, actor: str, reason: str,
        expected_version: int,
    ) -> dict[str, Any]:
        item = self._read_item(task_id)
        if item["version"] != expected_version:
            raise RevisionConflict("方案已被其他人修改，请刷新后合并")
        plan = copy.deepcopy(plan)
        plan["risks"] = canonicalize_risks(plan.get("risks"))
        issues = validate_plan(plan)
        revision_id = f"rev-{item['revision_count'] + 1:04d}"
        revision = {
            "revision_id": revision_id, "task_id": task_id, "actor": actor,
            "reason": reason, "base_version": expected_version, "created_at": utc_now(),
            "plan": copy.deepcopy(plan), "validation": issues,
        }
        revision_dir = self.items_root / task_id / "revisions"
        self._write_json(revision_dir / f"{revision_id}.json", revision)
        item["revision_count"] += 1
        item["version"] += 1
        item["review_status"] = "editing"
        item["updated_at"] = utc_now()
        self._write_json(self._item_path(task_id), item)
        return {"item": item, "revision": revision}

    def submit_review(self, task_id: str, expected_version: int) -> dict[str, Any]:
        return self._set_review_status(task_id, expected_version, "deliverable", require_valid=True)

    def confirm_delivery(self, task_id: str, expected_version: int, actor: str) -> dict[str, Any]:
        item = self._set_review_status(task_id, expected_version, "completed", require_valid=True)
        work = self.get_work_item(task_id)
        version_id = f"delivery-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        delivery_dir = self.items_root / task_id / "deliveries" / version_id
        delivery_dir.mkdir(parents=True, exist_ok=False)
        markdown = render_plan_markdown(work["plan"], work["agent_task"], actor)
        (delivery_dir / "production-plan.md").write_text(markdown, encoding="utf-8")
        self._write_json(delivery_dir / "snapshot.json", {
            "delivery_id": version_id, "task_id": task_id, "actor": actor,
            "created_at": utc_now(), "item_version": item["version"], "plan": work["plan"],
        })
        return {"item": item, "delivery_id": version_id,
                "markdown_path": str(delivery_dir / "production-plan.md")}

    def list_revisions(self, task_id: str) -> list[dict[str, Any]]:
        revision_dir = self.items_root / task_id / "revisions"
        if not revision_dir.exists():
            return []
        result = []
        for path in sorted(revision_dir.glob("*.json"), reverse=True):
            value = self._read_json(path)
            result.append({key: value[key] for key in (
                "revision_id", "actor", "reason", "base_version", "created_at", "validation"
            )})
        return result

    def dashboard(self) -> dict[str, Any]:
        batches = self.list_batches()
        items = [item for batch in batches for item in batch["items"]]
        counts: dict[str, int] = {}
        routes: dict[str, int] = {}
        tags: dict[str, int] = {}
        for item in items:
            counts[item["business_status"]] = counts.get(item["business_status"], 0) + 1
            if item.get("route"):
                routes[item["route"]] = routes.get(item["route"], 0) + 1
            for tag in item.get("tags", []):
                tags[tag] = tags.get(tag, 0) + 1
        return {
            "total": len(items), "completed": counts.get("completed", 0),
            "pending_review": counts.get("pending_review", 0),
            "needs_attention": counts.get("needs_input", 0) + counts.get("failed", 0) + counts.get("unsupported", 0),
            "status_counts": counts, "route_counts": routes,
            "top_tags": sorted(tags.items(), key=lambda value: (-value[1], value[0]))[:8],
            "batches": batches[:8],
        }

    def export_batch(self, batch_id: str, *, include_audit: bool = False) -> dict[str, str]:
        batch = self.get_batch(batch_id)
        works = [self.get_work_item(task_id) for task_id in batch["task_ids"]]
        export_id = f"export-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        export_dir = self.exports_root / export_id
        export_dir.mkdir(parents=True)
        sheets = build_export_sheets(works)
        xlsx_path = export_dir / f"{batch_id}.xlsx"
        write_xlsx(xlsx_path, sheets)
        csv_path = export_dir / f"{batch_id}-tasks.csv"
        _write_csv(csv_path, sheets["任务汇总"])
        zip_path = export_dir / f"{batch_id}.zip"
        failures: list[str] = []
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(xlsx_path, xlsx_path.name)
            archive.write(csv_path, csv_path.name)
            for work in works:
                task_id = work["task_id"]
                try:
                    markdown = render_plan_markdown(work["plan"], work["agent_task"], "批量导出")
                    archive.writestr(f"plans/{task_id}.md", markdown)
                    materials_ref = work["agent_task"].get("artifacts", {}).get("materials_dir")
                    materials = Path(materials_ref).resolve() if materials_ref else None
                    if (materials is not None and materials.is_dir()
                            and (materials == self.outputs_root or self.outputs_root in materials.parents)):
                        for file in materials.rglob("*"):
                            if file.is_file():
                                archive.write(file, f"materials/{task_id}/{file.relative_to(materials)}")
                    if include_audit:
                        archive.writestr(f"audit/{task_id}.json", json.dumps(work, ensure_ascii=False, indent=2))
                except Exception as error:
                    failures.append(f"{task_id}: {error}")
            archive.writestr("FAILED.txt", "\n".join(failures) or "无失败任务")
        return {"export_id": export_id, "xlsx": str(xlsx_path), "csv": str(csv_path), "zip": str(zip_path)}

    def _set_review_status(self, task_id: str, expected_version: int, status: str, require_valid: bool) -> dict[str, Any]:
        item = self._read_item(task_id)
        if item["version"] != expected_version:
            raise RevisionConflict("任务已被更新，请刷新后重试")
        if require_valid:
            plan = self._latest_revision(task_id)
            plan_value = copy.deepcopy(plan["plan"]) if plan else self._plan_from_task(self._load_task(task_id))
            plan_value["risks"] = canonicalize_risks(plan_value.get("risks"))
            issues = validate_plan(plan_value)
            if issues:
                raise WorkbenchError("方案校验未通过：" + "；".join(issue["message"] for issue in issues))
        item["review_status"] = status
        item["version"] += 1
        item["updated_at"] = utc_now()
        self._write_json(self._item_path(task_id), item)
        return item

    def _decorate_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        items = []
        for task_id in batch["task_ids"]:
            item = self._read_item(task_id)
            task = self._load_task(task_id)
            summary = summarize_task(task)
            items.append({**item, **summary,
                "business_status": agent_status_to_business(task, item.get("review_status"))})
        statuses = [item["business_status"] for item in items]
        completed = sum(status == "completed" for status in statuses)
        return {**batch, "items": items, "progress": {"completed": completed, "total": len(items)}}

    def _load_task(self, task_id: str) -> dict[str, Any]:
        path = self.outputs_root / task_id / "task-result.json"
        if not path.exists():
            return {"task_id": task_id, "status": "initialized", "current_step": 1,
                    "source": {"video_uri": "", "title": task_id}, "workflow": {},
                    "artifacts": {}, "issues": [], "updated_at": None}
        return self._read_json(path)

    def _plan_from_task(self, task: dict[str, Any]) -> dict[str, Any]:
        workflow = task.get("workflow", {})
        outputs = {step: (workflow.get(step, {}).get("output") or {}) for step in (
            "step_1", "step_2", "step_3", "step_4", "step_5", "step_6", "step_7"
        )}
        return {
            "summary": outputs["step_1"].get("content_summary", ""),
            "primary_selling_point": outputs["step_2"].get("primary_selling_point", {}),
            "secondary_selling_points": outputs["step_2"].get("secondary_selling_points", []),
            "replication_goal": outputs["step_2"].get("replication_goal", {"preserve": [], "replace": [], "adapt": [], "optional": []}),
            "selected_chain": outputs["step_3"].get("selected_chain", ""),
            "selection_reason": outputs["step_3"].get("selection_reason", ""),
            "case_ids": outputs["step_3"].get("case_ids", []),
            "runtime_inputs": outputs["step_4"].get("runtime_inputs", []),
            "base_materials": outputs["step_4"].get("base_materials", []),
            "nodes": outputs["step_4"].get("nodes", []),
            "node_prompts": outputs["step_6"].get("node_prompts", []),
            "risks": merge_workflow_risks(
                outputs["step_3"].get("risks"),
                outputs["step_4"].get("risks"),
                outputs["step_6"].get("coverage_gaps"),
            ),
        }

    def _latest_revision(self, task_id: str) -> dict[str, Any] | None:
        paths = sorted((self.items_root / task_id / "revisions").glob("*.json"))
        return self._read_json(paths[-1]) if paths else None

    def _read_item(self, task_id: str) -> dict[str, Any]:
        self._validate_id(task_id)
        path = self._item_path(task_id)
        if not path.exists():
            raise WorkbenchError(f"工作项不存在：{task_id}")
        return self._read_json(path)

    def _item_path(self, task_id: str) -> Path:
        return self.items_root / task_id / "work-item.json"

    @staticmethod
    def _validate_id(value: str) -> None:
        if not SAFE_ID.fullmatch(value):
            raise WorkbenchError(f"无效 ID：{value!r}")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
                json.dump(value, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
                temporary = Path(file.name)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


def summarize_task(task: dict[str, Any]) -> dict[str, Any]:
    workflow = task.get("workflow", {})
    step2 = workflow.get("step_2", {}).get("output") or {}
    step3 = workflow.get("step_3", {}).get("output") or {}
    step4 = workflow.get("step_4", {}).get("output") or {}
    primary = step2.get("primary_selling_point") or {}
    return {
        "agent_status": task.get("status"), "current_step": task.get("current_step"),
        "title": task.get("source", {}).get("title") or task.get("task_id"),
        "video_uri": task.get("source", {}).get("video_uri", ""),
        "selling_point": primary.get("description", ""), "tags": primary.get("tags", []),
        "confidence": primary.get("confidence"), "route": step3.get("selected_chain"),
        "node_count": len(step4.get("nodes", [])), "issues": task.get("issues", []),
        "agent_updated_at": task.get("updated_at"),
    }


def validate_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    def issue(code: str, message: str, path: str) -> None:
        issues.append({"code": code, "message": message, "path": path})
    primary = plan.get("primary_selling_point") or {}
    if not primary.get("description"):
        issue("missing_selling_point", "缺少核心卖点", "primary_selling_point.description")
    chain = plan.get("selected_chain")
    if chain not in {"single_image", "reference_video", "multi_image", "unsupported"}:
        issue("invalid_chain", "请选择有效链路", "selected_chain")
    if chain == "unsupported":
        issue("unsupported_chain", "当前链路需要人工判断，不可自动交付", "selected_chain")
    runtime_ids = [value.get("id") for value in plan.get("runtime_inputs", [])]
    material_ids = [value.get("id") for value in plan.get("base_materials", [])]
    nodes = plan.get("nodes", [])
    node_ids = [node.get("id") for node in nodes]
    output_ids = [output for node in nodes for output in node.get("outputs", [])]
    all_ids = runtime_ids + material_ids + output_ids
    for label, values in (("运行时输入", runtime_ids), ("固定素材", material_ids), ("节点", node_ids), ("节点输出", output_ids)):
        duplicates = sorted({value for value in values if value and values.count(value) > 1})
        if duplicates:
            issue("duplicate_id", f"{label} ID 重复：{', '.join(duplicates)}", "nodes")
    if len(set(value for value in all_ids if value)) != len([value for value in all_ids if value]):
        issue("cross_scope_duplicate", "输入、素材与节点输出 ID 必须唯一", "nodes")
    available = set(value for value in runtime_ids + material_ids + output_ids if value)
    node_set = set(value for value in node_ids if value)
    for index, node in enumerate(nodes):
        unknown_deps = set(node.get("dependencies", [])) - node_set
        unknown_inputs = set(node.get("inputs", [])) - available
        if unknown_deps:
            issue("broken_dependency", f"节点 {node.get('id')} 引用了不存在的依赖", f"nodes.{index}.dependencies")
        if unknown_inputs:
            issue("broken_input", f"节点 {node.get('id')} 引用了不存在的输入", f"nodes.{index}.inputs")
        if node.get("needs_input") or not node.get("inputs"):
            issue("missing_node_input", f"节点 {node.get('display_name') or node.get('id')} 需要补充输入", f"nodes.{index}.inputs")
        if not [value for value in node.get("outputs", []) if value]:
            issue("missing_node_output", f"节点 {node.get('display_name') or node.get('id')} 需要补充产出内容", f"nodes.{index}.outputs")
    prompt_nodes = {value.get("node_id") for value in plan.get("node_prompts", [])}
    for index, node in enumerate(nodes):
        if node.get("model") and node.get("id") not in prompt_nodes:
            issue("missing_prompt", f"模型节点 {node.get('id')} 缺少 Prompt", f"nodes.{index}")
    for prompt in plan.get("node_prompts", []):
        if prompt.get("node_id") not in node_set:
            issue("orphan_prompt", "Prompt 引用了不存在的节点", "node_prompts")
        elif not any((variant.get("prompt") or "").strip() for variant in prompt.get("variants", [])):
            issue("missing_prompt_text", f"节点 {prompt.get('node_id')} 的 Prompt 尚未填写", "node_prompts")
    return issues


def render_plan_markdown(plan: dict[str, Any], task: dict[str, Any], actor: str) -> str:
    primary = plan.get("primary_selling_point") or {}
    lines = ["# 特效生成链路方案", "", f"- **视频**：{task.get('source', {}).get('title') or task.get('task_id')}",
             f"- **核心卖点**：{primary.get('description', '未填写')}",
             f"- **链路**：{plan.get('selected_chain', '未选择')}",
             f"- **交付人**：{actor}", "", "> 本方案未经真实模型跑片验证，不代表成片质量结论。", "",
             "## 链路选择", "", plan.get("selection_reason") or "无", "", "## 节点方案", ""]
    prompts = {value.get("node_id"): value for value in plan.get("node_prompts", [])}
    for index, node in enumerate(plan.get("nodes", []), 1):
        lines.extend([f"### {index}. {node.get('id', '未命名节点')}", "",
                      f"- 模型：{node.get('model') or '无'}", f"- 输入：{', '.join(node.get('inputs', [])) or '无'}",
                      f"- 输出：{', '.join(node.get('outputs', [])) or '无'}", ""])
        prompt = prompts.get(node.get("id"))
        if prompt:
            for variant in prompt.get("variants", []):
                lines.extend([f"**Prompt（{variant.get('variant_id', 'default')}）**", "", variant.get("prompt", ""), ""])
    lines.extend(["## 输入与素材", "", "### 运行时输入（未来用户使用特效时提供）", ""])
    lines.extend([f"- {value.get('id')}: {value.get('description', '')}" for value in plan.get("runtime_inputs", [])] or ["- 无"])
    lines.extend(["", "### 当前固定素材", ""])
    lines.extend([f"- {value.get('id')}: {value.get('description', '')}" for value in plan.get("base_materials", [])] or ["- 无"])
    lines.extend(["", "## 风险与待验证项", ""])
    for risk in plan.get("risks", []):
        lines.append(f"- {risk if isinstance(risk, str) else json.dumps(risk, ensure_ascii=False)}")
    if not plan.get("risks"):
        lines.append("- 无已记录风险")
    return "\n".join(lines) + "\n"


def build_export_sheets(works: list[dict[str, Any]]) -> dict[str, list[list[Any]]]:
    tasks = [["任务ID", "标题", "业务状态", "核心卖点", "链路", "节点数", "负责人", "优先级", "风险数", "更新时间"]]
    nodes = [["任务ID", "节点ID", "依赖", "模型", "输入", "输出", "参数"]]
    prompts = [["任务ID", "节点ID", "分支", "条件", "Prompt"]]
    materials = [["任务ID", "类型", "ID", "描述/风险", "必需"]]
    for work in works:
        plan, task_id = work["plan"], work["task_id"]
        tasks.append([task_id, work["agent_task"].get("source", {}).get("title") or task_id,
                      work["business_status"], (plan.get("primary_selling_point") or {}).get("description", ""),
                      plan.get("selected_chain", ""), len(plan.get("nodes", [])), work.get("assignee", ""),
                      work.get("priority", ""), len(plan.get("risks", [])), work.get("updated_at", "")])
        for node in plan.get("nodes", []):
            nodes.append([task_id, node.get("id"), ", ".join(node.get("dependencies", [])), node.get("model", ""),
                          ", ".join(node.get("inputs", [])), ", ".join(node.get("outputs", [])),
                          json.dumps(node.get("parameters", {}), ensure_ascii=False)])
        for prompt in plan.get("node_prompts", []):
            for variant in prompt.get("variants", []):
                prompts.append([task_id, prompt.get("node_id"), variant.get("variant_id", "default"),
                                json.dumps(variant.get("conditions", {}), ensure_ascii=False),
                                variant.get("prompt", "")])
        for kind, values in (("运行时输入", plan.get("runtime_inputs", [])), ("固定素材", plan.get("base_materials", []))):
            for value in values:
                materials.append([task_id, kind, value.get("id"), value.get("description", ""), value.get("required", "")])
        for risk in plan.get("risks", []):
            materials.append([task_id, "风险", "", risk if isinstance(risk, str) else json.dumps(risk, ensure_ascii=False), ""])
    return {"任务汇总": tasks, "节点明细": nodes, "Prompt明细": prompts, "素材与风险": materials}


def _write_csv(path: Path, rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        csv.writer(file).writerows(rows)


def write_xlsx(path: Path, sheets: dict[str, list[list[Any]]]) -> None:
    """Write a small standards-compliant XLSX using inline strings."""
    def cell(value: Any, row: int, column: int) -> str:
        letters, number = "", column
        while number:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        reference = f"{letters}{row}"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{reference}"><v>{value}</v></c>'
        text = escape("" if value is None else str(value))
        return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + overrides + '</Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheet_defs = "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1))
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + sheet_defs + '</sheets></workbook>')
        relationships = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + relationships + '</Relationships>')
        for index, rows in enumerate(sheets.values(), 1):
            body = "".join(f'<row r="{row_index}">' + "".join(cell(value, row_index, column) for column, value in enumerate(row, 1)) + '</row>' for row_index, row in enumerate(rows, 1))
            archive.writestr(f"xl/worksheets/sheet{index}.xml", '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + body + '</sheetData></worksheet>')
