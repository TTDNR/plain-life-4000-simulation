#!/usr/bin/env python3
"""Validate the pre-simulation Phase 1 world and population contract."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VALID_RECORD_STATUSES = {"known", "assumption", "unresolved"}
FOOD_DIMENSION_IDS = (
    "mature",
    "reachable",
    "identifiable_and_processable",
    "labor_and_energy_cost",
    "transport_and_distribution",
    "preservation_duration",
    "household_capability_differences",
    "future_reproduction_impact",
)
REQUIRED_WINDOW_IDS = (
    "initial_days",
    "initial_weeks",
    "first_season_transition",
    "first_year_plus",
)
REQUIRED_PATH_IDS = (
    "water",
    "food",
    "shelter",
    "fire",
    "tools",
    "stable_supply",
)
REQUIRED_PATH_PROBLEMS = {
    "water": {
        "find water",
        "reach water",
        "recognize risk",
        "drink without a container",
        "assist a person who cannot self-provision",
    },
    "food": {
        "recognize food",
        "gather or capture",
        "transport",
        "process",
        "allocate",
        "bear misidentification and acquisition failure",
    },
    "shelter": {
        "choose a site",
        "collect material",
        "build cover",
        "manage damp and crowding",
        "manage night risk",
    },
    "fire": {
        "have an operator with practical skill",
        "find suitable material",
        "attempt and possibly fail",
        "maintain embers or fire",
    },
    "tools": {
        "find raw material",
        "know processing method",
        "spend labor time",
        "handle breakage and injury",
    },
    "stable_supply": {
        "store food",
        "cultivate or manage harvests",
        "improve tools",
        "cooperate",
        "recover from short-term shocks",
    },
}
REQUIRED_INITIALIZATION_IDS = (
    "environment_materialized_before_people",
    "agent_demand_generation_allowed",
    "state_fingerprint",
    "generation_seed",
)
REQUIRED_BOUNDARY_IDS = (
    "edge_rule",
    "weather_driver",
    "rainfall",
    "evaporation",
    "surface_water_outflow",
    "groundwater_outflow",
    "external_biota",
    "external_nonliving_material",
)
REQUIRED_COMPONENT_IDS = (
    "terrain.slope",
    "terrain.depressions",
    "terrain.flood_zones",
    "terrain.habitable_land",
    "terrain.cultivable_land",
    "freshwater.seasonal_volume",
    "freshwater.quality",
    "freshwater.access_difficulty",
    "freshwater.contamination_paths",
    "plants.edible_parts",
    "plants.maturity_season",
    "plants.toxicity",
    "plants.harvest_difficulty",
    "plants.regeneration",
    "plants.reproduction",
    "animals.habitat",
    "animals.food_sources",
    "animals.reproduction",
    "animals.capture_difficulty",
    "animals.harvest_response",
    "materials.stone",
    "materials.wood",
    "materials.fiber",
    "materials.clay",
    "materials.processing_conditions",
    "land.fertility",
    "land.drainage",
    "land.clearing_cost",
    "land.continuous_use_change",
)
REQUIRED_POPULATION_CONSTRAINT_IDS = (
    "age_kinship_fertility_and_memory_consistent",
    "infants_have_caregivers",
    "pregnancies_lactation_and_infants_reconciled",
    "skills_have_learning_and_practice_history",
    "households_can_contain_dependence_conflict_and_inequality",
    "households_are_not_forced_to_cooperate",
    "preexisting_private_ties_between_households",
    "shared_origin_language_and_customs_can_seed_trust",
    "old_property_and_office_transfer",
    "critical_craft_person_coverage",
)
REQUIRED_SETTLEMENT_CONSTRAINT_IDS = (
    "single_initial_drop_point",
    "preassigned_groups",
    "exploration_shares_map_globally",
    "new_dwelling_immediately_creates_polity",
    "settlement_identity_and_political_units_may_diverge",
    "stay_or_leave_decision",
)
REQUIRED_COMPONENT_CATEGORIES = {
    "terrain",
    "freshwater",
    "plants",
    "animals",
    "materials",
    "land",
}


@dataclass(frozen=True)
class Finding:
    section: str
    severity: str
    code: str
    path: str
    message: str


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def record_status_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(VALID_RECORD_STATUSES)}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        status = record.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def mapping_values(value: Any) -> list[Any]:
    if not isinstance(value, Mapping):
        return []
    return list(value.values())


def require_records(
    findings: list[Finding],
    section: str,
    records: Mapping[str, Any],
    required_ids: Sequence[str],
    path_prefix: str,
) -> None:
    for record_id in required_ids:
        if record_id not in records:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_record",
                    f"{path_prefix}.{record_id}",
                    "Required record is absent.",
                )
            )


def audit_record(
    findings: list[Finding],
    section: str,
    record: Mapping[str, Any],
    path: str,
    *,
    unresolved_is_blocker: bool = True,
) -> None:
    status = record.get("status")
    if status not in VALID_RECORD_STATUSES:
        findings.append(
            Finding(
                section,
                "blocker",
                "invalid_status",
                f"{path}.status",
                f"Status must be one of {sorted(VALID_RECORD_STATUSES)}.",
            )
        )
        return

    if status == "known":
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "known_without_evidence",
                    f"{path}.evidence",
                    "Known facts require at least one evidence identifier.",
                )
            )
        return

    if status == "assumption":
        if not isinstance(record.get("rationale"), str) or not record["rationale"].strip():
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "assumption_without_rationale",
                    f"{path}.rationale",
                    "Assumptions require an explicit rationale.",
                )
            )
        if record.get("accepted") is not True:
            findings.append(
                Finding(
                    section,
                    "warning",
                    "assumption_not_accepted",
                    f"{path}.accepted",
                    "Assumption is documented but not yet accepted.",
                )
            )
        return

    if unresolved_is_blocker:
        findings.append(
            Finding(
                section,
                "blocker",
                "unresolved_required_fact",
                path,
                "Required fact has not been resolved.",
            )
        )


def audit_environment(world: Mapping[str, Any]) -> list[Finding]:
    section = "environment"
    findings: list[Finding] = []
    area = world.get("area_km2")
    if not isinstance(area, (int, float)) or abs(float(area) - 50.0) > 1e-9:
        findings.append(
            Finding(
                section,
                "blocker",
                "wrong_world_area",
                "world.area_km2",
                "The first requirement fixes the world at 50 square kilometers.",
            )
        )

    initialization = world.get("initialization")
    if not isinstance(initialization, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_initialization",
                "world.initialization",
                "Initialization controls are required.",
            )
        )
    else:
        require_records(
            findings,
            section,
            initialization,
            REQUIRED_INITIALIZATION_IDS,
            "world.initialization",
        )
        for key, record in initialization.items():
            if isinstance(record, dict):
                audit_record(
                    findings, section, record, f"world.initialization.{key}"
                )
        if initialization.get("environment_materialized_before_people", {}).get(
            "value"
        ) is not True:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "people_before_environment",
                    "world.initialization.environment_materialized_before_people.value",
                    "The environment must exist before any person is placed.",
                )
            )
        if initialization.get("agent_demand_generation_allowed", {}).get(
            "value"
        ) is not False:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "demand_driven_generation",
                    "world.initialization.agent_demand_generation_allowed.value",
                    "Resource generation must not depend on current agent needs.",
                )
            )

    boundary = world.get("boundary")
    if not isinstance(boundary, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_boundary",
                "world.boundary",
                "Closed-world boundary rules are required.",
            )
        )
    else:
        require_records(
            findings,
            section,
            boundary,
            REQUIRED_BOUNDARY_IDS,
            "world.boundary",
        )
        for key, record in boundary.items():
            if isinstance(record, dict):
                audit_record(findings, section, record, f"world.boundary.{key}")
        if str(boundary.get("external_biota", {}).get("value", "")).lower() != "none":
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "external_biota",
                    "world.boundary.external_biota.value",
                    "Living resources must not enter from outside the closed world.",
                )
            )

    components = world.get("components")
    if not isinstance(components, dict) or not components:
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_components",
                "world.components",
                "The materialized environment inventory is required.",
            )
        )
        return findings

    seen_categories: set[str] = set()
    require_records(
        findings,
        section,
        components,
        REQUIRED_COMPONENT_IDS,
        "world.components",
    )
    for component_id, record in components.items():
        path = f"world.components.{component_id}"
        if not isinstance(record, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_component",
                    path,
                    "Component record must be an object.",
                )
            )
            continue
        category = record.get("category")
        if isinstance(category, str):
            seen_categories.add(category)
        if not isinstance(record.get("required_content"), str) or not record[
            "required_content"
        ].strip():
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_required_content",
                    f"{path}.required_content",
                    "Each environment component must state what it has to answer.",
                )
            )
        audit_record(findings, section, record, path)

    missing_categories = sorted(REQUIRED_COMPONENT_CATEGORIES - seen_categories)
    if missing_categories:
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_component_category",
                "world.components",
                f"Missing environment categories: {', '.join(missing_categories)}.",
            )
        )
    return findings


def audit_survival(survival: Mapping[str, Any]) -> list[Finding]:
    section = "survival"
    findings: list[Finding] = []
    if survival.get("target_population") != 4000:
        findings.append(
            Finding(
                section,
                "blocker",
                "wrong_population",
                "survival.target_population",
                "Opening survival capacity must be checked for 4000 people.",
            )
        )

    windows = survival.get("windows")
    by_window_id: dict[str, Mapping[str, Any]] = {}
    if isinstance(windows, list):
        by_window_id = {
            item.get("id"): item
            for item in windows
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    require_records(
        findings,
        section,
        by_window_id,
        REQUIRED_WINDOW_IDS,
        "survival.windows",
    )
    for window_id in REQUIRED_WINDOW_IDS:
        window = by_window_id.get(window_id)
        if not window:
            continue
        path = f"survival.windows.{window_id}"
        window_status = window.get("status")
        if window_status != "evaluated":
            findings.append(
                Finding(
                    section,
                    "blocker",
                    (
                        "window_not_evaluated"
                        if window_status == "unresolved"
                        else "window_failed"
                    ),
                    f"{path}.status",
                    (
                        "Each required time window must be evaluated before long simulation."
                        if window_status == "unresolved"
                        else "The evaluated time window did not pass its survival checks."
                    ),
                )
            )
            continue
        for field in ("bottleneck", "likely_failure"):
            if not isinstance(window.get(field), str) or not window[field].strip():
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        f"missing_{field}",
                        f"{path}.{field}",
                        f"Evaluated window requires {field}.",
                    )
                )
        paths = window.get("feasible_paths")
        if not isinstance(paths, list) or not paths:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_feasible_paths",
                    f"{path}.feasible_paths",
                    "Evaluated window requires at least one feasible path.",
                )
            )
        margin = window.get("capacity_margin")
        if not isinstance(margin, (int, float)):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_capacity_margin",
                    f"{path}.capacity_margin",
                    "Evaluated window requires a numeric capacity margin.",
                )
            )
        if not window.get("evidence"):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "window_without_evidence",
                    f"{path}.evidence",
                    "Evaluated window requires evidence.",
                )
            )

    paths = survival.get("paths")
    if not isinstance(paths, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_survival_paths",
                "survival.paths",
                "All required survival dependencies must be represented.",
            )
        )
    else:
        require_records(
            findings, section, paths, REQUIRED_PATH_IDS, "survival.paths"
        )
        for path_id in REQUIRED_PATH_IDS:
            path_data = paths.get(path_id)
            if not isinstance(path_data, dict):
                continue
            path = f"survival.paths.{path_id}"
            problems = path_data.get("required_problems")
            if not isinstance(problems, list) or not problems:
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        "missing_required_problems",
                        f"{path}.required_problems",
                        "The complete dependency chain must be stated.",
                    )
                )
            else:
                expected_problems = REQUIRED_PATH_PROBLEMS[path_id]
                missing_problems = sorted(
                    expected_problems
                    - {problem for problem in problems if isinstance(problem, str)}
                )
                if missing_problems:
                    findings.append(
                        Finding(
                            section,
                            "blocker",
                            "incomplete_required_problems",
                            f"{path}.required_problems",
                            "Missing required problems: "
                            + ", ".join(missing_problems)
                            + ".",
                        )
                    )
            path_status = path_data.get("status")
            if path_status != "evaluated":
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        (
                            "path_not_evaluated"
                            if path_status == "unresolved"
                            else "path_failed"
                        ),
                        f"{path}.status",
                        (
                            "Each survival path must be evaluated against the environment."
                            if path_status == "unresolved"
                            else "The evaluated survival path did not pass against the environment."
                        ),
                    )
                )
                continue
            if not isinstance(path_data.get("solution"), str) or not path_data[
                "solution"
            ].strip():
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        "path_without_solution",
                        f"{path}.solution",
                        "Evaluated path requires a concrete solution.",
                    )
                )
            if not path_data.get("evidence"):
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        "path_without_evidence",
                        f"{path}.evidence",
                        "Evaluated path requires evidence.",
                    )
                )

    food_audit = survival.get("food_audit")
    if not isinstance(food_audit, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_food_audit",
                "survival.food_audit",
                "Food is the primary verification target.",
            )
        )
    else:
        dimensions = food_audit.get("dimensions")
        if not isinstance(dimensions, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_food_dimensions",
                    "survival.food_audit.dimensions",
                    "Food must be evaluated beyond total map biomass.",
                )
            )
        else:
            require_records(
                findings,
                section,
                dimensions,
                FOOD_DIMENSION_IDS,
                "survival.food_audit.dimensions",
            )
            for dimension_id in FOOD_DIMENSION_IDS:
                record = dimensions.get(dimension_id)
                if isinstance(record, dict):
                    audit_record(
                        findings,
                        section,
                        record,
                        f"survival.food_audit.dimensions.{dimension_id}",
                    )

        known_constraints = {
            "total_biomass_is_sufficient_proof": False,
            "automatic_agriculture": False,
        }
        for key, expected in known_constraints.items():
            record = food_audit.get(key, {})
            if record.get("value") is not expected:
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        f"invalid_{key}",
                        f"survival.food_audit.{key}.value",
                        f"{key} must be {expected}.",
                    )
                )
        if str(
            food_audit.get("external_crop_seeds", {}).get("value", "")
        ).lower() != "none":
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "external_crop_seeds",
                    "survival.food_audit.external_crop_seeds.value",
                    "No crop seed supply may enter from outside the world.",
                )
            )
        if str(
            food_audit.get("domestication_shortcut", {}).get("value", "")
        ).lower() == "allowed":
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "domestication_shortcut",
                    "survival.food_audit.domestication_shortcut.value",
                    "Domestication cannot complete through a short-term progress bar.",
                )
            )

    time_allocation = survival.get("time_allocation")
    if not isinstance(time_allocation, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_time_allocation",
                "survival.time_allocation",
                "Competing care, illness, search, conflict, and rest must consume time.",
            )
        )
    else:
        if time_allocation.get("all_people_free_for_collection", {}).get(
            "value"
        ) is not False:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "unlimited_collection_time",
                    "survival.time_allocation.all_people_free_for_collection.value",
                    "Not every person may be assigned to full-time collection.",
                )
            )
        if time_allocation.get("skill_implies_immediate_success", {}).get(
            "value"
        ) is not False:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "skill_guarantees_success",
                    "survival.time_allocation.skill_implies_immediate_success.value",
                    "Skill knowledge must not bypass material, labor, and failure checks.",
                )
            )
    return findings


def _validate_references(
    findings: list[Finding],
    section: str,
    refs: Iterable[Any],
    valid_ids: set[str],
    path: str,
) -> None:
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or ref not in valid_ids:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_reference",
                    f"{path}[{index}]",
                    f"Reference {ref!r} does not resolve.",
                )
            )


def audit_population(population: Mapping[str, Any]) -> list[Finding]:
    section = "initialization"
    findings: list[Finding] = []
    target_total = population.get("target_total")
    if target_total != 4000:
        findings.append(
            Finding(
                section,
                "blocker",
                "wrong_population_target",
                "population.target_total",
                "Population initialization must target exactly 4000 people.",
            )
        )

    constraints = population.get("constraints")
    if not isinstance(constraints, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_population_constraints",
                "population.constraints",
                "Population consistency constraints are required.",
            )
        )
    else:
        require_records(
            findings,
            section,
            constraints,
            REQUIRED_POPULATION_CONSTRAINT_IDS,
            "population.constraints",
        )
        for key, record in constraints.items():
            if isinstance(record, dict):
                audit_record(
                    findings,
                    section,
                    record,
                    f"population.constraints.{key}",
                )

    settlement = population.get("settlement_constraints")
    if not isinstance(settlement, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_settlement_constraints",
                "population.settlement_constraints",
                "Initial settlement behavior must remain emergent.",
            )
        )
    else:
        require_records(
            findings,
            section,
            settlement,
            REQUIRED_SETTLEMENT_CONSTRAINT_IDS,
            "population.settlement_constraints",
        )
        for key, record in settlement.items():
            if isinstance(record, dict):
                audit_record(
                    findings,
                    section,
                    record,
                    f"population.settlement_constraints.{key}",
                )
        if settlement.get("preassigned_groups", {}).get("value") != "none":
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "preassigned_groups",
                    "population.settlement_constraints.preassigned_groups.value",
                    "No groups or tribes may be assigned before people decide.",
                )
            )
        if settlement.get("exploration_shares_map_globally", {}).get(
            "value"
        ) is not False:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "global_exploration_map",
                    "population.settlement_constraints.exploration_shares_map_globally.value",
                    "Exploration knowledge cannot become globally available automatically.",
                )
            )

    ecology_link = population.get("ecology_link")
    if not isinstance(ecology_link, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_ecology_link",
                "population.ecology_link",
                "Population capabilities must be reconciled with the environment.",
            )
        )
    elif ecology_link.get("status") == "unresolved":
        findings.append(
            Finding(
                section,
                "blocker",
                "ecology_link_unresolved",
                "population.ecology_link",
                "Population, household capabilities, care load, labor, and ecology are not reconciled.",
            )
        )
    else:
        for key, value in ecology_link.items():
            if key not in {"status", "evidence"} and value is None:
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        "missing_ecology_link_field",
                        f"population.ecology_link.{key}",
                        "Every population-to-ecology link must be concrete.",
                    )
                )

    snapshot = population.get("snapshot")
    if not isinstance(snapshot, dict):
        findings.append(
            Finding(
                section,
                "blocker",
                "missing_population_snapshot",
                "population.snapshot",
                "A concrete population snapshot is required.",
            )
        )
        return findings

    if snapshot.get("status") != "ready":
        findings.append(
            Finding(
                section,
                "blocker",
                "population_snapshot_unresolved",
                "population.snapshot.status",
                "A ready snapshot of 4000 people and their households is required.",
            )
        )
        return findings

    people = snapshot.get("people")
    households = snapshot.get("households")
    kinship_edges = snapshot.get("kinship_edges")
    pregnancy_events = snapshot.get("pregnancy_events")
    lactation_links = snapshot.get("lactation_links")
    for key, value in (
        ("people", people),
        ("households", households),
        ("kinship_edges", kinship_edges),
        ("pregnancy_events", pregnancy_events),
        ("lactation_links", lactation_links),
    ):
        if not isinstance(value, list):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_snapshot_collection",
                    f"population.snapshot.{key}",
                    "Snapshot collection must be a list.",
                )
            )
            return findings

    if len(people) != 4000:
        findings.append(
            Finding(
                section,
                "blocker",
                "snapshot_population_mismatch",
                "population.snapshot.people",
                f"Snapshot contains {len(people)} people instead of 4000.",
            )
        )

    person_ids: set[str] = set()
    for index, person in enumerate(people):
        path = f"population.snapshot.people[{index}]"
        if not isinstance(person, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_person",
                    path,
                    "Person record must be an object.",
                )
            )
            continue
        person_id = person.get("id")
        if not isinstance(person_id, str) or not person_id:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_person_id",
                    f"{path}.id",
                    "Person requires a non-empty string id.",
                )
            )
        elif person_id in person_ids:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "duplicate_person_id",
                    f"{path}.id",
                    f"Duplicate person id {person_id!r}.",
                )
            )
        else:
            person_ids.add(person_id)

        if not isinstance(person.get("life_stage"), str):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_life_stage",
                    f"{path}.life_stage",
                    "Person requires a life stage.",
                )
            )
        if not isinstance(person.get("life_history"), list) or not person[
            "life_history"
        ]:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_life_history",
                    f"{path}.life_history",
                    "Age and capabilities require consistent lived experience.",
                )
            )
        skills = person.get("skills")
        if not isinstance(skills, list):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_skill_list",
                    f"{path}.skills",
                    "Every person requires an explicit, possibly empty, skill list.",
                )
            )
        else:
            for skill_index, skill in enumerate(skills):
                skill_path = f"{path}.skills[{skill_index}]"
                if not isinstance(skill, dict):
                    findings.append(
                        Finding(
                            section,
                            "blocker",
                            "invalid_skill",
                            skill_path,
                            "Skill record must be an object.",
                        )
                    )
                    continue
                if not isinstance(skill.get("learned_via"), str) or not skill[
                    "learned_via"
                ].strip():
                    findings.append(
                        Finding(
                            section,
                            "blocker",
                            "skill_without_learning_history",
                            f"{skill_path}.learned_via",
                            "Skill requires a learning experience.",
                        )
                    )
                practice = skill.get("practice_opportunities")
                if not isinstance(practice, int) or practice < 0:
                    findings.append(
                        Finding(
                            section,
                            "blocker",
                            "skill_without_practice",
                            f"{skill_path}.practice_opportunities",
                            "Skill requires a non-negative practice count.",
                        )
                    )

        caregiver_ids = person.get("caregiver_ids", [])
        if not isinstance(caregiver_ids, list):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_caregiver_list",
                    f"{path}.caregiver_ids",
                    "Caregiver references must be a list.",
                )
            )
        elif person.get("life_stage") == "infant" and not caregiver_ids:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "infant_without_caregiver",
                    f"{path}.caregiver_ids",
                    "Every infant requires a known caregiver.",
                )
            )

    for index, person in enumerate(people):
        if isinstance(person, dict):
            _validate_references(
                findings,
                section,
                person.get("caregiver_ids", []),
                person_ids,
                f"population.snapshot.people[{index}].caregiver_ids",
            )

    household_ids: set[str] = set()
    assigned_members: dict[str, int] = {}
    for index, household in enumerate(households):
        path = f"population.snapshot.households[{index}]"
        if not isinstance(household, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_household",
                    path,
                    "Household record must be an object.",
                )
            )
            continue
        household_id = household.get("id")
        if not isinstance(household_id, str) or not household_id:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_household_id",
                    f"{path}.id",
                    "Household requires a non-empty string id.",
                )
            )
        elif household_id in household_ids:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "duplicate_household_id",
                    f"{path}.id",
                    f"Duplicate household id {household_id!r}.",
                )
            )
        else:
            household_ids.add(household_id)
        members = household.get("member_ids")
        if not isinstance(members, list) or not members:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_household_members",
                    f"{path}.member_ids",
                    "Household requires at least one member.",
                )
            )
            continue
        _validate_references(
            findings,
            section,
            members,
            person_ids,
            f"{path}.member_ids",
        )
        for member_id in members:
            if isinstance(member_id, str):
                assigned_members[member_id] = assigned_members.get(member_id, 0) + 1
    for person_id, count in assigned_members.items():
        if count > 1:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "person_in_multiple_households",
                    "population.snapshot.households",
                    f"Person {person_id!r} appears in {count} households.",
                )
            )

    for index, edge in enumerate(kinship_edges):
        path = f"population.snapshot.kinship_edges[{index}]"
        if not isinstance(edge, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_kinship_edge",
                    path,
                    "Kinship edge must be an object.",
                )
            )
            continue
        if not isinstance(edge.get("kind"), str):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "missing_kinship_kind",
                    f"{path}.kind",
                    "Kinship edge requires a kind.",
                )
            )
        _validate_references(
            findings,
            section,
            [edge.get("from"), edge.get("to")],
            person_ids,
            path,
        )

    live_birth_infants: set[str] = set()
    for index, event in enumerate(pregnancy_events):
        path = f"population.snapshot.pregnancy_events[{index}]"
        if not isinstance(event, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_pregnancy_event",
                    path,
                    "Pregnancy event must be an object.",
                )
            )
            continue
        person_id = event.get("person_id")
        if person_id not in person_ids:
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "pregnancy_without_person",
                    f"{path}.person_id",
                    "Pregnancy event must resolve to a person.",
                )
            )
        if event.get("outcome") == "live_birth":
            infant_id = event.get("infant_id")
            if infant_id not in person_ids:
                findings.append(
                    Finding(
                        section,
                        "blocker",
                        "live_birth_without_infant",
                        f"{path}.infant_id",
                        "Live birth must resolve to an initialized infant.",
                    )
                )
            elif isinstance(infant_id, str):
                live_birth_infants.add(infant_id)

    for index, link in enumerate(lactation_links):
        path = f"population.snapshot.lactation_links[{index}]"
        if not isinstance(link, dict):
            findings.append(
                Finding(
                    section,
                    "blocker",
                    "invalid_lactation_link",
                    path,
                    "Lactation link must be an object.",
                )
            )
            continue
        _validate_references(
            findings,
            section,
            [link.get("person_id"), link.get("infant_id")],
            person_ids,
            path,
        )

    record_by_id = {
        person.get("id"): person
        for person in people
        if isinstance(person, dict) and isinstance(person.get("id"), str)
    }
    for person_id, person in record_by_id.items():
        if person.get("life_stage") == "infant" and person_id not in live_birth_infants:
            findings.append(
                Finding(
                    section,
                    "warning",
                    "infant_without_birth_event",
                    f"population.snapshot.people.{person_id}",
                    "Infant has no live-birth event; verify whether the infant was adopted or data is incomplete.",
                )
            )
    return findings


def build_audit(
    world: Mapping[str, Any],
    survival: Mapping[str, Any],
    population: Mapping[str, Any],
) -> dict[str, Any]:
    findings = [
        *audit_environment(world),
        *audit_survival(survival),
        *audit_population(population),
    ]
    if any(item.severity == "blocker" for item in findings):
        gate_status = "BLOCKED"
    elif any(item.severity == "warning" for item in findings):
        gate_status = "CONDITIONAL"
    else:
        gate_status = "PASS"

    environment_records = [
        *mapping_values(world.get("initialization")),
        *mapping_values(world.get("boundary")),
        *mapping_values(world.get("components")),
    ]
    survival_records: list[Mapping[str, Any]] = []
    windows = survival.get("windows", [])
    if isinstance(windows, list):
        survival_records.extend(item for item in windows if isinstance(item, dict))
    paths = survival.get("paths", {})
    if isinstance(paths, dict):
        survival_records.extend(
            item for item in paths.values() if isinstance(item, dict)
        )
    food_audit = survival.get("food_audit", {})
    if isinstance(food_audit, dict):
        dimensions = food_audit.get("dimensions", {})
        if isinstance(dimensions, dict):
            survival_records.extend(
                item for item in dimensions.values() if isinstance(item, dict)
            )

    population_records: list[Mapping[str, Any]] = []
    constraints = population.get("constraints", {})
    if isinstance(constraints, dict):
        population_records.extend(
            item for item in constraints.values() if isinstance(item, dict)
        )
    settlement = population.get("settlement_constraints", {})
    if isinstance(settlement, dict):
        population_records.extend(
            item for item in settlement.values() if isinstance(item, dict)
        )

    return {
        "gate_status": gate_status,
        "summary": {
            "blockers": sum(item.severity == "blocker" for item in findings),
            "warnings": sum(item.severity == "warning" for item in findings),
            "environment_status_counts": record_status_counts(environment_records),
            "survival_status_counts": record_status_counts(survival_records),
            "population_status_counts": record_status_counts(population_records),
        },
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(audit: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 1 Audit",
        "",
        f"Gate status: **{audit['gate_status']}**",
        "",
        "This report is generated from `data/phase1/*.json`. A non-PASS result is a "
        "long-simulation gate failure, not a simulation outcome.",
        "",
        "## Summary",
        "",
    ]
    summary = audit["summary"]
    lines.extend(
        [
            f"- Blockers: {summary['blockers']}",
            f"- Warnings: {summary['warnings']}",
            f"- Environment status counts: `{summary['environment_status_counts']}`",
            f"- Survival status counts: `{summary['survival_status_counts']}`",
            f"- Population status counts: `{summary['population_status_counts']}`",
            "",
            "## Findings",
            "",
        ]
    )

    severities = ("blocker", "warning", "info")
    for severity in severities:
        selected = [
            finding
            for finding in audit["findings"]
            if finding["severity"] == severity
        ]
        if not selected:
            continue
        lines.append(f"### {severity.title()} ({len(selected)})")
        lines.append("")
        for finding in selected:
            lines.append(
                f"- `{finding['code']}` at `{finding['path']}`: "
                f"{finding['message']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the Phase 1 environment, survival, and population gate."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/phase1"),
        help="Directory containing world.json, survival.json, and population.json.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format written to stdout.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file. stdout is used when omitted.",
    )
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Return zero even when the gate is not PASS.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        world = load_json(args.data / "world.json")
        survival = load_json(args.data / "survival.json")
        population = load_json(args.data / "population.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"phase1-audit: {exc}", file=sys.stderr)
        return 2

    audit = build_audit(world, survival, population)
    report = (
        render_markdown(audit)
        if args.format == "markdown"
        else json.dumps(audit, indent=2, sort_keys=True) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    if audit["gate_status"] == "PASS" or args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
