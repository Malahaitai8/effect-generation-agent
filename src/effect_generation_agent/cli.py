from __future__ import annotations

import argparse
import json
import sys
import uuid
import os
import tempfile
from pathlib import Path

from .batch import BatchRunner
from .config import load_local_env
from .errors import AgentRuntimeError
from .evaluation import Step12TrialEvaluator
from .executors import build_deepseek_executors, build_manual_executors
from .mock_executor import build_mock_executors
from .model_execution import (
    ManualExchangeModelClient,
    DeepSeekStructuredModelClient,
    ManualResultRequired,
    ModelExecutionBlocked,
)
from .migration import migrate_task_040_to_050
from .retrieval import CaseRetriever, SentenceTransformerEmbeddingEncoder
from .step3 import Step3RetrievalSelectionExecutor
from .project import PROJECT_ROOT, scaffold_status
from .resources import load_runtime_resources
from .store import TaskStore
from .workflow import WorkflowEngine


DEFAULT_OUTPUTS_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "task-result.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="effect-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="检查 Agent 脚手架及当前实现阶段")

    task_parser = subparsers.add_parser("task", help="创建、查看或运行本地任务")
    task_parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=DEFAULT_OUTPUTS_ROOT,
        help="任务状态根目录；默认使用项目 outputs/",
    )
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)

    create_parser = task_subparsers.add_parser("create", help="创建任务")
    create_parser.add_argument("--video-uri", required=True)
    create_parser.add_argument("--task-id")
    create_parser.add_argument("--title")

    show_parser = task_subparsers.add_parser("show", help="查看任务状态")
    show_parser.add_argument("task_id")

    migrate_parser = task_subparsers.add_parser("migrate", help="显式迁移旧版任务状态")
    migrate_parser.add_argument("task_id")

    run_parser = task_subparsers.add_parser("run", help="运行任务")
    run_parser.add_argument("task_id")
    run_mode = run_parser.add_mutually_exclusive_group(required=True)
    run_mode.add_argument("--mock", action="store_true")
    run_mode.add_argument("--manual", action="store_true")
    run_mode.add_argument("--deepseek", action="store_true")

    resume_parser = task_subparsers.add_parser("resume", help="恢复当前任务步骤")
    resume_parser.add_argument("task_id")
    resume_mode = resume_parser.add_mutually_exclusive_group(required=True)
    resume_mode.add_argument("--mock", action="store_true")
    resume_mode.add_argument("--manual", action="store_true")
    resume_mode.add_argument("--deepseek", action="store_true")

    pending_parser = task_subparsers.add_parser(
        "pending-request", help="查看当前等待 Codex 处理的请求"
    )
    pending_parser.add_argument("task_id")

    submit_parser = task_subparsers.add_parser(
        "submit", help="提交当前 Step 的 Codex 业务 JSON 并恢复任务"
    )
    submit_parser.add_argument("task_id")
    submit_parser.add_argument("--result", type=Path, required=True)
    submit_parser.add_argument(
        "--deepseek",
        action="store_true",
        help="提交 Step 1 后使用 DeepSeek 与本地 RAG 继续运行",
    )

    evaluate_parser = task_subparsers.add_parser(
        "evaluate-step1-2", help="导出 Step 1–2 与人工试跑基线的对比请求"
    )
    evaluate_parser.add_argument("task_id")
    evaluate_parser.add_argument("--baseline", type=Path, required=True)

    submit_evaluation_parser = task_subparsers.add_parser(
        "submit-evaluation", help="提交并保存 Step 1–2 人工对比结果"
    )
    submit_evaluation_parser.add_argument("task_id")
    submit_evaluation_parser.add_argument("--result", type=Path, required=True)

    batch_parser = subparsers.add_parser("batch", help="创建、查看或并发运行任务批次")
    batch_parser.add_argument("--outputs-dir", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command", required=True)
    batch_create = batch_subparsers.add_parser("create", help="从 JSON 清单创建任务批次")
    batch_create.add_argument("--batch-id", required=True)
    batch_create.add_argument("--manifest", type=Path, required=True)
    batch_show = batch_subparsers.add_parser("show", help="查看批次及各任务状态")
    batch_show.add_argument("batch_id")
    for command in ("run", "resume"):
        batch_run = batch_subparsers.add_parser(command, help=f"{command} 批次")
        batch_run.add_argument("batch_id")
        batch_run.add_argument("--max-concurrency", type=int, default=2)
        modes = batch_run.add_mutually_exclusive_group(required=True)
        modes.add_argument("--mock", action="store_true")
        modes.add_argument("--manual", action="store_true")
        modes.add_argument("--deepseek", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_local_env(PROJECT_ROOT)
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            _print_json(scaffold_status())
            return 0

        if args.command == "batch":
            store = TaskStore(args.outputs_dir, DEFAULT_SCHEMA_PATH)
            runner = BatchRunner(store)
            if args.batch_command == "create":
                manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
                if not isinstance(manifest, list):
                    raise ValueError("Batch manifest must be a JSON array")
                _print_json(runner.create(args.batch_id, manifest))
                return 0
            if args.batch_command == "show":
                _print_json(runner.show(args.batch_id))
                return 0
            manual_client = ManualExchangeModelClient(
                args.outputs_dir, store.validator.schema_version
            )
            if args.deepseek:
                mode = "deepseek"
                shared_engine = _deepseek_engine(store, manual_client, args.outputs_dir)
            elif args.manual:
                mode = "manual"
                shared_engine = _manual_engine(store, manual_client, args.outputs_dir)
            else:
                mode = "mock"
                shared_engine = WorkflowEngine(
                    store,
                    build_mock_executors(),
                    resources=load_runtime_resources(PROJECT_ROOT, args.outputs_dir),
                )
            factory = lambda: shared_engine
            _print_json(
                runner.run(
                    args.batch_id,
                    factory,
                    mode=mode,
                    max_concurrency=args.max_concurrency,
                    resume=args.batch_command == "resume",
                )
            )
            return 0

        if args.task_command == "migrate":
            task_path = args.outputs_dir.resolve() / args.task_id / "task-result.json"
            _print_json(migrate_task_040_to_050(task_path, DEFAULT_SCHEMA_PATH))
            return 0

        store = TaskStore(args.outputs_dir, DEFAULT_SCHEMA_PATH)
        if args.task_command == "create":
            task_id = args.task_id or f"task-{uuid.uuid4().hex[:12]}"
            _print_json(
                store.create_task(
                    task_id,
                    args.video_uri,
                    title=args.title,
                )
            )
            return 0
        if args.task_command == "show":
            _print_json(store.load_task(args.task_id))
            return 0

        manual_client = ManualExchangeModelClient(
            args.outputs_dir,
            store.validator.schema_version,
        )
        if args.task_command == "pending-request":
            task = store.load_task(args.task_id)
            _print_json(manual_client.pending_request(args.task_id, task["current_step"]))
            return 0
        if args.task_command == "submit":
            task = store.load_task(args.task_id)
            if task["status"] != "needs_input":
                raise ModelExecutionBlocked(
                    f"Task is not waiting for a Codex result: {task['status']}"
                )
            with args.result.open(encoding="utf-8") as result_file:
                output = json.load(result_file)
            if not isinstance(output, dict):
                raise ModelExecutionBlocked("Submitted result must be a JSON object")
            store.validate_step_output(args.task_id, task["current_step"], output)
            manual_client.submit(args.task_id, task["current_step"], output)
            engine = (
                _deepseek_engine(store, manual_client, args.outputs_dir)
                if args.deepseek
                else _manual_engine(store, manual_client, args.outputs_dir)
            )
            _print_json(engine.resume(args.task_id))
            return 0
        if args.task_command in {"evaluate-step1-2", "submit-evaluation"}:
            evaluation_client = ManualExchangeModelClient(
                args.outputs_dir,
                store.validator.schema_version,
                namespace="evaluation-step1-2",
            )
            evaluator = Step12TrialEvaluator(
                evaluation_client,
                PROJECT_ROOT / "evals" / "step1-step2-comparison.md",
            )
            task = store.load_task(args.task_id)
            if args.task_command == "evaluate-step1-2":
                try:
                    result = evaluator.compare(task, args.baseline.resolve())
                except ManualResultRequired as error:
                    _print_json(evaluation_client.pending_request(args.task_id, 2))
                    return 0
                _save_evaluation(args.outputs_dir, args.task_id, result)
                _print_json(result)
                return 0
            request = evaluation_client.pending_request(args.task_id, 2)
            with args.result.open(encoding="utf-8") as result_file:
                result = json.load(result_file)
            if not isinstance(result, dict):
                raise ModelExecutionBlocked("Evaluation result must be a JSON object")
            evaluation_client.submit(args.task_id, 2, result)
            baseline_path = Path(request["inputs"]["baseline_path"])
            comparison = evaluator.compare(task, baseline_path)
            _save_evaluation(args.outputs_dir, args.task_id, comparison)
            _print_json(comparison)
            return 0

        engine = (
            _deepseek_engine(store, manual_client, args.outputs_dir)
            if getattr(args, "deepseek", False)
            else _manual_engine(store, manual_client, args.outputs_dir)
            if getattr(args, "manual", False)
            else WorkflowEngine(
                store,
                build_mock_executors(),
                resources=load_runtime_resources(PROJECT_ROOT, args.outputs_dir),
            )
        )
        if args.task_command == "run":
            _print_json(engine.run(args.task_id))
            return 0
        if args.task_command == "resume":
            _print_json(engine.resume(args.task_id))
            return 0
        raise AssertionError(f"Unhandled task command: {args.task_command}")
    except (AgentRuntimeError, ModelExecutionBlocked, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _manual_engine(
    store: TaskStore,
    client: ManualExchangeModelClient,
    outputs_dir: Path,
) -> WorkflowEngine:
    retriever = CaseRetriever(
        PROJECT_ROOT / "rag" / "data" / "cases.jsonl",
        PROJECT_ROOT / "rag" / "case.schema.json",
        SentenceTransformerEmbeddingEncoder(),
    )
    return WorkflowEngine(
        store,
        build_manual_executors(
            PROJECT_ROOT,
            client,
            step_3_executor=Step3RetrievalSelectionExecutor(retriever, client),
        ),
        resources=load_runtime_resources(PROJECT_ROOT, outputs_dir),
    )


def _deepseek_engine(
    store: TaskStore,
    manual_client: ManualExchangeModelClient,
    outputs_dir: Path,
) -> WorkflowEngine:
    deepseek_client = DeepSeekStructuredModelClient(
        output_validator=store.validate_step_output
    )
    retriever = CaseRetriever(
        PROJECT_ROOT / "rag" / "data" / "cases.jsonl",
        PROJECT_ROOT / "rag" / "case.schema.json",
        SentenceTransformerEmbeddingEncoder(),
    )
    return WorkflowEngine(
        store,
        build_deepseek_executors(
            PROJECT_ROOT,
            manual_client,
            deepseek_client,
            retriever,
        ),
        resources=load_runtime_resources(PROJECT_ROOT, outputs_dir),
    )


def _save_evaluation(
    outputs_dir: Path,
    task_id: str,
    result: object,
) -> Path:
    output_dir = outputs_dir.resolve() / task_id / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "step1-step2-comparison.json"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_dir,
            prefix=".step1-step2-comparison.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(result, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return output_path
