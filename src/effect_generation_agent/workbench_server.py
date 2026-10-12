"""Dependency-free HTTP server for the effect planning workbench."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .batch import BatchRunner
from .mock_executor import build_mock_executors
from .project import PROJECT_ROOT
from .resources import load_runtime_resources
from .store import TaskStore
from .workbench import RevisionConflict, WorkbenchError, WorkbenchStore
from .workflow import WorkflowEngine


STATIC_ROOT = Path(__file__).with_name("workbench_static")
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "task-result.schema.json"


class WorkbenchApplication:
    def __init__(self, outputs_root: Path) -> None:
        self.outputs_root = outputs_root.resolve()
        self.task_store = TaskStore(self.outputs_root, SCHEMA_PATH)
        self.batch_runner = BatchRunner(self.task_store)
        self.workbench = WorkbenchStore(self.outputs_root)
        self.current_user = getpass.getuser()
        self._media_locks: dict[str, threading.Lock] = {}
        self._media_locks_guard = threading.Lock()

    def browser_media(self, task_id: str) -> Path:
        work = self.workbench.get_work_item(task_id)
        source = Path(work["agent_task"].get("source", {}).get("video_uri", ""))
        if not source.is_absolute():
            source = (PROJECT_ROOT / source).resolve()
        if not source.is_file():
            raise WorkbenchError("原视频文件不存在")
        if source.suffix.lower() in {".mp4", ".webm"}:
            return source
        stat = source.stat()
        cache_key = hashlib.sha256(
            f"{source}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()[:24]
        cache_dir = self.outputs_root / ".workbench-cache" / "media"
        target = cache_dir / f"{cache_key}.mp4"
        with self._media_locks_guard:
            lock = self._media_locks.setdefault(cache_key, threading.Lock())
        with lock:
            if target.is_file() and target.stat().st_size:
                return target
            cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = cache_dir / f".{cache_key}.{uuid.uuid4().hex}.tmp.mp4"
            ffmpeg = self._resolve_ffmpeg()
            remux = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                     "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", str(temporary)]
            result = subprocess.run(remux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode != 0:
                temporary.unlink(missing_ok=True)
                transcode = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                             "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
                             "-movflags", "+faststart", str(temporary)]
                result = subprocess.run(transcode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode != 0 or not temporary.is_file() or not temporary.stat().st_size:
                temporary.unlink(missing_ok=True)
                detail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
                raise WorkbenchError("原视频兼容处理失败" + (f"：{detail[0]}" if detail else ""))
            os.replace(temporary, target)
        return target

    @staticmethod
    def _resolve_ffmpeg() -> str:
        configured = os.environ.get("EFFECT_GENERATION_FFMPEG")
        candidates = [configured]
        try:
            import imageio_ffmpeg
            candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
        except (ImportError, RuntimeError):
            pass
        candidates.append(shutil.which("ffmpeg"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(Path(candidate).resolve())
        raise WorkbenchError("未找到视频兼容处理工具")

    def reference_frames(self, task_id: str) -> list[dict[str, object]]:
        work = self.workbench.get_work_item(task_id)
        step_one = work["agent_task"].get("workflow", {}).get("step_1", {}).get("output") or {}
        preprocessing = step_one.get("video_preprocessing") or {}
        manifest_path = self._resolve_safe_reference(preprocessing.get("frames_manifest_ref"))
        manifest: list[dict[str, object]] = []
        if manifest_path and manifest_path.is_file():
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = value.get("frames", []) if isinstance(value, dict) else value
            if not isinstance(manifest, list):
                manifest = []
        manifest_by_id = {str(item.get("frame_id")): item for item in manifest if isinstance(item, dict)}
        selected = [item for item in step_one.get("key_frames", []) if isinstance(item, dict)]
        if not selected:
            ids: list[str] = []
            for event in step_one.get("timeline", []):
                for frame_id in event.get("evidence_frame_ids", []):
                    if frame_id not in ids:
                        ids.append(frame_id)
            selected = [{"frame_id": frame_id} for frame_id in ids]
        if not selected and manifest:
            indexes = sorted({round(index * (len(manifest) - 1) / min(4, len(manifest) - 1))
                              for index in range(min(5, len(manifest)))}) if len(manifest) > 1 else [0]
            selected = [manifest[index] for index in indexes]
        result = []
        for item in selected[:5]:
            frame_id = str(item.get("frame_id", ""))
            if not frame_id:
                continue
            try:
                self.reference_frame_path(task_id, frame_id, work=work, manifest=manifest_by_id)
            except WorkbenchError:
                continue
            manifest_item = manifest_by_id.get(frame_id, {})
            result.append({
                "frame_id": frame_id,
                "timestamp_seconds": item.get("timestamp_seconds", manifest_item.get("timestamp_seconds")),
                "description": item.get("content_description") or item.get("state_description") or "关键参考帧",
                "quality_issues": item.get("quality_issues", []),
                "url": f"/api/tasks/{task_id}/reference-frames/{frame_id}",
            })
        return sorted(result, key=lambda item: float(item.get("timestamp_seconds") or 0))

    def reference_frame_path(self, task_id: str, frame_id: str, *, work=None, manifest=None) -> Path:
        if not frame_id or not all(character.isalnum() or character in "_-" for character in frame_id):
            raise WorkbenchError("参考帧 ID 无效")
        work = work or self.workbench.get_work_item(task_id)
        step_one = work["agent_task"].get("workflow", {}).get("step_1", {}).get("output") or {}
        preprocessing = step_one.get("video_preprocessing") or {}
        manifest_path = self._resolve_safe_reference(preprocessing.get("frames_manifest_ref"))
        if manifest is None:
            manifest = {}
            if manifest_path and manifest_path.is_file():
                value = json.loads(manifest_path.read_text(encoding="utf-8"))
                items = value.get("frames", []) if isinstance(value, dict) else value
                manifest = {str(item.get("frame_id")): item for item in items if isinstance(item, dict)}
        candidates: list[Path] = []
        manifest_item = manifest.get(frame_id, {}) if isinstance(manifest, dict) else {}
        if manifest_item.get("file_ref") and manifest_path:
            candidates.append((manifest_path.parent / str(manifest_item["file_ref"])).resolve())
        frames_dir = self._resolve_safe_reference(preprocessing.get("frames_dir"))
        if frames_dir:
            candidates.extend((frames_dir / f"{frame_id}{suffix}").resolve() for suffix in (".jpg", ".jpeg", ".png", ".webp"))
        key_frame = next((item for item in step_one.get("key_frames", []) if item.get("frame_id") == frame_id), {})
        if key_frame.get("file_ref"):
            candidates.append(self._resolve_safe_reference(key_frame["file_ref"]) or Path())
        allowed = [PROJECT_ROOT.resolve(), self.outputs_root]
        for candidate in candidates:
            if candidate and candidate.is_file() and any(candidate == root or root in candidate.parents for root in allowed):
                return candidate
        raise WorkbenchError("参考帧文件不存在")

    def _resolve_safe_reference(self, reference: object) -> Path | None:
        if not reference:
            return None
        path = Path(str(reference))
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        else:
            path = path.resolve()
        if not any(path == root or root in path.parents for root in (PROJECT_ROOT.resolve(), self.outputs_root)):
            raise WorkbenchError("文件引用超出工作台目录")
        return path

    def create_uploaded_batch(self, fields: dict[str, str], uploads: list[dict[str, object]]) -> dict[str, object]:
        batch_id = fields.get("batch_id") or f"batch-{uuid.uuid4().hex[:10]}"
        upload_dir = self.outputs_root / ".uploads" / batch_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        definitions = []
        for index, upload in enumerate(uploads, 1):
            original = str(upload["filename"])
            suffix = Path(original).suffix.lower()
            if suffix not in {".mp4", ".mov", ".m4v", ".webm", ".avi"}:
                raise WorkbenchError(f"不支持的视频格式：{original}")
            task_id = f"{batch_id}-video-{index:03d}"
            destination = upload_dir / f"{task_id}{suffix}"
            with destination.open("wb") as target:
                shutil.copyfileobj(upload["file"], target)
            if destination.stat().st_size == 0:
                raise WorkbenchError(f"视频文件为空：{original}")
            definitions.append({"task_id": task_id, "video_uri": str(destination),
                                "title": Path(original).stem, "priority": fields.get("priority", "normal")})
        if not definitions:
            raise WorkbenchError("请至少上传一条视频")
        agent_batch = self.batch_runner.create(batch_id, definitions)
        workbench_batch = self.workbench.create_batch({
            "batch_id": batch_id, "name": fields.get("name") or batch_id,
            "source": "", "campaign": "", "creator": self.current_user,
        }, definitions)
        return {"agent_batch": agent_batch, "batch": workbench_batch}

    def seed_demo(self) -> dict[str, object]:
        """Create a disposable prototype batch covering the major UI states."""
        batch_id = f"prototype-{uuid.uuid4().hex[:6]}"
        specs = [
            ("掌心小人", "initialized", 1, None, None),
            ("泳池水枪", "running", 3, None, None),
            ("秋日下午茶", "needs_input", 5, None, None),
            ("泡面奇遇", "completed", 7, "single_image", None),
            ("生日摇车窗", "completed", 7, "reference_video", "editing"),
            ("功夫小猫", "completed", 7, "single_image", "deliverable"),
            ("古风水晶桥", "completed", 7, "multi_image", None),
            ("寿司店老板", "failed", 2, None, None),
        ]
        definitions = []
        for index, (title, status, step, route, review) in enumerate(specs, 1):
            task_id = f"{batch_id}-task-{index:02d}"
            definitions.append({"task_id": task_id, "title": title,
                                "priority": "high" if index < 3 else "normal",
                                "assignee": "设计师 Alice" if index % 2 == 0 else None})
            task_dir = self.outputs_root / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            workflow: dict[str, object] = {}
            if step >= 1:
                workflow["step_1"] = {"output": {"content_summary": f"{title}的热点视频内容，通过视觉反差形成趣味叙事。"}}
            if step >= 2:
                workflow["step_2"] = {"output": {"primary_selling_point": {
                    "description": f"将用户主体融入「{title}」的标志性瞬间",
                    "tags": ["state_transformation", "reveal_or_micro_narrative"], "confidence": .88},
                    "secondary_selling_points": [], "replication_goal": {"preserve": [], "replace": [], "adapt": [], "optional": []}}}
            if route:
                workflow["step_3"] = {"output": {"selected_chain": route,
                    "selection_reason": "根据最终视频模型的实际媒体入参选择链路。",
                    "case_ids": ["prototype_case"], "risks": ["身份一致性需在真实模型跑片中验证"]}}
                workflow["step_4"] = {"output": {"runtime_inputs": [{"id": "user_image", "description": "用户主体图"}],
                    "base_materials": [], "nodes": [{"id": "generate_video", "model": "Kling 3.0 Omni",
                    "inputs": ["user_image"], "outputs": ["result_video"], "dependencies": [], "parameters": {}}], "risks": []}}
                workflow["step_6"] = {"output": {"node_prompts": [{"node_id": "generate_video", "model": "Kling 3.0 Omni",
                    "variants": [{"variant_id": "default", "conditions": {}, "prompt": f"保持人物身份，完成{title}的标志性动作与画面变化；全程避免身份漂移、闪烁和穿模。"}]}], "coverage_gaps": []}}
            task = {"task_id": task_id, "status": status, "current_step": step,
                "created_at": "2026-08-26T01:00:00+00:00", "updated_at": "2026-08-26T02:00:00+00:00",
                "source": {"video_uri": "", "title": title}, "workflow": workflow,
                "artifacts": {}, "issues": ([{"message": "需要补充固定视觉素材"}] if status == "needs_input" else
                    [{"message": "视频预处理失败，请重试"}] if status == "failed" else [])}
            (task_dir / "task-result.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        batch = self.workbench.create_batch({"batch_id": batch_id, "name": "前端原型验证批次",
            "creator": self.current_user}, definitions)
        for definition, spec in zip(definitions, specs):
            review = spec[4]
            if review:
                item = self.workbench._read_item(definition["task_id"])
                item["review_status"] = review
                self.workbench._write_json(self.workbench._item_path(definition["task_id"]), item)
        return self.workbench.get_batch(batch_id)

    def seed_real_results(self) -> dict[str, object]:
        """Build a prototype batch from actual persisted Agent runs."""
        candidates = [
            ("blind-v07-a", None),
            ("blind-v07-b", None),
            ("deepseek-blind-b", "pending_review"),
            ("eval-v04-reference-kungfu-cat", "editing"),
            ("trial-pool-water-gun-v04", "deliverable"),
            ("eval-v04-single-pocket-person", "completed"),
            ("trial-autumn-tea", "pending_review"),
            ("deepseek-blind-f", "pending_review"),
        ]
        available = [(task_id, review) for task_id, review in candidates
                     if (self.outputs_root / task_id / "task-result.json").is_file()]
        if not available:
            raise WorkbenchError("outputs 中没有可用的真实任务结果")
        batch_id = f"real-results-{uuid.uuid4().hex[:6]}"
        definitions = []
        review_by_alias: dict[str, str | None] = {}
        friendly_titles = {
            "blind-v07-a": "泡面奇遇真实试跑", "blind-v07-b": "浪漫时刻真实试跑",
            "deepseek-blind-b": "寿司店老板深度分析", "deepseek-blind-f": "泡面奇遇深度分析",
        }
        fallback_videos = {
            "eval-v04-reference-kungfu-cat": PROJECT_ROOT / "测试用例" / "功夫小猫.mov",
            "eval-v04-single-pocket-person": PROJECT_ROOT / "测试用例" / "掌心小人.mov",
        }
        for index, (source_task_id, review) in enumerate(available, 1):
            source_path = self.outputs_root / source_task_id / "task-result.json"
            task = json.loads(source_path.read_text(encoding="utf-8"))
            alias = f"{batch_id}-task-{index:02d}"
            task["task_id"] = alias
            task.setdefault("source", {})
            task["source"]["title"] = task["source"].get("title") or friendly_titles.get(source_task_id, "真实试跑任务")
            current_video = Path(task["source"].get("video_uri", ""))
            if not current_video.is_file() and source_task_id in fallback_videos:
                task["source"]["video_uri"] = str(fallback_videos[source_task_id])
            task["source"].setdefault("metadata", {})
            task["source"]["metadata"]["prototype_source_task_id"] = source_task_id
            alias_dir = self.outputs_root / alias
            alias_dir.mkdir(parents=True, exist_ok=False)
            (alias_dir / "task-result.json").write_text(
                json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            definitions.append({"task_id": alias, "title": task["source"]["title"],
                "priority": "high" if index <= 2 else "normal",
                "assignee": "设计师 Alice" if index % 2 == 0 else None,
                "notes": f"来自真实任务 {source_task_id}"})
            review_by_alias[alias] = review
        self.workbench.create_batch({"batch_id": batch_id, "name": "真实试跑结果演示",
            "creator": self.current_user}, definitions)
        for definition in definitions:
            review = review_by_alias[definition["task_id"]]
            if review:
                item = self.workbench._read_item(definition["task_id"])
                item["review_status"] = review
                self.workbench._write_json(self.workbench._item_path(definition["task_id"]), item)
        return self.workbench.get_batch(batch_id)

    def run_mock_async(self, batch_id: str, max_concurrency: int = 2) -> None:
        def run() -> None:
            self.batch_runner.run(
                batch_id,
                lambda: WorkflowEngine(self.task_store, build_mock_executors(),
                    resources=load_runtime_resources(PROJECT_ROOT, self.outputs_root)),
                mode="mock", max_concurrency=max_concurrency,
            )
        threading.Thread(target=run, name=f"workbench-{batch_id}", daemon=True).start()


def make_handler(application: WorkbenchApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "EffectWorkbench/0.1"

        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/api/dashboard":
                    return self.json_response(application.workbench.dashboard())
                if path == "/api/session":
                    return self.json_response({"username": application.current_user})
                if path == "/api/batches":
                    return self.json_response(application.workbench.list_batches())
                if path.startswith("/api/batches/"):
                    batch_id = path.split("/")[3]
                    return self.json_response(application.workbench.get_batch(batch_id))
                if path.startswith("/api/tasks/"):
                    task_id = path.split("/")[3]
                    if path.endswith("/reference-frames"):
                        return self.json_response({"frames": application.reference_frames(task_id)})
                    if "/reference-frames/" in path:
                        frame_id = path.rsplit("/", 1)[-1]
                        return self.send_explicit_file(
                            application.reference_frame_path(task_id, frame_id), attachment=False
                        )
                    if path.endswith("/timeline-preview"):
                        work = application.workbench.get_work_item(task_id)
                        step_one = work["agent_task"].get("workflow", {}).get("step_1", {}).get("output") or {}
                        reference = (step_one.get("video_preprocessing") or {}).get("timeline_overview_ref", "")
                        preview = Path(reference)
                        if not preview.is_absolute():
                            preview = (PROJECT_ROOT / preview).resolve()
                        return self.send_explicit_file(preview, attachment=False)
                    if path.endswith("/media"):
                        return self.send_explicit_file(application.browser_media(task_id), attachment=False)
                    return self.json_response(application.workbench.get_work_item(task_id))
                if path.startswith("/api/files/"):
                    relative = path[len("/api/files/"):]
                    return self.send_managed_file(relative)
                return self.send_static(path)
            except WorkbenchError as error:
                self.json_error(HTTPStatus.NOT_FOUND, str(error))
            except Exception as error:
                self.json_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

        def do_POST(self) -> None:
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/api/batches/upload":
                    fields, uploads = self.read_multipart()
                    result = application.create_uploaded_batch(fields, uploads)
                    if fields.get("auto_run") == "mock":
                        application.run_mock_async(result["batch"]["batch_id"])
                    return self.json_response(result, HTTPStatus.CREATED)
                if path == "/api/demo/seed":
                    return self.json_response(application.seed_demo(), HTTPStatus.CREATED)
                if path == "/api/demo/real-results":
                    return self.json_response(application.seed_real_results(), HTTPStatus.CREATED)
                if path.startswith("/api/batches/") and path.endswith("/run-mock"):
                    batch_id = path.split("/")[3]
                    application.run_mock_async(batch_id)
                    return self.json_response({"status": "started"}, HTTPStatus.ACCEPTED)
                if path.startswith("/api/batches/") and path.endswith("/export"):
                    batch_id = path.split("/")[3]
                    body = self.read_json()
                    return self.json_response(application.workbench.export_batch(batch_id,
                        include_audit=bool(body.get("include_audit"))))
                if path.startswith("/api/tasks/"):
                    parts = path.split("/")
                    task_id, action = parts[3], parts[4]
                    body = self.read_json()
                    if action == "assignment":
                        result = application.workbench.update_assignment(task_id, body, int(body["expected_version"]))
                    elif action == "revisions":
                        result = application.workbench.save_revision(task_id, body["plan"], actor=body.get("actor", "设计师"),
                            reason=body.get("reason", ""), expected_version=int(body["expected_version"]))
                    elif action == "submit-review":
                        result = application.workbench.submit_review(task_id, int(body["expected_version"]))
                    elif action == "confirm-delivery":
                        result = application.workbench.confirm_delivery(task_id, int(body["expected_version"]), body.get("actor", "设计师"))
                    else:
                        raise WorkbenchError(f"未知操作：{action}")
                    return self.json_response(result)
                raise WorkbenchError("接口不存在")
            except RevisionConflict as error:
                self.json_error(HTTPStatus.CONFLICT, str(error))
            except (WorkbenchError, KeyError, ValueError) as error:
                self.json_error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                self.json_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

        def read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise WorkbenchError("请求体必须是 JSON 对象")
            return value

        def read_multipart(self) -> tuple[dict[str, str], list[dict[str, object]]]:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                raise WorkbenchError("空的上传请求")
            body = self.rfile.read(length)
            envelope = (f"Content-Type: {self.headers.get('Content-Type', '')}\r\n"
                        f"MIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
            form = BytesParser(policy=default).parsebytes(envelope)
            if not form.is_multipart():
                raise WorkbenchError("上传请求必须是 multipart/form-data")
            fields: dict[str, str] = {}
            uploads = []
            for item in form.iter_parts():
                name = item.get_param("name", header="content-disposition")
                filename = item.get_filename()
                payload = item.get_payload(decode=True) or b""
                if filename:
                    uploads.append({"filename": filename, "file": io.BytesIO(payload)})
                else:
                    fields[str(name)] = payload.decode(item.get_content_charset() or "utf-8")
            return fields, uploads

        def json_response(self, value: object, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json_error(self, status: int, message: str) -> None:
            self.json_response({"error": message}, status)

        def send_static(self, path: str) -> None:
            relative = "index.html" if path in {"", "/"} else path.lstrip("/")
            file = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT.resolve() not in file.parents or not file.is_file():
                file = STATIC_ROOT / "index.html"
            body = file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_managed_file(self, relative: str) -> None:
            file = (application.outputs_root / relative).resolve()
            if application.outputs_root not in file.parents or not file.is_file():
                raise WorkbenchError("文件不存在")
            self.send_explicit_file(file, attachment=True)

        def send_explicit_file(self, file: Path, *, attachment: bool) -> None:
            if not file.is_file():
                raise WorkbenchError("文件不存在")
            size = file.stat().st_size
            start, end = 0, size - 1
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                requested = range_header[6:].split(",", 1)[0]
                start_text, end_text = requested.split("-", 1)
                if start_text:
                    start = int(start_text)
                if end_text:
                    end = min(int(end_text), size - 1)
                if start < 0 or start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            length = end - start + 1
            self.send_response(HTTPStatus.PARTIAL_CONTENT if range_header else HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{file.name}"')
            self.send_header("Content-Length", str(length))
            self.end_headers()
            with file.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    chunk = source.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler


def serve(outputs_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    application = WorkbenchApplication(outputs_root)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"特效方案工作台已启动：http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="effect-workbench")
    parser.add_argument("--outputs-dir", type=Path, default=PROJECT_ROOT / "outputs")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    serve(args.outputs_dir, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
