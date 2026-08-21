#!/usr/bin/env python3
"""Run the Step 3 main retrieval and persist a task-level case snapshot.

The stable CLI is scaffolded now; retrieval behavior will be implemented after
the task-result and case schemas are fixed.
"""

from __future__ import annotations

import argparse


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
    raise SystemExit("Case retrieval is not implemented in the scaffold stage.")


if __name__ == "__main__":
    main()

