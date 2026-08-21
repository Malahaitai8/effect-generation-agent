from __future__ import annotations

import argparse
import json

from .project import scaffold_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="effect-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="检查 Agent 脚手架及当前实现阶段")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "status":
        print(json.dumps(scaffold_status(), ensure_ascii=False, indent=2))

