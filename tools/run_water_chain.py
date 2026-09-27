#!/usr/bin/env python3
"""Run the first real S01 chain: move to water and drink."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plain_life.contracts import (  # noqa: E402
    CONTRACT_VERSION,
    ActionIntent,
    Location,
    PersonState,
    RunManifest,
)
from plain_life.core import SimulationCore, create_run  # noqa: E402
from plain_life.core_adapters import WorldClockAdapter  # noqa: E402
from plain_life.environment import (  # noqa: E402
    generate_environment,
    load_environment_baseline,
)
from plain_life.life_actions import (  # noqa: E402
    DrinkAtWaterHandler,
    MoveToLocationHandler,
    move_duration_seconds,
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _location_for_cell(world: Any, cell_index: int) -> Location:
    cell = world.cells[cell_index]
    return Location(
        x_m=cell.x * world.cell_size_m,
        y_m=cell.y * world.cell_size_m,
        cell_index=cell.index,
    )


def _distance_cells(world: Any, first: int, second: int) -> float:
    a = world.cells[first]
    b = world.cells[second]
    return math.hypot(a.x - b.x, a.y - b.y)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


def _render_report(result: dict[str, Any]) -> str:
    lines = [
        "# S01 第一条真实生活链：移动到水源并饮水",
        "",
        "这是 `integration_fixture`，不是正式历史，也不代表长期生存能力。",
        "",
        f"- 运行标识：`{result['run_id']}`",
        f"- 代码提交：`{result['code_commit']}`",
        f"- 人物位置：`{result['start_location']}` → `{result['water_location']}`",
        f"- 移动耗时：`{result['move_duration_seconds']}` 秒",
        f"- 饮水：`{result['litres']}` L",
        f"- 口渴：`{result['thirst_before']}` → `{result['thirst_after']}`",
        f"- 世界水量：`{result['water_volume_before_m3']}` → "
        f"`{result['water_volume_after_m3']}` m³",
        "",
        "## 关键事件",
        "",
        "| 世界秒 | 事件 | 行动 | 事实 |",
        "| ---: | --- | --- | --- |",
    ]
    for event in result["key_events"]:
        lines.append(
            f"| {event['world_seconds']} | `{event['event_type']}` | "
            f"`{event['action_id']}` | `{event['facts']}` |"
        )
    lines.extend(
        [
            "",
            "## 检查",
            "",
            "| 检查 | 结果 |",
            "| --- | --- |",
        ]
    )
    for key, value in result["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## 入口",
            "",
            "```powershell",
            f"py -3.12 tools\\run_water_chain.py --code-commit {result['code_commit']}",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-commit", default=None)
    arguments = parser.parse_args()
    code_commit = arguments.code_commit or _git_commit()

    baseline_path = (
        ROOT
        / "data"
        / "phase1"
        / "versions"
        / "v6"
        / "environment_baseline.json"
    )
    baseline = load_environment_baseline(baseline_path)
    world = generate_environment(baseline)
    drop_index = world.drop_point.index
    water_cell = min(
        world.water_cells,
        key=lambda cell: _distance_cells(world, drop_index, cell.index),
    )
    drop_location = _location_for_cell(world, drop_index)
    water_location = _location_for_cell(world, water_cell.index)
    move_seconds = move_duration_seconds(drop_location, water_location)
    scenario = {
        "mode": "integration_fixture",
        "scenario_id": "s01_water_chain",
        "drop_index": drop_index,
        "water_cell_index": water_cell.index,
        "move_seconds": move_seconds,
        "litres": 1.5,
    }
    scenario_fingerprint = _stable_fingerprint(scenario)
    parameter_fingerprint = _stable_fingerprint(
        {
            "walking_speed_m_per_second": 1.25,
            "drink_thirst_relief_per_litre": 0.35,
            "initial_thirst": 0.72,
        }
    )
    run_id = _stable_fingerprint(
        {
            "contract": CONTRACT_VERSION,
            "code_commit": code_commit,
            "scenario": scenario_fingerprint,
            "parameters": parameter_fingerprint,
        }
    )[:16]
    manifest = RunManifest(
        run_id=run_id,
        code_commit=code_commit,
        contract_version=CONTRACT_VERSION,
        scenario_id=scenario["scenario_id"],
        scenario_fingerprint=scenario_fingerprint,
        parameter_fingerprint=parameter_fingerprint,
        random_seed=int(world.seed),
        environment_fingerprint=world.initial_fingerprint,
        population_fingerprint="fixture-person-p000001",
        initial_day_of_year=world.start_day_of_year,
        start_world_seconds=0,
        day_seconds=86400,
        mode=scenario["mode"],
        unsupported_capabilities=[
            "disease",
            "death",
            "container_transport",
        ],
        dependency_versions={
            "python": "3.12",
            "sqlite": "stdlib",
        },
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    handlers = {
        "move_to_location": MoveToLocationHandler(),
        "drink_at_water": DrinkAtWaterHandler(),
    }
    core = create_run(manifest, handlers)
    world_adapter = WorldClockAdapter(world)
    world_adapter.bind(core)
    core.register_person(
        PersonState(
            person_id="p000001",
            household_id="h0001",
            location=drop_location,
            body={"hunger": 0.3, "thirst": 0.72},
        )
    )
    core.record_known_location(
        person_id="p000001",
        location=water_location,
        label="nearest_water",
        source_event_id="fixture_initial",
        certainty=1.0,
    )
    water_before = float(core.module_state("environment_world")["water_volume_m3"])

    move_intent = ActionIntent(
        action_id="move-to-water",
        person_id="p000001",
        action_type="move_to_location",
        formed_at_world_seconds=0,
        expected_duration_seconds=move_seconds,
        target={"location": water_location.to_dict()},
        known_conditions=["nearest_water known by p000001"],
        expected_outcome="arrive at water source",
    )
    core.submit_action(move_intent)
    core.start_action(move_intent.action_id)
    core.advance_to(move_seconds)

    drink_intent = ActionIntent(
        action_id="drink-at-water",
        person_id="p000001",
        action_type="drink_at_water",
        formed_at_world_seconds=move_seconds,
        expected_duration_seconds=120,
        target={
            "water_location": water_location.to_dict(),
            "water_module": "environment_world",
            "litres": 1.5,
        },
        known_conditions=["person arrived at water"],
        expected_outcome="drink 1.5 litres and reduce thirst",
    )
    core.submit_action(drink_intent)
    core.start_action(drink_intent.action_id)
    core.advance_to(move_seconds + 120)

    final_person = core.people["p000001"]
    drink_result = core.actions["drink-at-water"].result
    water_after = float(core.module_state("environment_world")["water_volume_m3"])
    key_types = {
        "action_started",
        "person_moved",
        "body_state_changed",
        "action_completed",
    }
    key_events = [
        event.to_dict()
        for event in core.events
        if event.event_type in key_types
    ]
    checks = {
        "move_completed": core.actions["move-to-water"].status == "completed",
        "arrived_at_water": (
            final_person.location.cell_index == water_location.cell_index
        ),
        "drink_completed": core.actions["drink-at-water"].status == "completed",
        "thirst_reduced": (
            float(final_person.body.get("thirst", 1.0)) < 0.72
        ),
        "world_water_reduced": water_after < water_before,
        "body_event_recorded": any(
            event.event_type == "body_state_changed" for event in core.events
        ),
        "event_query_has_move_and_drink": {
            event["action_id"]
            for event in core.query_events(person_id="p000001")
            if event["event_type"] == "action_completed"
        }
        == {"move-to-water", "drink-at-water"},
    }
    result = {
        "run_id": run_id,
        "code_commit": code_commit,
        "mode": scenario["mode"],
        "start_location": drop_location.to_dict(),
        "water_location": water_location.to_dict(),
        "move_duration_seconds": move_seconds,
        "litres": 1.5,
        "thirst_before": 0.72,
        "thirst_after": final_person.body.get("thirst"),
        "water_volume_before_m3": water_before,
        "water_volume_after_m3": water_after,
        "drink_result": drink_result,
        "key_events": key_events,
        "checks": checks,
    }
    output_dir = ROOT / "artifacts" / "s01" / "water_chain"
    _write_json(output_dir / "summary.json", result)
    _write_json(output_dir / "run_manifest.json", manifest.to_dict())
    _write_events_jsonl(
        output_dir / "events.jsonl",
        [event.to_dict() for event in core.events],
    )
    core.save(output_dir / "water_chain.sqlite3")
    report_path = ROOT / "docs" / "s01" / "S01_WATER_CHAIN.md"
    report_path.write_text(_render_report(result), encoding="utf-8")

    passed = all(checks.values())
    print(f"run_id={run_id}")
    print(f"water_chain_passed={passed}")
    print(f"report={report_path.relative_to(ROOT)}")
    print(f"summary={(output_dir / 'summary.json').relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

