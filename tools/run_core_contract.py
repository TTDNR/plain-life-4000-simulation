#!/usr/bin/env python3
"""Run the S01-1 contract fixture through the unified simulation core."""

from __future__ import annotations

import hashlib
import json
import os
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
    Commitment,
    ItemBatch,
    Location,
    PersonState,
    RunManifest,
    SocialResponse,
)
from plain_life.core import (  # noqa: E402
    SimulationCore,
    TransferItemHandler,
    create_run,
)


def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def _manifest(
    fixture: dict[str, Any],
    *,
    run_id: str,
    code_commit: str,
    scenario_fingerprint: str,
    parameter_fingerprint: str,
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        code_commit=code_commit,
        contract_version=CONTRACT_VERSION,
        scenario_id=fixture["scenario_id"],
        scenario_fingerprint=scenario_fingerprint,
        parameter_fingerprint=parameter_fingerprint,
        random_seed=int(fixture["seed"]),
        environment_fingerprint=fixture["environment_fingerprint"],
        population_fingerprint=fixture["population_fingerprint"],
        initial_day_of_year=int(fixture["initial_day_of_year"]),
        start_world_seconds=int(fixture["start_world_seconds"]),
        day_seconds=int(fixture["day_seconds"]),
        mode=fixture["mode"],
        unsupported_capabilities=list(
            fixture["unsupported_capabilities"]
        ),
        dependency_versions=dict(fixture["dependency_versions"]),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def _register_fixture(core: SimulationCore, fixture: dict[str, Any]) -> None:
    for item in fixture["people"]:
        core.register_person(
            PersonState(
                person_id=item["person_id"],
                household_id=item["household_id"],
                location=Location.from_dict(item["location"]),  # type: ignore[arg-type]
                body=dict(item["body"]),
            )
        )
    for item in fixture["items"]:
        core.add_item(ItemBatch.from_dict(item))
    for item in fixture["knowledge"]:
        core.record_knowledge(
            person_id=item["person_id"],
            subject=item["subject"],
            stage=item["stage"],
            source_event_id="fixture-initial",
            certainty=float(item["certainty"]),
        )
    for item in fixture["known_locations"]:
        core.record_known_location(
            person_id=item["person_id"],
            location=Location.from_dict(item["location"]),  # type: ignore[arg-type]
            label=item["label"],
            source_event_id="fixture-initial",
            certainty=float(item["certainty"]),
        )
    for item in fixture["relationships"]:
        core.set_relationship(
            person_id=item["person_id"],
            other_person_id=item["other_person_id"],
            domain=item["domain"],
            value=float(item["value"]),
        )
    for item in fixture["commitments"]:
        core.add_commitment(
            Commitment(
                commitment_id=item["commitment_id"],
                request_id=item["request_id"],
                responder_id=item["responder_id"],
                beneficiary_id=item["beneficiary_id"],
                service_or_item=item["service_or_item"],
                quantity=item.get("quantity"),
                unit=item.get("unit"),
                due_start_world_seconds=item.get("due_start_world_seconds"),
                due_end_world_seconds=item.get("due_end_world_seconds"),
                status=item["status"],
                source_response_id=item["source_response_id"],
                details=dict(item.get("details", {})),
            )
        )
    for item in fixture["scheduled_events"]:
        core.schedule_event(
            due_world_seconds=int(item["due_world_seconds"]),
            event_type=item["event_type"],
            actor_ids=list(item.get("actor_ids", [])),
            facts=dict(item.get("facts", {})),
            observed_by=list(item.get("observed_by", [])),
            location=Location.from_dict(item.get("location")),
        )
    core.emit_event(
        event_type="fixture_state_loaded",
        actor_ids=["p1", "p2", "p3"],
        action_id=None,
        facts={
            "scenario_id": fixture["scenario_id"],
            "known_locations": len(fixture["known_locations"]),
            "commitments": len(fixture["commitments"]),
        },
        observed_by=["p1", "p2", "p3"],
    )


def _intent_from_fixture(
    fixture: dict[str, Any],
    key: str,
    *,
    formed_at_world_seconds: int,
) -> ActionIntent:
    definition = fixture["actions"][key]
    return ActionIntent(
        action_id=definition["action_id"],
        person_id=definition["person_id"],
        action_type=definition["action_type"],
        formed_at_world_seconds=formed_at_world_seconds,
        expected_duration_seconds=int(
            definition["expected_duration_seconds"]
        ),
        target=dict(definition["target"]),
        known_conditions=list(definition["known_conditions"]),
        expected_outcome=definition["expected_outcome"],
        requested_participants=list(
            definition.get("requested_participants", [])
        ),
    )


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


def _render_report(run: dict[str, Any]) -> str:
    lines = [
        "# S01-1 契约与执行核心夹具",
        "",
        "这是 `contract_fixture`，不是正式世界历史，也不代表生存路径通过。",
        "",
        f"- 运行标识：`{run['run_id']}`",
        f"- 代码提交：`{run['code_commit']}`",
        f"- 模式：`{run['mode']}`",
        f"- 世界时间：`{run['final_world_seconds']}` 秒",
        "",
        "## 验收检查",
        "",
        "| 检查 | 结果 |",
        "| --- | --- |",
    ]
    for key, value in run["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## 关键事件",
            "",
            "| 序号 | 世界秒 | 事件 | 行动 | 事实 |",
            "| ---: | ---: | --- | --- | --- |",
        ]
    )
    for event in run["example_events"]:
        lines.append(
            f"| {event['sequence']} | {event['world_seconds']} | "
            f"`{event['event_type']}` | "
            f"`{event['action_id']}` | `{event['facts']}` |"
        )
    lines.extend(
        [
            "",
            "## 状态结果",
            "",
            f"- 物品批次：`{run['final_items']}`",
            f"- 活跃行动：`{run['active_actions_after_restore']}`",
            f"- 待处理事件：`{run['pending_events_after_restore']}`",
            f"- 恢复后随机状态一致：`{run['checks']['random_state_restored']}`",
            f"- 未来照护承诺恢复：`{run['checks']['future_commitment_restored']}`",
            "",
            "## 入口",
            "",
            "```powershell",
            "py -3.12 tools\\run_core_contract.py",
            "```",
            "",
            "机器结果和 SQLite 存档位于 `artifacts/s01/contract_fixture/`。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    fixture_path = ROOT / "data" / "s01" / "contract_fixture.json"
    fixture = _load_fixture(fixture_path)
    scenario_fingerprint = _stable_fingerprint(
        {
            "scenario_id": fixture["scenario_id"],
            "people": fixture["people"],
            "items": fixture["items"],
            "actions": fixture["actions"],
        }
    )
    parameter_fingerprint = _stable_fingerprint(
        {
            "seed": fixture["seed"],
            "day_seconds": fixture["day_seconds"],
            "unsupported": fixture["unsupported_capabilities"],
        }
    )
    code_commit = _git_commit()
    run_id = _stable_fingerprint(
        {
            "contract": CONTRACT_VERSION,
            "code_commit": code_commit,
            "scenario": scenario_fingerprint,
            "parameters": parameter_fingerprint,
        }
    )[:16]
    manifest = _manifest(
        fixture,
        run_id=run_id,
        code_commit=code_commit,
        scenario_fingerprint=scenario_fingerprint,
        parameter_fingerprint=parameter_fingerprint,
    )
    handlers = {"transfer_item": TransferItemHandler()}
    core = create_run(manifest, handlers)
    _register_fixture(core, fixture)

    interrupted = core.submit_action(
        _intent_from_fixture(
            fixture,
            "interrupted_attempt",
            formed_at_world_seconds=0,
        )
    )
    core.start_action(interrupted.action_id)
    core.advance_to(1800)
    core.interrupt_action(interrupted.action_id, reason="fixture_interruption")

    restored = core.submit_action(
        _intent_from_fixture(
            fixture,
            "restored_attempt",
            formed_at_world_seconds=1800,
        )
    )
    core.start_action(restored.action_id)

    competing = core.submit_action(
        _intent_from_fixture(
            fixture,
            "competing_attempt",
            formed_at_world_seconds=1800,
        )
    )
    core.start_action(competing.action_id)
    competing = core.actions[competing.action_id]
    rng_before_save = core.random.getstate()
    snapshot_before_restore = core.snapshot()
    output_dir = ROOT / "artifacts" / "s01" / "contract_fixture"
    before_save = output_dir / "before_restore.sqlite3"
    after_save = output_dir / "after_restore.sqlite3"
    core.save(before_save)

    loaded = SimulationCore.load(
        before_save,
        handlers=handlers,
    )
    restored_before_continue = loaded.actions[restored.action_id]
    restored_was_active = restored_before_continue.status == "active"
    pending_events_before_continue = [
        event.to_dict() for event in loaded.scheduled_events
    ]
    rng_after_load = loaded.random.getstate()
    loaded.advance_to(7200)
    restored_after_continue = loaded.actions[restored.action_id]
    loaded.save(after_save)

    source_batch = loaded.items["food-1"]
    output_batches = sorted(
        (
            batch
            for batch in loaded.items.values()
            if batch.batch_id.startswith("food-1:transfer:")
        ),
        key=lambda batch: batch.batch_id,
    )
    output_quantity = sum(batch.quantity for batch in output_batches)
    final_quantity = source_batch.quantity + output_quantity
    restored_person = loaded.people["p1"]
    pending_events = pending_events_before_continue
    example_types = {
        "action_intent_submitted",
        "action_interrupted",
        "action_blocked",
        "item_transferred",
        "action_completed",
    }
    example_events = [
        event.to_dict()
        for event in loaded.events
        if event.event_type in example_types
    ]
    checks = {
        "interrupted_action_has_no_output": (
            not core.actions[interrupted.action_id].output_batch_ids
        ),
        "competing_action_blocked": competing.status == "blocked",
        "restored_action_was_active": restored_was_active,
        "restored_action_completed_after_load": (
            restored_after_continue.status == "completed"
        ),
        "item_quantity_conserved": abs(final_quantity - 1.0) < 1e-9,
        "only_one_transfer_output": len(output_batches) == 1,
        "random_state_restored": rng_before_save == rng_after_load,
        "future_commitment_restored": (
            "commitment-care-1" in loaded.commitments
        ),
        "knowledge_restored": (
            loaded.perceived_state("p1").knowledge[0]["subject"]
            == "location:water_source"
        ),
        "location_and_body_restored": (
            restored_person.location.cell_index == 102
            and restored_person.body.get("hunger") == 0.25
        ),
        "pending_event_restored": bool(pending_events),
        "pending_event_processed_after_restore": any(
            event.event_type == "fixture_pending_event"
            for event in loaded.events
        ),
        "all_events_have_run_id": all(
            event.run_id == run_id for event in loaded.events
        ),
    }
    run = {
        "run_id": run_id,
        "code_commit": code_commit,
        "mode": fixture["mode"],
        "final_world_seconds": loaded.clock.current_world_seconds,
        "checks": checks,
        "example_events": example_events[:20],
        "final_items": [
            batch.to_dict() for batch in loaded.items.values()
        ],
        "active_actions_after_restore": [
            action.action_id
            for action in loaded.actions.values()
            if action.status == "active"
        ],
        "pending_events_after_restore": pending_events,
        "snapshot_before_restore": snapshot_before_restore,
        "outputs": {
            "before_restore": str(before_save.relative_to(ROOT)),
            "after_restore": str(after_save.relative_to(ROOT)),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "run_manifest.json", manifest.to_dict())
    _write_json(output_dir / "summary.json", run)
    _write_events_jsonl(output_dir / "events.jsonl", [
        event.to_dict() for event in loaded.events
    ])
    report_path = ROOT / "docs" / "s01" / "S01_CONTRACT_FIXTURE.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(run), encoding="utf-8")

    passed = all(checks.values())
    print(f"run_id={run_id}")
    print(f"contract_fixture_passed={passed}")
    print(f"report={report_path.relative_to(ROOT)}")
    print(f"summary={ (output_dir / 'summary.json').relative_to(ROOT) }")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
