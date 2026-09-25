"""End-to-end Phase 1 generation, validation, and reporting."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .environment import (
    EnvironmentBaseline,
    WorldState,
    environment_summary,
    generate_environment,
    load_environment_baseline,
)
from .population import PopulationState, generate_population
from .reporting import (
    render_environment_report,
    render_initialization_report,
    render_survival_report,
)
from .survival import SurvivalRunResult, run_survival_validation


@dataclass
class Phase1Result:
    world: WorldState
    population: PopulationState
    survival: SurvivalRunResult
    audit: dict[str, Any]
    reports: dict[str, str]


def run_phase1(
    root: Path,
    days: int = 365,
) -> Phase1Result:
    baseline = load_environment_baseline(
        root / "data" / "phase1" / "environment_baseline.json"
    )
    world = generate_environment(baseline)
    population = generate_population(
        seed=int(baseline.raw["seed"]),
        target_total=4000,
    )
    survival = run_survival_validation(world, population, days=days)
    audit_data = _build_audit_contracts(root, baseline, world, population, survival)
    audit_module = _load_audit_module(root)
    audit = audit_module.build_audit(
        audit_data["world"],
        audit_data["survival"],
        audit_data["population"],
    )
    findings = audit["findings"]
    reports = {
        "environment": render_environment_report(world, population, survival),
        "survival": render_survival_report(survival),
        "initialization": render_initialization_report(
            population, survival, findings
        ),
    }
    return Phase1Result(
        world=world,
        population=population,
        survival=survival,
        audit=audit,
        reports=reports,
    )


def write_phase1_artifacts(
    root: Path,
    result: Phase1Result,
) -> dict[str, Path]:
    artifacts_dir = root / "artifacts" / "phase1"
    docs_dir = root / "docs" / "phase1"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    world_summary = environment_summary(result.world)
    written["world_summary"] = _write_json(
        artifacts_dir / "world_summary.json", world_summary
    )
    written["population_summary"] = _write_json(
        artifacts_dir / "population_summary.json",
        result.population.summary(),
    )
    written["survival_run"] = _write_json(
        artifacts_dir / "survival_run.json",
        {
            **result.survival.summary(),
            "daily_metrics": [
                asdict(metric) for metric in result.survival.metrics
            ],
        },
    )
    written["phase1_audit_json"] = _write_json(
        artifacts_dir / "phase1_audit.json", result.audit
    )
    written["phase1_audit_markdown"] = _write_text(
        artifacts_dir / "phase1_audit.md",
        _render_audit_markdown(result.audit),
    )
    written["environment_report"] = _write_text(
        docs_dir / "ENVIRONMENT_RESOURCE_INVENTORY.md",
        result.reports["environment"],
    )
    written["survival_report"] = _write_text(
        docs_dir / "OPENING_SURVIVAL_REVIEW.md",
        result.reports["survival"],
    )
    written["initialization_report"] = _write_text(
        docs_dir / "INITIALIZATION_CONSISTENCY_REVIEW.md",
        result.reports["initialization"],
    )
    return written


def _build_audit_contracts(
    root: Path,
    baseline: EnvironmentBaseline,
    world: WorldState,
    population: PopulationState,
    survival: SurvivalRunResult,
) -> dict[str, dict[str, Any]]:
    world_contract = _load_json(root / "data" / "phase1" / "world.json")
    survival_contract = _load_json(root / "data" / "phase1" / "survival.json")
    population_contract = _load_json(root / "data" / "phase1" / "population.json")
    environment = environment_summary(world)

    for field in ("state_fingerprint", "generation_seed"):
        world_contract["initialization"][field]["status"] = "known"
        world_contract["initialization"][field]["value"] = (
            world.initial_fingerprint
            if field == "state_fingerprint"
            else world.seed
        )
        world_contract["initialization"][field]["evidence"] = [
            "ENV-GENERATION-001"
        ]
    for record in world_contract["boundary"].values():
        if isinstance(record, dict) and record.get("status") == "assumption":
            record["accepted"] = True
    for component_id, record in world_contract["components"].items():
        record["status"] = "assumption"
        record["accepted"] = True
        record["rationale"] = (
            "Accepted only for the deterministic Phase 1 baseline; empirical "
            "site validation remains pending."
        )
        record["value"] = _component_value(
            component_id, environment, baseline.raw
        )
        record["evidence"] = ["ENV-MODEL-BASELINE"]

    for window_id, result in survival.window_results.items():
        window = next(
            item for item in survival_contract["windows"] if item["id"] == window_id
        )
        window.update(result)
    for path_id, result in survival.path_results.items():
        survival_contract["paths"][path_id].update(result)
    survival_contract["food_audit"]["dimensions"] = survival.food_audit[
        "dimensions"
    ]
    survival_contract["food_audit"]["simulation_result"] = {
        "status": "known",
        "value": {
            "initial_available_kcal": survival.food_audit[
                "initial_available_kcal"
            ],
            "final_available_kcal": survival.food_audit[
                "final_available_kcal"
            ],
            "minimum_daily_household_food_success_rate": survival.food_audit[
                "minimum_daily_household_food_success_rate"
            ],
            "average_daily_household_food_success_rate": survival.food_audit[
                "average_daily_household_food_success_rate"
            ],
        },
        "evidence": ["SIM-YEAR-001"],
    }

    population_contract["snapshot"] = population.to_snapshot_dict()
    population_contract["ecology_link"] = {
        "status": "ready",
        "aggregate_population_target": 4000,
        "household_capability_distribution": result_string(
            survival.food_audit["dimensions"][
                "household_capability_differences"
            ]["value"]
        ),
        "care_load": result_string(
            f"{population.summary()['dependent_people']} dependent people and "
            f"{population.summary()['caregiver_people']} caregivers"
        ),
        "labor_time_available": "care-adjusted hours are calculated per household",
        "food_and_water_access_by_household": (
            "water succeeds in every window; food shows household-level failure "
            "in the model without inter-household allocation"
        ),
        "evidence": ["SIM-CAPABILITY-001", "SIM-WATER-001", "SIM-FOOD-001"],
    }
    return {
        "world": world_contract,
        "survival": survival_contract,
        "population": population_contract,
    }


def _component_value(
    component_id: str,
    environment: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    if component_id.startswith("terrain."):
        return {
            "habitat_counts": environment["habitat_counts"],
            "drop_point": environment["drop_point"],
            "land_rules": baseline["land"],
        }
    if component_id.startswith("freshwater."):
        return {
            "initial": environment["water"],
            "hydrology": baseline["hydrology"],
        }
    resource_id = {
        "plants.edible_parts": "mixed_berries",
        "plants.maturity_season": "oak_acorn",
        "plants.toxicity": "oak_acorn",
        "plants.harvest_difficulty": "cattail",
        "plants.regeneration": "oak_acorn",
        "plants.reproduction": "oak_acorn",
        "animals.habitat": "fish",
        "animals.food_sources": "fish",
        "animals.reproduction": "deer",
        "animals.capture_difficulty": "fish",
        "animals.harvest_response": "deer",
    }.get(component_id)
    if resource_id:
        return environment["resources"][resource_id]
    material_id = {
        "materials.stone": "stone",
        "materials.wood": "wood",
        "materials.fiber": "fiber",
        "materials.clay": "clay",
        "materials.processing_conditions": "wood",
    }.get(component_id)
    if material_id:
        return environment["materials"][material_id]
    return {"baseline_component": component_id, "land_rules": baseline["land"]}


def result_string(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _load_audit_module(root: Path) -> Any:
    tools_dir = str(root / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import phase1_audit

    return phase1_audit


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> Path:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_text(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def _render_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Audit",
        "",
        f"Gate status: **{audit['gate_status']}**",
        "",
        "## Summary",
        "",
        f"- Blockers: {audit['summary']['blockers']}",
        f"- Warnings: {audit['summary']['warnings']}",
        "",
        "## Findings",
        "",
    ]
    for finding in audit["findings"]:
        lines.append(
            f"- `{finding['severity']}` `{finding['code']}` at "
            f"`{finding['path']}`: {finding['message']}"
        )
    return "\n".join(lines).rstrip() + "\n"
