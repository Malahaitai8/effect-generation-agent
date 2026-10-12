"""Structured model execution shared by prompt-driven workflow Steps."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .workflow import StepContext, StepResult


@dataclass(frozen=True)
class StructuredModelRequest:
    """One prompt plus validated task inputs and optional media references."""

    task_id: str
    step: int
    prompt_key: str
    prompt: str
    inputs: Mapping[str, Any]
    media_refs: tuple[str, ...] = ()
    validate_as_step_output: bool = True


class StructuredModelClient(Protocol):
    """Provider-neutral boundary for a model that returns one JSON object."""

    def generate(self, request: StructuredModelRequest) -> Mapping[str, Any]:
        """Run the model and return only the current Step business output."""


class ModelExecutionBlocked(RuntimeError):
    """A recoverable provider or capability problem prevented execution."""


class ManualResultRequired(ModelExecutionBlocked):
    """Codex must supply a response for an exported request."""

    def __init__(self, request_path: Path) -> None:
        self.request_path = request_path
        super().__init__(f"Manual result required: {request_path}")


class ManualExchangeModelClient:
    """Exchange structured model requests and Codex responses through files."""

    def __init__(
        self,
        outputs_root: Path,
        schema_version: str,
        *,
        namespace: str | None = None,
    ) -> None:
        self.outputs_root = outputs_root.resolve()
        self.schema_version = schema_version
        if namespace and not namespace.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Unsafe manual exchange namespace: {namespace}")
        self.namespace = namespace

    def generate(self, request: StructuredModelRequest) -> Mapping[str, Any]:
        request_dir = self._request_dir(request.task_id, request.step)
        request_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "request_version": "1.0",
            "schema_version": self.schema_version,
            "task_id": request.task_id,
            "step": request.step,
            "output_target": f"workflow.step_{request.step}.output",
            "prompt_key": request.prompt_key,
            "prompt": request.prompt,
            "inputs": request.inputs,
            "media_refs": list(request.media_refs),
        }
        identity_payload = copy.deepcopy(payload)
        preprocessing = identity_payload.get("inputs", {}).get("video_preprocessing")
        if isinstance(preprocessing, dict):
            # Step 1 changes this operational flag from false to true on resume,
            # while the actual media and requested business result stay identical.
            preprocessing.pop("reused", None)
        request_id = hashlib.sha256(
            json.dumps(identity_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        payload["request_id"] = request_id
        request_path = request_dir / "request.json"
        response_path = request_dir / "response.json"
        self._write_json(request_path, payload)
        if not response_path.exists():
            raise ManualResultRequired(request_path)
        response = self._read_json(response_path)
        if response.get("request_id") != request_id:
            raise ManualResultRequired(request_path)
        output = response.get("output")
        if not isinstance(output, dict):
            raise ModelExecutionBlocked(
                f"Manual response output must be a JSON object: {response_path}"
            )
        return output

    def pending_request(self, task_id: str, step: int) -> dict[str, Any]:
        request_path = self._request_dir(task_id, step) / "request.json"
        if not request_path.exists():
            raise ModelExecutionBlocked(
                f"No manual request exists for task {task_id} Step {step}"
            )
        return self._read_json(request_path)

    def submit(self, task_id: str, step: int, output: Mapping[str, Any]) -> Path:
        request = self.pending_request(task_id, step)
        response_path = self._request_dir(task_id, step) / "response.json"
        self._write_json(
            response_path,
            {"request_id": request["request_id"], "output": dict(output)},
        )
        return response_path

    def _request_dir(self, task_id: str, step: int) -> Path:
        root = self.outputs_root / task_id / "manual"
        if self.namespace:
            root = root / self.namespace
        return root / f"step-{step}"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as input_file:
            value = json.load(input_file)
        if not isinstance(value, dict):
            raise ModelExecutionBlocked(f"Expected a JSON object: {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
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
                json.dump(value, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise


DeepSeekTransport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]]
StepOutputValidator = Callable[[str, int, dict[str, Any]], None]


class DeepSeekStructuredModelClient:
    """Call a DeepSeek-compatible chat endpoint and return validated JSON."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 60.0,
        output_validator: StepOutputValidator | None = None,
        transport: DeepSeekTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout_seconds = timeout_seconds
        self.output_validator = output_validator
        self.transport = transport or self._urlopen_transport

    def generate(self, request: StructuredModelRequest) -> Mapping[str, Any]:
        if not self.api_key:
            raise ModelExecutionBlocked("DEEPSEEK_API_KEY is not configured")
        messages = [
            {
                "role": "system",
                "content": "You execute one workflow step. Return only one JSON object and no Markdown.",
            },
            {
                "role": "user",
                "content": self._request_content(request),
            },
        ]
        first_content = self._chat(messages)
        try:
            return self._parse_and_validate(request, first_content)
        except (ValueError, json.JSONDecodeError) as error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": first_content},
                {
                    "role": "user",
                    "content": (
                        "The previous response is invalid. Return a corrected JSON object only. "
                        f"Validation error: {error}"
                    ),
                },
            ]
            repaired_content = self._chat(repair_messages)
            try:
                return self._parse_and_validate(request, repaired_content)
            except (ValueError, json.JSONDecodeError) as repair_error:
                raise ModelExecutionBlocked(
                    f"DeepSeek returned invalid structured output after one repair: {repair_error}"
                ) from repair_error

    def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self.transport(
                f"{self.base_url}/chat/completions",
                headers,
                payload,
                self.timeout_seconds,
            )
            content = response["choices"][0]["message"]["content"]
        except ModelExecutionBlocked:
            raise
        except (KeyError, IndexError, TypeError) as error:
            raise ModelExecutionBlocked("DeepSeek response is missing message content") from error
        if not isinstance(content, str) or not content.strip():
            raise ModelExecutionBlocked("DeepSeek returned empty message content")
        return content

    def _parse_and_validate(
        self,
        request: StructuredModelRequest,
        content: str,
    ) -> Mapping[str, Any]:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("response must be a JSON object")
        if self.output_validator is not None and request.validate_as_step_output:
            try:
                self.output_validator(request.task_id, request.step, value)
            except Exception as error:
                raise ValueError(str(error)) from error
        return value

    @staticmethod
    def _request_content(request: StructuredModelRequest) -> str:
        return "\n\n".join(
            [
                request.prompt,
                "## Runtime input JSON",
                json.dumps(request.inputs, ensure_ascii=False, indent=2),
            ]
        )

    @staticmethod
    def _urlopen_transport(
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise ModelExecutionBlocked(
                f"DeepSeek HTTP {error.code}: {detail or error.reason}"
            ) from error
        except urllib.error.URLError as error:
            raise ModelExecutionBlocked(f"DeepSeek request failed: {error.reason}") from error
        except (TimeoutError, socket.timeout) as error:
            raise ModelExecutionBlocked("DeepSeek request timed out") from error
        except json.JSONDecodeError as error:
            raise ModelExecutionBlocked("DeepSeek HTTP response is not JSON") from error
        if not isinstance(result, dict):
            raise ModelExecutionBlocked("DeepSeek HTTP response must be a JSON object")
        return result


class StructuredPromptExecutor:
    """Load one Prompt, call a structured model client, and return StepResult."""

    def __init__(self, prompt_key: str, client: StructuredModelClient) -> None:
        self.prompt_key = prompt_key
        self.client = client

    def execute(self, context: StepContext) -> StepResult:
        try:
            request = self.build_request(context)
            output = self.client.generate(request)
        except ManualResultRequired as error:
            return StepResult(
                status="needs_input",
                output=None,
                errors=[
                    {
                        "code": "manual_result_required",
                        "message": str(error),
                        "severity": "info",
                        "step": context.step,
                        "recoverable": True,
                        "details": {"request_path": str(error.request_path)},
                    }
                ],
            )
        except ModelExecutionBlocked as error:
            return StepResult(
                status="blocked",
                output=None,
                errors=[
                    {
                        "code": "model_execution_blocked",
                        "message": str(error),
                        "severity": "warning",
                        "step": context.step,
                        "recoverable": True,
                        "details": {"prompt_key": self.prompt_key},
                    }
                ],
            )
        if not isinstance(output, Mapping):
            raise TypeError("Structured model output must be a JSON object")
        return StepResult(status="completed", output=copy.deepcopy(dict(output)))

    def build_request(self, context: StepContext) -> StructuredModelRequest:
        try:
            prompt_path = context.resources.prompt_paths[self.prompt_key]
        except KeyError as error:
            raise ModelExecutionBlocked(
                f"Prompt resource is not configured: {self.prompt_key}"
            ) from error
        with open(prompt_path, encoding="utf-8") as prompt_file:
            prompt = prompt_file.read()
        inputs = copy.deepcopy(dict(context.inputs))
        if context.step in {4, 6}:
            inputs["_runtime"] = {
                "model_capabilities": copy.deepcopy(
                    dict(context.resources.model_capabilities)
                ),
                "case_snapshot": self._read_case_snapshot(context),
            }
        return StructuredModelRequest(
            task_id=context.task_id,
            step=context.step,
            prompt_key=self.prompt_key,
            prompt=prompt,
            inputs=inputs,
        )

    @staticmethod
    def _read_case_snapshot(context: StepContext) -> Mapping[str, Any] | None:
        reference = context.inputs.get("artifacts.case_snapshot_path")
        reader = context.resources.case_snapshot_reader
        if not reference or reader is None:
            return None
        try:
            snapshot = reader.read(reference)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ModelExecutionBlocked(
                f"Case snapshot cannot be read: {reference}: {error}"
            ) from error
        case_ids = set(
            context.inputs.get("workflow.step_3.output", {}).get("case_ids", [])
        )
        candidates = snapshot.get("candidates") if isinstance(snapshot, Mapping) else None
        if isinstance(candidates, list) and case_ids:
            return {
                **dict(snapshot),
                "candidates": [
                    candidate
                    for candidate in candidates
                    if isinstance(candidate, Mapping)
                    and candidate.get("case_id") in case_ids
                ],
            }
        cases = snapshot.get("cases") if isinstance(snapshot, Mapping) else None
        if isinstance(cases, list) and case_ids:
            return {
                **dict(snapshot),
                "cases": [
                    case
                    for case in cases
                    if isinstance(case, Mapping) and case.get("case_id") in case_ids
                ],
            }
        return copy.deepcopy(dict(snapshot))


def build_structured_prompt_executors(
    client: StructuredModelClient,
) -> dict[int | tuple[int, str], StructuredPromptExecutor]:
    """Build the prompt-driven executors that share one model client."""

    return {
        2: StructuredPromptExecutor("step_2", client),
        (4, "single_image"): StructuredPromptExecutor(
            "step_4.single_image", client
        ),
        (4, "reference_video"): StructuredPromptExecutor(
            "step_4.reference_video", client
        ),
        (4, "multi_image"): StructuredPromptExecutor(
            "step_4.multi_image", client
        ),
        (6, "single_image"): StructuredPromptExecutor(
            "step_6.single_image", client
        ),
        (6, "reference_video"): StructuredPromptExecutor(
            "step_6.reference_video", client
        ),
        (6, "multi_image"): StructuredPromptExecutor(
            "step_6.multi_image", client
        ),
    }
