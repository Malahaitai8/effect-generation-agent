"""Deterministic local semantic retrieval for the Step 3 case snapshot."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .model_execution import ModelExecutionBlocked


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


class EmbeddingEncoder(Protocol):
    model_id: str

    def encode_query(self, text: str) -> Sequence[float]: ...

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class SentenceTransformerEmbeddingEncoder:
    """Lazy optional adapter so the core runtime does not require PyTorch."""

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get(
            "EFFECT_AGENT_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self._model: Any | None = None
        self._lock = threading.RLock()

    def _load_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise ModelExecutionBlocked(
                    "Local RAG dependencies are missing; install the project with the 'rag' extra"
                ) from error
            try:
                self._model = SentenceTransformer(self.model_id)
            except Exception as error:
                raise ModelExecutionBlocked(
                    f"Embedding model cannot be loaded: {self.model_id}: {error}"
                ) from error
            return self._model

    def encode_query(self, text: str) -> Sequence[float]:
        with self._lock:
            model = self._load_model()
            method = getattr(model, "encode_query", model.encode)
            return method(text, normalize_embeddings=True).tolist()

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        with self._lock:
            model = self._load_model()
            method = getattr(model, "encode_document", model.encode)
            return method(list(texts), normalize_embeddings=True).tolist()


class CaseRetriever:
    """Validate all formal cases, rank them, and atomically persist Top K."""

    def __init__(
        self,
        cases_path: Path,
        schema_path: Path,
        encoder: EmbeddingEncoder,
        *,
        top_k: int = 6,
        embedding_weight: float = 0.85,
        tag_weight: float = 0.15,
    ) -> None:
        self.cases_path = cases_path.resolve()
        self.schema_path = schema_path.resolve()
        self.encoder = encoder
        self.top_k = top_k
        self.embedding_weight = embedding_weight
        self.tag_weight = tag_weight

    def retrieve(
        self,
        step_2_output: Mapping[str, Any],
        snapshot_path: Path,
    ) -> dict[str, Any]:
        source_bytes = self.cases_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        reusable = self._load_reusable(snapshot_path, source_sha256)
        if reusable is not None:
            return reusable

        cases = self._load_cases(source_bytes)
        query = self._query(step_2_output)
        document_texts = [self._case_text(case) for case in cases]
        query_vector = self.encoder.encode_query(query["text"])
        document_vectors = self.encoder.encode_documents(document_texts)
        if len(document_vectors) != len(cases):
            raise ModelExecutionBlocked("Embedding encoder returned the wrong document count")

        ranked: list[dict[str, Any]] = []
        query_tags = set(query["tags"])
        for case, vector in zip(cases, document_vectors):
            embedding_score = self._cosine(query_vector, vector)
            tag_score = self._jaccard(query_tags, self._case_tags(case))
            score = self.embedding_weight * embedding_score + self.tag_weight * tag_score
            ranked.append(
                {
                    "case_id": case["case_id"],
                    "score": round(score, 8),
                    "score_components": {
                        "embedding_cosine": round(embedding_score, 8),
                        "tag_jaccard": round(tag_score, 8),
                    },
                    "case": case,
                }
            )
        ranked.sort(key=lambda item: (-item["score"], item["case_id"]))
        snapshot = {
            "snapshot_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "retrieval": {
                "method": "embedding_cosine_plus_tag_jaccard",
                "embedding_model": self.encoder.model_id,
                "embedding_weight": self.embedding_weight,
                "tag_weight": self.tag_weight,
                "top_k": self.top_k,
                "case_source": str(self.cases_path),
                "case_source_sha256": source_sha256,
                "valid_case_count": len(cases),
            },
            "candidates": ranked[: self.top_k],
        }
        self._write_json(snapshot_path, snapshot)
        return snapshot

    def _load_cases(self, source_bytes: bytes) -> list[dict[str, Any]]:
        try:
            schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            cases = [
                json.loads(line)
                for line in source_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelExecutionBlocked(f"Case data cannot be read: {error}") from error
        seen: set[str] = set()
        for case in cases:
            errors = list(validator.iter_errors(case))
            if errors:
                raise ModelExecutionBlocked(
                    f"Invalid RAG case {case.get('case_id', '<unknown>')}: {errors[0].message}"
                )
            if case["case_id"] in seen:
                raise ModelExecutionBlocked(f"Duplicate RAG case ID: {case['case_id']}")
            seen.add(case["case_id"])
        return cases

    def _load_reusable(
        self, snapshot_path: Path, source_sha256: str
    ) -> dict[str, Any] | None:
        if not snapshot_path.exists():
            return None
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            retrieval = snapshot["retrieval"]
            candidates = snapshot["candidates"]
            valid = (
                snapshot.get("snapshot_version") == "1.0"
                and retrieval["case_source_sha256"] == source_sha256
                and retrieval["embedding_model"] == self.encoder.model_id
                and retrieval["top_k"] == self.top_k
                and retrieval["embedding_weight"] == self.embedding_weight
                and retrieval["tag_weight"] == self.tag_weight
                and isinstance(candidates, list)
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return None
        return snapshot if valid else None

    @classmethod
    def _query(cls, output: Mapping[str, Any]) -> dict[str, Any]:
        primary = output.get("primary_selling_point")
        secondary = output.get("secondary_selling_points", [])
        if not isinstance(primary, Mapping) or not isinstance(secondary, list):
            raise ModelExecutionBlocked("Step 2 selling-point output is incomplete")
        points = [primary, *[point for point in secondary if isinstance(point, Mapping)]]
        descriptions = [str(point.get("description", "")).strip() for point in points]
        tags = [
            str(tag)
            for point in points
            for tag in point.get("tags", [])
            if isinstance(tag, str)
        ]
        text_parts = [part for part in descriptions if part] + tags
        if not text_parts:
            raise ModelExecutionBlocked("Step 2 did not provide retrievable selling-point text")
        return {
            "primary_selling_point": dict(primary),
            "secondary_selling_points": [dict(point) for point in points[1:]],
            "tags": list(dict.fromkeys(tags)),
            "text": "\n".join(text_parts),
        }

    @staticmethod
    def _case_text(case: Mapping[str, Any]) -> str:
        points = [case["primary_selling_point"], *case["secondary_selling_points"]]
        return "\n".join(
            [point["description"] for point in points]
            + [tag for point in points for tag in point["tags"]]
        )

    @staticmethod
    def _case_tags(case: Mapping[str, Any]) -> set[str]:
        points = [case["primary_selling_point"], *case["secondary_selling_points"]]
        return {tag for point in points for tag in point["tags"]}

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            raise ModelExecutionBlocked("Embedding vectors have incompatible dimensions")
        numerator = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
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
