#!/usr/bin/env python3
"""Run the seven-day integrated opening diagnostic."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.integration import (
    render_seven_day_integration_report,
    run_seven_day_integration,
)


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else "v4"
    result = run_seven_day_integration(ROOT, version=version)
    docs_path = (
        ROOT
        / "docs"
        / "phase1"
        / "versions"
        / version
        / "SEVEN_DAY_INTEGRATION.md"
    )
    artifacts_path = (
        ROOT
        / "artifacts"
        / "phase1"
        / "versions"
        / version
        / "seven_day_integration.json"
    )
    docs_path.write_text(
        render_seven_day_integration_report(result), encoding="utf-8"
    )
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"diagnostic={docs_path.relative_to(ROOT)}")
    print(f"machine_result={artifacts_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
