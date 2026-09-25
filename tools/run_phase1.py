#!/usr/bin/env python3
"""Generate the fixed Phase 1 state and run the opening validation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.phase1 import run_phase1, write_phase1_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and validate the Phase 1 environment and population."
    )
    parser.add_argument(
        "--version",
        default="v2",
        help="Version directory under data/phase1/versions.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of test days. This is not formal world history.",
    )
    parser.add_argument(
        "--allow-failed",
        action="store_true",
        help="Write reports and return zero even when the gate is not PASS.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_phase1(ROOT, days=args.days, version=args.version)
    written = write_phase1_artifacts(ROOT, result, version=args.version)
    print(f"gate_status={result.audit['gate_status']}")
    print(f"blockers={result.audit['summary']['blockers']}")
    print(f"warnings={result.audit['summary']['warnings']}")
    for name, path in written.items():
        print(f"{name}={path.relative_to(ROOT)}")
    if result.audit["gate_status"] == "PASS" or args.allow_failed:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
