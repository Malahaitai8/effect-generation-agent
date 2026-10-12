"""Factories for the real execution paths that are currently available."""

from __future__ import annotations

from pathlib import Path

from .delivery import ProductionPlanExecutor
from .materials import MaterialProcessor, Step5MaterialExecutor
from .model_execution import StructuredModelClient, build_structured_prompt_executors
from .prompt_quality import Step4ValidatedDesignExecutor, Step6ValidatedPromptExecutor
from .retrieval import CaseRetriever
from .step3 import Step3RetrievalSelectionExecutor
from .video_preprocessing import ScriptVideoPreprocessor, Step1VideoUnderstandingExecutor
from .workflow import ExecutorKey, StepExecutor
from .workflow import StepContext, StepResult


def build_available_model_executors(
    project_root: Path,
    client: StructuredModelClient,
) -> dict[ExecutorKey, StepExecutor]:
    """Wire Step 1, 2, 4, and 6 to one provider-neutral model client.

    Step 3, Step 5 material operations, and Step 7 delivery remain separate
    executors because they require retrieval, filesystem tools, or delivery
    behavior rather than only a structured model call.
    """

    executors: dict[ExecutorKey, StepExecutor] = dict(
        build_structured_prompt_executors(client)
    )
    executors[1] = Step1VideoUnderstandingExecutor(
        ScriptVideoPreprocessor(project_root),
        client,
    )
    return executors


class Step3UnavailableExecutor:
    """Pause cleanly until the parallel RAG/Step 3 executor is integrated."""

    def execute(self, context: StepContext) -> StepResult:
        return StepResult(
            status="blocked",
            output=None,
            errors=[
                {
                    "code": "step_3_executor_not_configured",
                    "message": "Step 3/RAG executor is not configured in this runtime.",
                    "severity": "warning",
                    "step": 3,
                    "recoverable": True,
                    "details": {},
                }
            ],
        )


def build_manual_executors(
    project_root: Path,
    client: StructuredModelClient,
    *,
    step_3_executor: StepExecutor | None = None,
) -> dict[ExecutorKey, StepExecutor]:
    """Build Codex file-exchange execution around a pluggable Step 3."""

    executors = build_available_model_executors(project_root, client)
    executors[3] = step_3_executor or Step3UnavailableExecutor()
    executors[5] = Step5MaterialExecutor(MaterialProcessor(project_root))
    executors[7] = ProductionPlanExecutor()
    return executors


def build_deepseek_executors(
    project_root: Path,
    manual_client: StructuredModelClient,
    deepseek_client: StructuredModelClient,
    retriever: CaseRetriever,
) -> dict[ExecutorKey, StepExecutor]:
    """Build the temporary hybrid path: manual Step 1, DeepSeek text Steps."""

    executors: dict[ExecutorKey, StepExecutor] = dict(
        build_structured_prompt_executors(deepseek_client)
    )
    for route in ("single_image", "reference_video", "multi_image"):
        executors[(4, route)] = Step4ValidatedDesignExecutor(
            f"step_4.{route}", deepseek_client
        )
    executors[(6, "single_image")] = Step6ValidatedPromptExecutor(
        "step_6.single_image", deepseek_client
    )
    executors[(6, "reference_video")] = Step6ValidatedPromptExecutor(
        "step_6.reference_video", deepseek_client
    )
    executors[(6, "multi_image")] = Step6ValidatedPromptExecutor(
        "step_6.multi_image", deepseek_client
    )
    executors[1] = Step1VideoUnderstandingExecutor(
        ScriptVideoPreprocessor(project_root), manual_client
    )
    executors[3] = Step3RetrievalSelectionExecutor(retriever, deepseek_client)
    executors[5] = Step5MaterialExecutor(MaterialProcessor(project_root))
    executors[7] = ProductionPlanExecutor()
    return executors
