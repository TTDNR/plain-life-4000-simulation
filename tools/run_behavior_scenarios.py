#!/usr/bin/env python3
"""Run traceable v3 individual and household behavior scenarios."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.behavior import render_behavior_report, run_behavior_scenarios


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else "v4"
    result = run_behavior_scenarios(ROOT, version=version)
    docs_path = (
        ROOT
        / "docs"
        / "phase1"
        / "versions"
        / version
        / "BEHAVIOR_SCENARIOS.md"
    )
    artifacts_path = (
        ROOT
        / "artifacts"
        / "phase1"
        / "versions"
        / version
        / "behavior_scenarios.json"
    )
    docs_path.write_text(render_behavior_report(result), encoding="utf-8")
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"all_passed={result['all_passed']}")
    print(f"report={docs_path.relative_to(ROOT)}")
    print(f"machine_result={artifacts_path.relative_to(ROOT)}")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
