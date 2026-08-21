#!/usr/bin/env python3
"""Generate or standardize Step 5 image materials.

The concrete model client and request schema are intentionally deferred until
the task-result schema and model capability contract are fixed.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="Path to a material-generation request JSON")
    parser.add_argument("--output-dir", help="Directory for generated material files")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.request or not args.output_dir:
        parser.error("--request and --output-dir are required for execution")
    raise SystemExit("Image generation is not implemented in the scaffold stage.")


if __name__ == "__main__":
    main()

