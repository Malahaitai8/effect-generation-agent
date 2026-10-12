#!/usr/bin/env python3
"""Run Step 3A local retrieval and persist a task-level case snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from effect_generation_agent.retrieval import (  # noqa: E402
    CaseRetriever,
    SentenceTransformerEmbeddingEncoder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", help="Path to a structured retrieval query JSON")
    parser.add_argument("--cases", help="Path to the case JSONL data")
    parser.add_argument("--snapshot", help="Path for the task-level snapshot JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.query or not args.cases or not args.snapshot:
        parser.error("--query, --cases, and --snapshot are required for execution")
    with Path(args.query).resolve().open(encoding="utf-8") as query_file:
        step_2_output = json.load(query_file)
    if not isinstance(step_2_output, dict):
        parser.error("--query must contain one Step 2 output JSON object")
    retriever = CaseRetriever(
        Path(args.cases),
        PROJECT_ROOT / "rag" / "case.schema.json",
        SentenceTransformerEmbeddingEncoder(),
    )
    snapshot = retriever.retrieve(step_2_output, Path(args.snapshot))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
