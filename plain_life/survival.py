"""Rule-based survival validation for the Phase 1 initial population."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from .environment import Cell, WorldState
from .environment import (
    record_material_harvest,
    record_resource_harvest,
    resource_ledger_snapshot,
)
from .population import Person, PopulationState


WINDOWS = (
    ("initial_days", 1, 3),
    ("initial_weeks", 4, 42),
    ("first_season_transition", 43, 180),
    ("first_year_plus", 181, 365),
)

SPOILAGE_PER_DAY = {
    "mixed_berries": 0.18,
    "spring_greens": 0.35,
    "fish": 0.22,
    "waterfowl": 0.18,
    "hare": 0.16,
    "deer": 0.16,
    "cattail": 0.04,
    "arrowhead": 0.04,
    "hazelnut": 0.005,
    "oak_acorn": 0.004,
}


@dataclass
class DayMetric:
    day: int
    day_of_year: int
    temperature_c: float
    rainfall_mm: float
    food_demand_kcal: float
    food_acquired_kcal: float
    food_ratio: float
    food_ratio_household_min: float
    food_ratio_household_p10: float
    households_below_080: int
    migration_hours: float
    knowledge_sharing_hours: float
    water_demand_litres: float
    water_acquired_litres: float
    water_ratio: float
    shelter_fraction: float
    fire_fraction: float
    tool_fraction: float
    exposed_households: int
    hard_food_failure_households: int
    water_failure_households: int
    migrations: int
    surface_water_m3: float
    remaining_wild_food_kcal: float
    known_available_food_kcal: float
    household_known_food_kcal_sum: float
    stock_kg_acquired: float
    edible_food_kg_acquired: float
    food_store_end_kcal: float
    food_obstacles: dict[str, int]
    food_resource_switches: int


@dataclass
class HouseholdRuntime:
    household_id: str
    members: list[Person]
    camp_cell_index: int
    known_cells: set[int]
    supply_options: list[tuple[str, int, float, float]]
    material_options: dict[str, list[int]]
    person_known_cells: dict[str, set[int]]
    food_store_kg: dict[str, float] = field(default_factory=dict)
    food_store_kcal: float = 0.0
    shelter_quality: float = 0.0
    fire_quality: float = 0.0
    tool_quality: float = 0.45
    food_deficit_streak: int = 0
    water_deficit_streak: int = 0
    low_food_days: int = 0
    migrations: int = 0
    last_migration_day: int = 0
    last_food_ratio: float = 1.0
    migration_travel_debt_hours: float = 0.0
    knowledge_sharing_hours: float = 0.0
    shelter_completed_day: int | None = None
    shelter_attempt_hours: float = 0.0
    shelter_material_failure_days: int = 0
    fire_first_success_day: int | None = None
    fire_first_attempt_day: int | None = None
    fire_attempts: int = 0
    fire_failures: int = 0
    fire_failure_reasons: dict[str, int] = field(default_factory=dict)
    fire_days_without_time: int = 0
    fire_material_search_failures: int = 0
    last_fire_material_search_day: int = 0
    tool_completed_day: int | None = None
    water_container_capacity_l: float = 0.0
    water_container_built_day: int | None = None
    water_vessel_attempts: int = 0
    water_vessel_failures: int = 0
    water_vessel_maker_ids: list[str] = field(default_factory=list)
    last_water_vessel_attempt_day: int = 0
    water_vessel_failure_reasons: dict[str, int] = field(default_factory=dict)
    water_vessel_blocked_reason: str | None = None
    body_states: dict[str, Any] = field(default_factory=dict)
    work_capacity_multiplier: float = 1.0
    last_consumed_kcal: float = 0.0
    last_water_ratio: float = 1.0
    last_labour_hours: float = 0.0
    last_remaining_hours: float = 0.0
    last_water_method: str = "none"
    last_water_distance_km: float = 0.0
    last_mobile_people: int = 0
    last_dependent_people: int = 0
    last_direct_capacity_l: float = 0.0
    last_water_hours: float = 0.0
    last_water_delivered_l: float = 0.0
    last_migration_hours: float = 0.0
    last_hours_before_water: float = 0.0
    last_potential_hours: float = 0.0
    last_care_hours: float = 0.0
    last_water_emergency: bool = False
    last_care_overlap_allowance: float = 0.0
    last_care_overlap_used: float = 0.0
    nearest_water_cell_index: int = 0
    last_food_activity_cell: int | None = None
    last_harvested_resource: str | None = None
    food_resource_switches: int = 0
    pending_water_credit_l: float = 0.0
    pending_care_credit_hours: float = 0.0
    last_care_credit_used_hours: float = 0.0
    social_travel_debt_hours: float = 0.0
    shelter_guest_capacity_used: int = 0
    pending_food_promises: list[dict[str, Any]] = field(default_factory=list)

    @property
    def skills(self) -> set[str]:
        return {
            skill["id"]
            for person in self.members
            for skill in person.skills
        }


@dataclass
class SurvivalRunResult:
    test_kind: str
    days: int
    start_environment_fingerprint: str
    end_environment_fingerprint: str
    population_fingerprint: str
    initial_world_unchanged: bool
    metrics: list[DayMetric]
    window_results: dict[str, dict[str, Any]]
    path_results: dict[str, dict[str, Any]]
    food_audit: dict[str, Any]
    resource_ledger: dict[str, dict[str, float]]
    harvest_details: dict[str, dict[str, float]]
    acquisition_paths: dict[str, dict[str, Any]]
    distribution_diagnostics: dict[str, Any]
    integration_diagnostics: dict[str, Any]
    household_daily_records: list[dict[str, Any]]
    person_daily_records: list[dict[str, Any]]
    social_action_records: list[dict[str, Any]]
    social_action_stats: dict[str, Any]
    person_food_records: list[dict[str, Any]]
    food_path_records: list[dict[str, Any]]
    daily_harvest_details: list[dict[str, float | str]]
    resource_consumption_kg: dict[str, float]
    migration_summary: dict[str, Any]
    final_resource_stock_kg: dict[str, float]

    def summary(self) -> dict[str, Any]:
        return {
            "test_kind": self.test_kind,
            "days": self.days,
            "start_environment_fingerprint": self.start_environment_fingerprint,
            "end_environment_fingerprint": self.end_environment_fingerprint,
            "population_fingerprint": self.population_fingerprint,
            "initial_world_unchanged": self.initial_world_unchanged,
            "window_results": self.window_results,
            "path_results": self.path_results,
            "food_audit": self.food_audit,
            "resource_ledger": self.resource_ledger,
            "harvest_details": self.harvest_details,
            "acquisition_paths": self.acquisition_paths,
            "distribution_diagnostics": self.distribution_diagnostics,
            "integration_diagnostics": self.integration_diagnostics,
            "household_daily_records": self.household_daily_records,
            "person_daily_records": self.person_daily_records,
            "social_action_records": self.social_action_records,
            "social_action_stats": self.social_action_stats,
            "person_food_records": self.person_food_records,
            "food_path_records": self.food_path_records,
            "daily_harvest_details": self.daily_harvest_details,
            "resource_consumption_kg": self.resource_consumption_kg,
            "migration_summary": self.migration_summary,
            "final_resource_stock_kg": self.final_resource_stock_kg,
        }


def run_survival_validation(
    initial_world: WorldState,
    population: PopulationState,
    days: int = 365,
    behavior_states: dict[str, Any] | None = None,
    record_household_trace: bool = False,
    enable_social_exchange: bool = False,
    apply_body_feedback: bool = True,
) -> SurvivalRunResult:
    world = initial_world.clone()
    start_fingerprint = initial_world.initial_fingerprint
    initial_world_changed_before_run = world.fingerprint() != start_fingerprint
    supply_cache: dict[int, list[tuple[str, int, float, float]]] = {}
    material_cache: dict[int, dict[str, list[int]]] = {}
    water_distance_cache: dict[int, float] = {}
    camp_score_cache: dict[int, float] = {}
    runtimes = _initialize_household_runtimes(
        world,
        population,
        supply_cache,
        material_cache,
        water_distance_cache,
        camp_score_cache,
    )
    if behavior_states:
        for runtime in runtimes.values():
            runtime.body_states = {
                person.id: behavior_states[person.id]
                for person in runtime.members
                if person.id in behavior_states
            }
    metrics: list[DayMetric] = []
    resource_consumption = {
        resource_id: 0.0
        for resource_id in world.baseline.resource_specs
    }
    harvest_details = {
        resource_id: {
            "stock_kg_removed": 0.0,
            "edible_food_kg": 0.0,
            "edible_kcal": 0.0,
            "harvest_hours": 0.0,
            "processing_hours": 0.0,
            "travel_hours": 0.0,
            "processing_attempts": 0.0,
            "processing_failures": 0.0,
        }
        for resource_id in world.baseline.resource_specs
    }
    distribution_observations: list[dict[str, float]] = []
    water_method_counts: dict[str, int] = {}
    daily_harvest_details: list[dict[str, float | str]] = []
    time_account: dict[str, float] = defaultdict(float)
    household_daily_records: list[dict[str, Any]] = []
    person_daily_records: list[dict[str, Any]] = []
    body_daily_summaries: list[dict[str, Any]] = []
    social_action_records: list[dict[str, Any]] = []
    social_action_stats = _empty_social_stats()
    person_food_records: list[dict[str, Any]] = []
    food_path_records: list[dict[str, Any]] = []
    camps_after_day_one_selection: set[int] = set()

    for day in range(1, days + 1):
        if behavior_states:
            _apply_body_constraints(runtimes, behavior_states)
        weather = _advance_day(world)
        _prepare_household_runtimes(
            world,
            runtimes,
            day,
            supply_cache,
            material_cache,
            water_distance_cache,
            camp_score_cache,
        )
        if day == 1:
            camps_after_day_one_selection = {
                runtime.camp_cell_index for runtime in runtimes.values()
            }
        day_metric = _simulate_day(
            world,
            runtimes,
            day,
            weather,
            resource_consumption,
            water_distance_cache,
            harvest_details,
            distribution_observations,
            water_method_counts,
            daily_harvest_details,
            time_account,
            household_daily_records if record_household_trace else None,
            person_daily_records if record_household_trace else None,
            food_path_records if record_household_trace else None,
        )
        metrics.append(day_metric)
        if enable_social_exchange:
            _run_social_exchange_phase(
                world,
                runtimes,
                day,
                weather,
                social_action_records,
                social_action_stats,
                behavior_states,
            )
        if behavior_states and apply_body_feedback:
            person_food_records.extend(
                _update_body_after_day(runtimes, behavior_states, day)
            )
            body_daily_summaries.append(
                _summarize_body_day(behavior_states, day)
            )

    window_results = _summarize_windows(metrics)
    path_results = _evaluate_paths(
        world, metrics
    )
    food_audit = _build_food_audit(
        initial_world,
        population,
        runtimes,
        metrics,
        resource_consumption,
        harvest_details,
    )
    distribution_diagnostics = _build_distribution_diagnostics(
        distribution_observations
    )
    acquisition_paths = _build_acquisition_paths(
        runtimes,
        metrics,
        harvest_details,
        world.baseline.raw,
        water_method_counts,
        daily_harvest_details,
        time_account,
    )
    integration_diagnostics = _summarize_integration(
        behavior_states if apply_body_feedback else None,
        runtimes,
        metrics,
        body_daily_summaries,
    )
    migration_summary = {
        "households_that_migrated": sum(
            runtime.migrations > 0 for runtime in runtimes.values()
        ),
        "migration_events": sum(
            runtime.migrations for runtime in runtimes.values()
        ),
        "drop_instant_camps": 1,
        "camps_after_day_one_selection": len(camps_after_day_one_selection),
        "final_camps": len(
            {runtime.camp_cell_index for runtime in runtimes.values()}
        ),
        "known_cell_radius_km_end": round(_exploration_radius_km(days), 3),
    }
    final_stock = {
        resource_id: round(sum(values), 3)
        for resource_id, values in {
            **world.plant_stock_kg,
            **world.animal_stock_kg,
        }.items()
    }
    end_fingerprint = world.fingerprint()
    return SurvivalRunResult(
        test_kind=(
            "dynamic_body_short_integration"
            if behavior_states
            else "fixed_population_demand_pressure_test"
        ),
        days=days,
        start_environment_fingerprint=start_fingerprint,
        end_environment_fingerprint=end_fingerprint,
        population_fingerprint=population.fingerprint,
        initial_world_unchanged=(
            not initial_world_changed_before_run
            and initial_world.fingerprint() == start_fingerprint
        ),
        metrics=metrics,
        window_results=window_results,
        path_results=path_results,
        food_audit=food_audit,
        resource_ledger=resource_ledger_snapshot(world),
        harvest_details={
            key: {metric: round(value, 6) for metric, value in values.items()}
            for key, values in sorted(harvest_details.items())
        },
        acquisition_paths=acquisition_paths,
        distribution_diagnostics=distribution_diagnostics,
        integration_diagnostics=integration_diagnostics,
        household_daily_records=household_daily_records,
        person_daily_records=person_daily_records,
        social_action_records=social_action_records,
        social_action_stats=social_action_stats,
        person_food_records=person_food_records,
        food_path_records=food_path_records,
        daily_harvest_details=daily_harvest_details,
        resource_consumption_kg={
            key: round(value, 3)
            for key, value in sorted(resource_consumption.items())
        },
        migration_summary=migration_summary,
        final_resource_stock_kg=final_stock,
    )


def _advance_day(world: WorldState) -> dict[str, float]:
    from .environment import advance_day

    return advance_day(world)


def _initialize_household_runtimes(
    world: WorldState,
    population: PopulationState,
    supply_cache: dict[int, list[tuple[str, int, float, float]]],
    material_cache: dict[int, dict[str, list[int]]],
    water_distance_cache: dict[int, float],
    camp_score_cache: dict[int, float],
) -> dict[str, HouseholdRuntime]:
    drop_index = world.drop_point.index
    runtimes: dict[str, HouseholdRuntime] = {}
    people_by_id = population.people_by_id
    households = sorted(population.households, key=lambda item: item.id)
    water_distance_cache[drop_index] = _nearest_water_distance_km(
        world, drop_index
    )
    camp_score_cache[drop_index] = _camp_score(world, drop_index)
    supply_options = supply_cache.get(drop_index)
    if supply_options is None:
        supply_options = _build_supply_options(world, drop_index)
        supply_cache[drop_index] = supply_options
    material_options = material_cache.get(drop_index)
    if material_options is None:
        material_options = _build_material_options(world, drop_index)
        material_cache[drop_index] = material_options
    for household in households:
        members = [people_by_id[person_id] for person_id in household.member_ids]
        runtimes[household.id] = HouseholdRuntime(
            household_id=household.id,
            members=members,
            camp_cell_index=drop_index,
            known_cells={drop_index},
            supply_options=supply_options,
            material_options=material_options,
            person_known_cells={
                person.id: {drop_index} for person in members
            },
            nearest_water_cell_index=_nearest_water_cell_index(world, drop_index),
        )
    return runtimes


def _prepare_household_runtimes(
    world: WorldState,
    runtimes: dict[str, HouseholdRuntime],
    day: int,
    supply_cache: dict[int, list[tuple[str, int, float, float]]],
    material_cache: dict[int, dict[str, list[int]]],
    water_distance_cache: dict[int, float],
    camp_score_cache: dict[int, float],
) -> None:
    radius_km = _exploration_radius_km(day)
    drop_index = world.drop_point.index
    explored_cells = [
        cell.index
        for cell in world.cells
        if cell.habitable
        and _distance_km(world, drop_index, cell.index) <= radius_km
    ]
    for index in explored_cells:
        camp_score_cache.setdefault(index, _camp_score(world, index))
    dynamic_camp_scores = {
        index: world.food_score(world.cells[index]) / 1_000_000.0
        for index in explored_cells
    }
    occupancy: dict[int, int] = {}
    for runtime in runtimes.values():
        occupancy[runtime.camp_cell_index] = (
            occupancy.get(runtime.camp_cell_index, 0) + 1
        )

    should_consider_migration = day == 1 or day % 5 == 0
    for runtime in runtimes.values():
        direct_observation = _nearby_habitable_indices(
            world, runtime.camp_cell_index, 1
        )
        for person in runtime.members:
            runtime.person_known_cells[person.id].update(
                direct_observation
            )
        scout = _choose_explorer(runtime)
        if scout is not None:
            explored = _nearby_habitable_indices(
                world, runtime.camp_cell_index, 2
            )
            before = set(runtime.person_known_cells[scout.id])
            runtime.person_known_cells[scout.id].update(explored)
            if len(runtime.person_known_cells[scout.id]) > len(before):
                runtime.knowledge_sharing_hours += 0.5 + 0.1 * max(
                    0, len(runtime.members) - 1
                )
        runtime.known_cells = {
            cell_index
            for known_cells in runtime.person_known_cells.values()
            for cell_index in known_cells
        }
        candidate_cells = sorted(runtime.known_cells)
        if should_consider_migration:
            recent_ratio = runtime.last_food_ratio
            current_water_distance = _cached_water_distance(
                world, runtime.camp_cell_index, water_distance_cache
            )
            needs_move = (
                day == 1
                or recent_ratio < 0.9
                or current_water_distance > 1.8
                or world.cells[runtime.camp_cell_index].flood_risk > 0.55
            )
            current_score = camp_score_cache[runtime.camp_cell_index]
            current_food_score = (
                world.food_score(world.cells[runtime.camp_cell_index])
                / 1_000_000.0
            )
            cooldown_elapsed = (
                day == 1 or day - runtime.last_migration_day >= 7
            )
            if needs_move and cooldown_elapsed and candidate_cells:
                best = max(
                    candidate_cells,
                    key=lambda index: (
                        dynamic_camp_scores[index]
                        + camp_score_cache[index] * 0.2
                        - occupancy.get(index, 0) * 0.45
                    ),
                )
                best_score = (
                    dynamic_camp_scores[best]
                    + camp_score_cache[best] * 0.2
                )
                current_score = (
                    current_food_score
                    + camp_score_cache[runtime.camp_cell_index] * 0.2
                )
                if (
                    best != runtime.camp_cell_index
                    and (
                        day == 1
                        or current_water_distance > 1.8
                        or world.cells[runtime.camp_cell_index].flood_risk > 0.55
                        or best_score > current_score * 1.2 + 0.5
                    )
                ):
                    occupancy[runtime.camp_cell_index] = max(
                        0, occupancy[runtime.camp_cell_index] - 1
                    )
                    occupancy[best] = occupancy.get(best, 0) + 1
                    migration_hours = (
                        _distance_km(world, runtime.camp_cell_index, best)
                        * 2.0
                        / 4.5
                    )
                    runtime.camp_cell_index = best
                    runtime.nearest_water_cell_index = (
                        _nearest_water_cell_index(world, best)
                    )
                    runtime.migrations += 1
                    runtime.last_migration_day = day
                    runtime.migration_travel_debt_hours += migration_hours
                    supply_options = supply_cache.get(best)
                    if supply_options is None:
                        supply_options = _build_supply_options(world, best)
                        supply_cache[best] = supply_options
                    material_options = material_cache.get(best)
                    if material_options is None:
                        material_options = _build_material_options(world, best)
                        material_cache[best] = material_options
                    runtime.supply_options = supply_options
                    runtime.material_options = material_options


def _simulate_day(
    world: WorldState,
    runtimes: dict[str, HouseholdRuntime],
    day: int,
    weather: dict[str, float],
    resource_consumption: dict[str, float],
    water_distance_cache: dict[int, float],
    harvest_details: dict[str, dict[str, float]],
    distribution_observations: list[dict[str, float]],
    water_method_counts: dict[str, int],
    daily_harvest_details: list[dict[str, float | str]],
    time_account: dict[str, float],
    household_daily_records: list[dict[str, Any]] | None,
    person_daily_records: list[dict[str, Any]] | None,
    food_path_records: list[dict[str, Any]] | None,
) -> DayMetric:
    food_demand = 0.0
    food_acquired = 0.0
    food_consumed = 0.0
    water_demand = 0.0
    water_acquired = 0.0
    shelter_quality_total = 0.0
    fire_quality_total = 0.0
    tool_quality_total = 0.0
    exposed_households = 0
    hard_food_failure_households = 0
    water_failure_households = 0
    migrations = 0
    migration_hours_total = 0.0
    knowledge_hours_total = 0.0
    household_food_ratios: list[float] = []
    households_below_080 = 0
    household_known_food_kcal_sum = 0.0
    distinct_known_food_cells: set[tuple[str, int]] = set()
    daily_harvest_start = len(daily_harvest_details)
    food_obstacles: dict[str, int] = defaultdict(int)
    food_resource_switches = 0
    household_order = sorted(
        runtimes,
        key=lambda household_id: (
            (sum(ord(char) for char in household_id) + day * 37) % 997,
            household_id,
        ),
    )

    for household_id in household_order:
        runtime = runtimes[household_id]
        household_category_hours: dict[str, float] = defaultdict(float)
        household_known_food_kcal_sum += _known_available_food_kcal(
            world, runtime
        )
        distinct_known_food_cells.update(
            _known_food_cells(world, runtime)
        )
        demand = sum(_daily_kcal_need(person) for person in runtime.members)
        litres = (
            len(runtime.members)
            * float(
                world.baseline.raw["hydrology"][
                    "drinking_litres_per_person_day"
                ]
            )
        )
        hours, care_hours, potential_hours = _available_labour_hours(runtime)
        care_credit_used = min(
            care_hours, runtime.pending_care_credit_hours
        )
        runtime.last_care_credit_used_hours = care_credit_used
        care_hours -= care_credit_used
        hours += care_credit_used
        runtime.pending_care_credit_hours = max(
            0.0, runtime.pending_care_credit_hours - care_credit_used
        )
        runtime.last_potential_hours = potential_hours
        runtime.last_care_hours = care_hours
        time_account["potential"] += potential_hours
        social_travel_hours = min(
            hours, runtime.social_travel_debt_hours
        )
        runtime.social_travel_debt_hours = max(
            0.0, runtime.social_travel_debt_hours - social_travel_hours
        )
        hours -= social_travel_hours
        time_account["social_travel"] += social_travel_hours
        household_category_hours["social_travel"] += social_travel_hours
        migration_hours = min(hours, runtime.migration_travel_debt_hours)
        runtime.last_migration_hours = migration_hours
        hours -= migration_hours
        time_account["migration_travel"] += migration_hours
        household_category_hours["migration_travel"] += migration_hours
        runtime.migration_travel_debt_hours = max(
            0.0, runtime.migration_travel_debt_hours - migration_hours
        )
        knowledge_hours = min(hours, runtime.knowledge_sharing_hours)
        hours -= knowledge_hours
        time_account["exploration_and_communication"] += knowledge_hours
        household_category_hours["exploration_and_communication"] += (
            knowledge_hours
        )
        runtime.knowledge_sharing_hours = max(
            0.0, runtime.knowledge_sharing_hours - knowledge_hours
        )
        runtime.last_hours_before_water = hours
        average_thirst = (
            mean(
                state.body.thirst
                for state in runtime.body_states.values()
            )
            if runtime.body_states
            else 0.0
        )
        water_emergency = (
            runtime.last_water_ratio < 0.8
            or average_thirst >= 0.65
            or (
                hours <= 0.01
                and care_hours > 0.0
                and any(
                    person.mobility >= 0.5
                    and person.life_stage != "infant"
                    for person in runtime.members
                )
            )
        )
        runtime.last_water_emergency = water_emergency
        care_overlap_allowance = (
            care_hours * 0.5 if water_emergency else 0.0
        )
        runtime.last_care_overlap_allowance = care_overlap_allowance
        delivered_credit = min(litres, runtime.pending_water_credit_l)
        runtime.pending_water_credit_l = max(
            0.0, runtime.pending_water_credit_l - delivered_credit
        )
        water_needed_after_credit = max(0.0, litres - delivered_credit)
        if water_needed_after_credit <= 0.0:
            water_hours = 0.0
            fetched_litres = 0.0
            water_method = "delivered_by_nearby_household"
            runtime.last_water_method = water_method
            runtime.last_water_hours = 0.0
            runtime.last_water_delivered_l = delivered_credit
        else:
            water_hours, fetched_litres, water_method = _fetch_water(
                world,
                runtime,
                water_needed_after_credit,
                hours + care_overlap_allowance,
                day,
                water_distance_cache,
            )
        delivered_litres = delivered_credit + fetched_litres
        time_account["water"] += water_hours
        household_category_hours["water"] += water_hours
        care_overlap_used = min(
            care_hours,
            max(0.0, water_hours - hours),
        )
        runtime.last_care_overlap_used = care_overlap_used
        care_hours_remaining = care_hours - care_overlap_used
        time_account["care"] += care_hours_remaining
        hours = max(
            0.0,
            hours + care_overlap_used - water_hours,
        )

        if day <= 3:
            task_hours = min(hours * 0.25, 2.0)
            _advance_shelter(world, runtime, task_hours)
            hours -= task_hours
            time_account["shelter"] += task_hours
            household_category_hours["shelter"] += task_hours
        if day == 1:
            task_hours = min(hours * 0.15, 1.0)
            _advance_tools(world, runtime, task_hours)
            hours -= task_hours
            time_account["tools"] += task_hours
            household_category_hours["tools"] += task_hours
        if day >= 2:
            task_hours = min(hours * 0.15, 1.0)
            _advance_fire(world, runtime, task_hours, day)
            hours -= task_hours
            time_account["fire"] += task_hours
            household_category_hours["fire"] += task_hours
        if day > 3:
            if runtime.shelter_quality < 0.8:
                task_hours = min(hours * 0.18, 1.2)
                _advance_shelter(world, runtime, task_hours)
                hours -= task_hours
                time_account["shelter"] += task_hours
                household_category_hours["shelter"] += task_hours
            maintenance = min(hours, 0.35)
            hours -= maintenance
            time_account["fire_maintenance"] += maintenance
            household_category_hours["fire_maintenance"] += maintenance

        target_kcal = demand + max(
            0.0,
            demand
            * _storage_target_fraction(day, world.start_day_of_year)
            - _store_kcal(world, runtime),
        )
        runtime.last_food_activity_cell = None
        previous_resource = runtime.last_harvested_resource
        acquired, food_hours_used = _harvest_food(
            world,
            runtime,
            hours,
            target_kcal,
            resource_consumption,
            harvest_details,
            daily_harvest_details,
            time_account,
            food_obstacles,
            food_path_records,
        )
        hours -= food_hours_used
        if (
            runtime.last_harvested_resource != previous_resource
            and previous_resource is not None
        ):
            runtime.food_resource_switches += 1
            food_resource_switches += 1
        household_category_hours["food_harvest_and_processing"] += (
            food_hours_used
        )
        time_account["unallocated_or_rest"] += max(0.0, hours)
        runtime.last_labour_hours = (
            potential_hours - care_hours_remaining - hours
        )
        runtime.last_remaining_hours = hours
        if person_daily_records is not None:
            person_daily_records.extend(
                _build_person_activity_records(
                    runtime,
                    day,
                    potential_hours,
                    care_hours,
                    hours,
                    household_category_hours,
                )
            )
        food_available_before_consumption = _store_kcal(world, runtime)
        consumed = _consume_food(world, runtime, demand)
        _spoil_food(world, runtime)
        ratio = consumed / demand if demand else 1.0
        if ratio < 0.5:
            runtime.food_deficit_streak += 1
            runtime.low_food_days += 1
        else:
            runtime.food_deficit_streak = 0
        if ratio < 0.8:
            hard_food_failure_households += 1
        water_ratio = delivered_litres / litres if litres else 1.0
        water_method_counts[water_method] = (
            water_method_counts.get(water_method, 0) + 1
        )
        if water_ratio < 0.9:
            runtime.water_deficit_streak += 1
            water_failure_households += 1
        else:
            runtime.water_deficit_streak = 0
        if runtime.shelter_quality < 0.55 and weather["rainfall_mm"] > 1.0:
            exposed_households += 1

        food_demand += demand
        food_acquired += acquired
        water_demand += litres
        water_acquired += delivered_litres
        shelter_quality_total += runtime.shelter_quality
        fire_quality_total += runtime.fire_quality
        tool_quality_total += runtime.tool_quality
        runtime.last_food_ratio = ratio
        runtime.last_consumed_kcal = consumed
        runtime.last_water_ratio = water_ratio
        if household_daily_records is not None:
            household_daily_records.append(
                {
                    "day": day,
                    "household_id": runtime.household_id,
                    "camp_cell_index": runtime.camp_cell_index,
                    "water_method": runtime.last_water_method,
                    "water_distance_km": runtime.last_water_distance_km,
                    "mobile_people": runtime.last_mobile_people,
                    "dependent_people": runtime.last_dependent_people,
                    "direct_capacity_l": runtime.last_direct_capacity_l,
                    "water_demand_l": litres,
                    "water_delivered_l": delivered_litres,
                    "water_ratio": water_ratio,
                    "water_hours": water_hours,
                    "migration_hours": runtime.last_migration_hours,
                    "hours_before_water": runtime.last_hours_before_water,
                    "potential_hours": runtime.last_potential_hours,
                    "care_hours": runtime.last_care_hours,
                    "water_emergency": runtime.last_water_emergency,
                    "care_overlap_allowance": (
                        runtime.last_care_overlap_allowance
                    ),
                    "care_overlap_used": runtime.last_care_overlap_used,
                    "family_labour_hours": runtime.last_labour_hours,
                    "vessel_capacity_l": runtime.water_container_capacity_l,
                    "vessel_blocked_reason": runtime.water_vessel_blocked_reason,
                    "food_ratio": ratio,
                    "family_labour_hours": runtime.last_labour_hours,
                }
            )
        food_consumed += consumed
        household_ratio = consumed / demand if demand else 1.0
        household_food_ratios.append(household_ratio)
        if household_ratio < 0.8:
            households_below_080 += 1
        distribution_observations.append(
            {
                "day": day,
                "demand_kcal": demand,
                "available_kcal": food_available_before_consumption,
                "camp_cell_index": float(runtime.camp_cell_index),
                "camp_x": float(world.cells[runtime.camp_cell_index].x),
                "camp_y": float(world.cells[runtime.camp_cell_index].y),
            }
        )
        migrations += 1 if runtime.last_migration_day == day else 0
        migration_hours_total += migration_hours
        knowledge_hours_total += knowledge_hours

    remaining_wild_food = sum(
        sum(values)
        * float(world.resource_spec(resource_id)["kcal_per_kg"])
        * float(
            world.resource_spec(resource_id).get(
                "edible_yield_fraction", 1.0
            )
        )
        for resource_id, values in {
            **world.plant_stock_kg,
            **world.animal_stock_kg,
        }.items()
    )
    household_count = len(runtimes)
    daily_harvest = daily_harvest_details[daily_harvest_start:]
    distinct_known_food_kcal = sum(
        _available_stock_kcal(world, resource_id, cell_index)
        for resource_id, cell_index in distinct_known_food_cells
    )
    return DayMetric(
        day=day,
        day_of_year=world.day_of_year,
        temperature_c=weather["temperature_c"],
        rainfall_mm=weather["rainfall_mm"],
        food_demand_kcal=round(food_demand, 3),
        food_acquired_kcal=round(food_acquired, 3),
        food_ratio=round(food_consumed / food_demand if food_demand else 1.0, 4),
        food_ratio_household_min=round(
            min(household_food_ratios) if household_food_ratios else 1.0,
            4,
        ),
        food_ratio_household_p10=round(
            _percentile(household_food_ratios, 0.10)
            if household_food_ratios
            else 1.0,
            4,
        ),
        households_below_080=households_below_080,
        migration_hours=round(migration_hours_total, 4),
        knowledge_sharing_hours=round(knowledge_hours_total, 4),
        water_demand_litres=round(water_demand, 3),
        water_acquired_litres=round(water_acquired, 3),
        water_ratio=round(water_acquired / water_demand if water_demand else 1.0, 4),
        shelter_fraction=round(shelter_quality_total / household_count, 4),
        fire_fraction=round(fire_quality_total / household_count, 4),
        tool_fraction=round(tool_quality_total / household_count, 4),
        exposed_households=exposed_households,
        hard_food_failure_households=hard_food_failure_households,
        water_failure_households=water_failure_households,
        migrations=migrations,
        surface_water_m3=round(world.water_volume_m3, 3),
        remaining_wild_food_kcal=round(remaining_wild_food, 3),
        known_available_food_kcal=round(distinct_known_food_kcal, 3),
        household_known_food_kcal_sum=round(
            household_known_food_kcal_sum, 3
        ),
        stock_kg_acquired=round(
            sum(float(item["stock_kg_removed"]) for item in daily_harvest),
            6,
        ),
        edible_food_kg_acquired=round(
            sum(float(item["edible_food_kg"]) for item in daily_harvest),
            6,
        ),
        food_store_end_kcal=round(
            sum(runtime.food_store_kcal for runtime in runtimes.values()),
            3,
        ),
        food_obstacles=dict(sorted(food_obstacles.items())),
        food_resource_switches=food_resource_switches,
    )


def _apply_body_constraints(
    runtimes: dict[str, HouseholdRuntime],
    behavior_states: dict[str, Any],
) -> None:
    for runtime in runtimes.values():
        capacities = [
            behavior_states[person.id].body.work_capacity
            for person in runtime.members
            if person.id in behavior_states
            and person.life_stage in {"adult", "elder"}
        ]
        runtime.work_capacity_multiplier = (
            mean(capacities) if capacities else 0.2
        )


def _update_body_after_day(
    runtimes: dict[str, HouseholdRuntime],
    behavior_states: dict[str, Any],
    day: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for runtime in runtimes.values():
        state_members = [
            behavior_states[person.id]
            for person in runtime.members
            if person.id in behavior_states
        ]
        active_states = [
            state
            for state in state_members
            if state.life_stage in {"adult", "elder"}
        ]
        labour_per_active = (
            runtime.last_labour_hours / max(1, len(active_states))
        )
        effective_needs = {
            state.person_id: state.daily_kcal_need
            + (
                max(0.0, labour_per_active - 4.0) * 45.0
                if state in active_states
                else 0.0
            )
            for state in state_members
        }
        total_weighted_claim = sum(
            effective_needs[state.person_id] * state.food_claim_weight
            for state in state_members
        )
        for state in state_members:
            effective_need = effective_needs[state.person_id]
            intake = (
                runtime.last_consumed_kcal
                * effective_need
                * state.food_claim_weight
                / max(1.0, total_weighted_claim)
            )
            deficit = effective_need - intake
            state.body.energy_balance_kcal -= deficit
            intake_ratio = min(1.0, intake / max(1.0, effective_need))
            state.body.hunger = max(
                0.0, state.body.hunger - 0.2 * intake_ratio
            )
            if deficit > 0.0:
                state.body.hunger = min(
                    1.0,
                    state.body.hunger
                    + 0.12 * deficit / state.daily_kcal_need,
                )
            if runtime.last_water_ratio < 1.0:
                state.body.thirst = min(
                    1.0,
                    state.body.thirst
                    + (1.0 - runtime.last_water_ratio) * 0.5,
                )
            else:
                state.body.thirst = max(0.0, state.body.thirst - 0.12)
            if state in active_states:
                state.body.fatigue = min(
                    1.0,
                    state.body.fatigue
                    + labour_per_active / 8.0 * 0.12,
                )
                state.body.sleep_debt_hours += max(
                    0.0, labour_per_active - 8.0
                )
            else:
                state.body.fatigue = min(
                    1.0, state.body.fatigue + 0.05
                )
            if (
                runtime.last_food_ratio >= 0.95
                and runtime.last_water_ratio >= 0.95
                and runtime.last_labour_hours <= 4.0
            ):
                state.body.fatigue = max(
                    0.0, state.body.fatigue - 0.08
                )
            records.append(
                {
                    "day": day,
                    "person_id": state.person_id,
                    "household_id": runtime.household_id,
                    "intake_kcal": round(intake, 3),
                    "effective_need_kcal": round(effective_need, 3),
                    "intake_ratio": round(intake_ratio, 4),
                    "food_claim_weight": round(
                        state.food_claim_weight, 4
                    ),
                    "sharing_disposition": round(
                        state.sharing_disposition, 4
                    ),
                    "hunger_after": round(state.body.hunger, 4),
                    "energy_balance_kcal": round(
                        state.body.energy_balance_kcal, 3
                    ),
                    "below_80_percent_need": intake_ratio < 0.8,
                }
            )
    return records


def _summarize_integration(
    behavior_states: dict[str, Any] | None,
    runtimes: dict[str, HouseholdRuntime],
    metrics: list[DayMetric],
    daily_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    if not behavior_states:
        return {
            "enabled": False,
            "reason": "Run without body-state feedback.",
        }
    capacities = [
        state.body.work_capacity for state in behavior_states.values()
    ]
    hunger_values = [
        state.body.hunger for state in behavior_states.values()
    ]
    thirst_values = [
        state.body.thirst for state in behavior_states.values()
    ]
    energy_values = [
        state.body.energy_balance_kcal
        for state in behavior_states.values()
    ]
    return {
        "enabled": True,
        "people": len(behavior_states),
        "minimum_work_capacity": round(min(capacities), 4),
        "mean_work_capacity": round(mean(capacities), 4),
        "people_with_hunger_at_cap": sum(
            state.body.hunger >= 0.999 for state in behavior_states.values()
        ),
        "people_with_thirst_at_cap": sum(
            state.body.thirst >= 0.999 for state in behavior_states.values()
        ),
        "total_energy_balance_kcal": round(sum(energy_values), 3),
        "minimum_energy_balance_kcal": round(min(energy_values), 3),
        "maximum_hunger": round(max(hunger_values), 4),
        "maximum_thirst": round(max(thirst_values), 4),
        "deaths": 0,
        "death_modeled": False,
        "disease_modeled": False,
        "people_capacity_limited_on_final_day": sum(
            state.body.work_capacity < 0.5
            for state in behavior_states.values()
        ),
        "days": len(metrics),
        "minimum_allowed_work_capacity": 0.05,
        "mean_work_capacity_day_scope": "final_day_population_mean",
        "daily": daily_summaries,
    }


def _empty_social_stats() -> dict[str, Any]:
    aid_types = ("water", "food", "fire", "care", "shelter", "teaching")
    return {
        aid_type: {
            "need_events": 0,
            "candidate_households": 0,
            "location_known": 0,
            "person_found": 0,
            "communication_opportunity": 0,
            "contacts_considered": 0,
            "requests_sent": 0,
            "responses_received": 0,
            "accepted": 0,
            "current_delivery_commitments": 0,
            "willing_no_current_resource": 0,
            "conditional_promises": 0,
            "promises_executed": 0,
            "promises_failed": 0,
            "current_commitment_failures": 0,
            "rejected": 0,
            "executed": 0,
            "not_continued_reasons": {},
        }
        for aid_type in aid_types
    }


def _run_social_exchange_phase(
    world: WorldState,
    runtimes: dict[str, HouseholdRuntime],
    day: int,
    weather: dict[str, float],
    records: list[dict[str, Any]],
    stats: dict[str, Any],
    behavior_states: dict[str, Any] | None,
) -> None:
    runtimes_list = sorted(runtimes.values(), key=lambda item: item.household_id)
    _process_food_promises(
        day, runtimes, records, stats
    )
    for runtime in runtimes_list:
        if runtime.last_care_credit_used_hours > 0.0:
            stats["care"]["executed"] += 1
            records.append(
                {
                    "day": day,
                    "aid_type": "care",
                    "requestor_id": runtime.household_id,
                    "donor_id": None,
                    "accepted": True,
                    "executed": True,
                    "details": {
                        "care_hours": runtime.last_care_credit_used_hours,
                        "execution_time": "current_day",
                    },
                }
            )
            runtime.last_care_credit_used_hours = 0.0
    for requestor in runtimes_list:
        aid_type = _choose_social_need(
            requestor, weather, behavior_states
        )
        if aid_type is None:
            continue
        stats[aid_type]["need_events"] += 1
        contacts = _nearby_contact_households(
            world, requestor, runtimes_list, max_distance_km=1.0, limit=6
        )
        if not contacts:
            _record_social_reason(
                records,
                stats,
                day,
                aid_type,
                requestor,
                None,
                "no_reachable_contact",
            )
            continue
        stats[aid_type]["candidate_households"] += len(contacts)
        contact_result = _find_contactable_household(
            world,
            requestor,
            contacts,
            stats,
            aid_type,
            day,
        )
        if contact_result is None:
            _record_social_reason(
                records,
                stats,
                day,
                aid_type,
                requestor,
                None,
                "no_contactable_household",
            )
            continue
        donor, distance_km = contact_result
        stats[aid_type]["contacts_considered"] += 1
        stats[aid_type]["requests_sent"] += 1
        relation_trust = _relationship_trust(stats, requestor, donor)
        capacity_available = _can_help_with(
            aid_type, donor, requestor, behavior_states
        )
        donor_capacity = (
            _help_capacity_score(aid_type, donor, requestor)
            if capacity_available
            else 0.0
        )
        willingness = max(
            0.05,
            min(
                0.95,
                0.15 + 0.45 * relation_trust + 0.4 * donor_capacity,
            ),
        )
        response_value = _stable_unit(
            world.seed + day * 9973,
            requestor.household_id + ":" + donor.household_id + ":" + aid_type,
        )
        willing = response_value < willingness
        accepted = False
        response_type = "rejected"
        response_details: dict[str, Any] = {}
        executed = False
        details: dict[str, Any] = {}
        stats[aid_type]["responses_received"] += 1
        if not capacity_available:
            if willing:
                stats[aid_type]["willing_no_current_resource"] += 1
                response_type = "willing_but_no_current_resource"
            else:
                stats[aid_type]["rejected"] += 1
            _record_social_reason(
                records,
                stats,
                day,
                aid_type,
                requestor,
                donor,
                (
                    "willing_but_no_current_resource"
                    if willing
                    else "request_rejected"
                ),
                distance_km=distance_km,
                willingness=willingness,
            )
        elif not willing:
            stats[aid_type]["rejected"] += 1
            _record_social_reason(
                records,
                stats,
                day,
                aid_type,
                requestor,
                donor,
                "request_rejected",
                distance_km=distance_km,
                willingness=willingness,
            )
        else:
            current_delivery = True
            if aid_type == "food":
                preview = _food_delivery_preview(world, donor, requestor)
                if preview is None:
                    current_delivery = False
                    response_type = "willing_but_no_current_food"
                    stats[aid_type]["willing_no_current_resource"] += 1
                else:
                    response_details = preview
                    commitment_roll = _stable_unit(
                        world.seed + day * 3301,
                        requestor.household_id
                        + ":food-commit:"
                        + donor.household_id,
                    )
                    current_delivery = (
                        commitment_roll
                        < 0.35 + 0.45 * donor_capacity + 0.2 * relation_trust
                    )
                    if not current_delivery:
                        promise = dict(preview)
                        promise["requestor_id"] = requestor.household_id
                        promise["due_day"] = day + 1
                        donor.pending_food_promises.append(promise)
                        response_type = "conditional_future_promise"
                        stats[aid_type]["conditional_promises"] += 1
            if current_delivery:
                accepted = True
                response_type = "current_delivery_commitment"
                stats[aid_type]["current_delivery_commitments"] += 1
                stats[aid_type]["accepted"] += 1
                executed, details = _execute_social_help(
                    world,
                    day,
                    aid_type,
                    donor,
                    requestor,
                    distance_km,
                    behavior_states,
                )
                if executed and aid_type != "care":
                    stats[aid_type]["executed"] += 1
                elif aid_type == "care":
                    details["execution_state"] = "scheduled_for_next_day"
                else:
                    stats[aid_type]["promises_failed"] += 1
                    stats[aid_type]["current_commitment_failures"] += 1
                    _record_social_reason(
                        records,
                        stats,
                        day,
                        aid_type,
                        requestor,
                        donor,
                        details.get("failure_reason", "execution_failed"),
                    )
            else:
                details = response_details
        records.append(
            {
                "day": day,
                "aid_type": aid_type,
                "requestor_id": requestor.household_id,
                "donor_id": donor.household_id,
                "distance_km": round(distance_km, 4),
                "relation_trust": round(relation_trust, 4),
                "donor_capacity_score": round(donor_capacity, 4),
                "willingness": round(willingness, 4),
                "accepted": accepted,
                "executed": executed and aid_type != "care",
                "response_type": response_type,
                "details": details,
            }
        )
        stats.setdefault("contact_counts", {}).setdefault(
            requestor.household_id, {}
        )[donor.household_id] = (
            stats.setdefault("contact_counts", {})
            .setdefault(requestor.household_id, {})
            .get(donor.household_id, 0)
            + 1
            )


def _process_food_promises(
    day: int,
    runtimes: dict[str, HouseholdRuntime],
    records: list[dict[str, Any]],
    stats: dict[str, Any],
) -> None:
    for donor in runtimes.values():
        remaining: list[dict[str, Any]] = []
        for promise in donor.pending_food_promises:
            if int(promise.get("due_day", day)) > day:
                remaining.append(promise)
                continue
            requestor = runtimes.get(str(promise.get("requestor_id", "")))
            resource_id = str(promise.get("food_resource", ""))
            kg = float(promise.get("food_kg", 0.0))
            available = donor.food_store_kg.get(resource_id, 0.0)
            if requestor is None or available <= 0.0 or kg <= 0.0:
                stats["food"]["promises_failed"] += 1
                stats["food"]["not_continued_reasons"][
                    "promise_failed_no_resource"
                ] = (
                    stats["food"]["not_continued_reasons"].get(
                        "promise_failed_no_resource", 0
                    )
                    + 1
                )
                records.append(
                    {
                        "day": day,
                        "aid_type": "food",
                        "requestor_id": promise.get("requestor_id"),
                        "donor_id": donor.household_id,
                        "accepted": True,
                        "executed": False,
                        "response_type": "promise_failed",
                        "details": {"reason": "promise_failed_no_resource"},
                    }
                )
                continue
            actual_kg = min(kg, available)
            donor.food_store_kg[resource_id] -= actual_kg
            requestor.food_store_kg[resource_id] = (
                requestor.food_store_kg.get(resource_id, 0.0)
                + actual_kg
            )
            kcal_per_kg = float(promise.get("kcal_per_kg", 0.0))
            transferred_kcal = actual_kg * kcal_per_kg
            donor.food_store_kcal = max(
                0.0, donor.food_store_kcal - transferred_kcal
            )
            requestor.food_store_kcal += transferred_kcal
            stats["food"]["promises_executed"] += 1
            stats["food"]["executed"] += 1
            records.append(
                {
                    "day": day,
                    "aid_type": "food",
                    "requestor_id": requestor.household_id,
                    "donor_id": donor.household_id,
                    "accepted": True,
                    "executed": True,
                    "response_type": "future_promise_delivered",
                    "details": {
                        "food_resource": resource_id,
                        "food_kg": round(actual_kg, 6),
                        "food_kcal": round(transferred_kcal, 3),
                    },
                }
            )
        donor.pending_food_promises = remaining


def _choose_social_need(
    requestor: HouseholdRuntime,
    weather: dict[str, float],
    behavior_states: dict[str, Any] | None,
) -> str | None:
    if requestor.last_water_ratio < 0.8:
        return "water"
    if requestor.last_care_hours > requestor.last_potential_hours * 0.7:
        return "care"
    if requestor.last_food_ratio < 0.75:
        return "food"
    if requestor.fire_quality <= 0.0:
        return "fire"
    if (
        requestor.shelter_quality < 0.5
        and weather.get("rainfall_mm", 0.0) > 1.0
    ):
        return "shelter"
    if behavior_states:
        key_skills = {
            "fire_friction",
            "acorn_processing",
            "fiber_cordage",
            "shelter_building",
            "water_safety",
        }
        for person in requestor.members:
            state = behavior_states.get(person.id)
            if state is None or person.life_stage not in {
                "adolescent",
                "adult",
                "elder",
            }:
                continue
            known = {
                subject.removeprefix("skill.")
                for subject in state.knowledge
                if subject.startswith("skill.")
            }
            if key_skills - known:
                return "teaching"
    return None


def _nearby_contact_households(
    world: WorldState,
    requestor: HouseholdRuntime,
    runtimes: list[HouseholdRuntime],
    max_distance_km: float,
    limit: int,
) -> list[tuple[float, HouseholdRuntime]]:
    candidates: list[tuple[float, HouseholdRuntime]] = []
    for candidate in runtimes:
        if candidate.household_id == requestor.household_id:
            continue
        distance = _distance_km(
            world, requestor.camp_cell_index, candidate.camp_cell_index
        )
        if distance <= max_distance_km:
            candidates.append((distance, candidate))
    candidates.sort(key=lambda item: (item[0], item[1].household_id))
    return candidates[:limit]


def _find_contactable_household(
    world: WorldState,
    requestor: HouseholdRuntime,
    candidates: list[tuple[float, HouseholdRuntime]],
    stats: dict[str, Any],
    aid_type: str,
    day: int,
) -> tuple[HouseholdRuntime, float] | None:
    for distance, candidate in candidates:
        pair_contacts = (
            stats.get("contact_counts", {})
            .get(requestor.household_id, {})
            .get(candidate.household_id, 0)
        )
        same_camp = (
            requestor.camp_cell_index == candidate.camp_cell_index
        )
        location_known = same_camp or pair_contacts > 0
        if location_known:
            stats[aid_type]["location_known"] += 1
        person_found = location_known or _stable_unit(
            world.seed + day * 241 + int(distance * 1000),
            requestor.household_id + ":find:" + candidate.household_id,
        ) < 0.4
        if person_found:
            stats[aid_type]["person_found"] += 1
        communication_chance = min(
            0.9,
            0.35
            + 0.12 * pair_contacts
            + min(0.3, requestor.last_remaining_hours / 20.0),
        )
        has_contact = person_found and _stable_unit(
            world.seed + day * 701,
            requestor.household_id + ":talk:" + candidate.household_id,
        ) < communication_chance
        if has_contact:
            stats[aid_type]["communication_opportunity"] += 1
            return candidate, distance
    return None


def _can_help_with(
    aid_type: str,
    donor: HouseholdRuntime,
    requestor: HouseholdRuntime,
    behavior_states: dict[str, Any] | None,
) -> bool:
    if aid_type == "water":
        requestor_has_mobile_member = any(
            person.life_stage != "infant" and person.mobility >= 0.5
            for person in requestor.members
        )
        donor_has_time = (
            donor.last_potential_hours - donor.last_labour_hours >= 0.5
        )
        return (
            donor.water_container_capacity_l >= 1.0
            or (requestor_has_mobile_member and donor_has_time)
        )
    if aid_type == "food":
        return _store_kcal_from_runtime(donor) > 0.0
    if aid_type == "fire":
        return donor.fire_quality >= 0.4
    if aid_type == "care":
        return donor.last_labour_hours < donor.last_potential_hours * 0.7
    if aid_type == "shelter":
        return (
            donor.shelter_quality >= 0.55
            and donor.shelter_guest_capacity_used < 2
        )
    if aid_type == "teaching":
        return bool(
            behavior_states
            and _teachable_skill(donor, requestor, behavior_states)
        )
    return False


def _help_capacity_score(
    aid_type: str,
    donor: HouseholdRuntime,
    requestor: HouseholdRuntime,
) -> float:
    if aid_type == "water":
        if donor.water_container_capacity_l >= 1.0:
            return min(1.0, donor.water_container_capacity_l / 8.0)
        return 0.3
    if aid_type == "food":
        demand = max(1.0, donor.last_consumed_kcal)
        return min(1.0, _store_kcal_from_runtime(donor) / (demand * 2.0))
    if aid_type == "fire":
        return min(1.0, donor.fire_quality)
    if aid_type == "care":
        return max(
            0.0,
            min(
                1.0,
                (donor.last_potential_hours - donor.last_labour_hours)
                / max(1.0, donor.last_potential_hours),
            ),
        )
    if aid_type == "shelter":
        return max(0.0, (2 - donor.shelter_guest_capacity_used) / 2.0)
    if aid_type == "teaching":
        return 0.6
    return 0.0


def _food_delivery_preview(
    world: WorldState,
    donor: HouseholdRuntime,
    requestor: HouseholdRuntime,
) -> dict[str, Any] | None:
    if not donor.food_store_kg:
        return None
    resource_id = max(donor.food_store_kg, key=donor.food_store_kg.get)
    spec = world.resource_spec(resource_id)
    donor_kcal = donor.food_store_kcal
    donor_surplus = max(0.0, donor_kcal - donor.last_consumed_kcal)
    requestor_need = max(
        0.0,
        sum(_daily_kcal_need(person) for person in requestor.members)
        - requestor.food_store_kcal,
    )
    transfer_kcal = min(donor_surplus * 0.25, requestor_need)
    if transfer_kcal <= 0.0:
        return None
    kg = min(
        donor.food_store_kg[resource_id],
        transfer_kcal / float(spec["kcal_per_kg"]),
    )
    if kg <= 0.0:
        return None
    return {
        "food_resource": resource_id,
        "food_kg": round(kg, 6),
        "food_kcal": round(kg * float(spec["kcal_per_kg"]), 3),
        "kcal_per_kg": float(spec["kcal_per_kg"]),
        "condition": "current_household_store",
    }


def _execute_social_help(
    world: WorldState,
    day: int,
    aid_type: str,
    donor: HouseholdRuntime,
    requestor: HouseholdRuntime,
    distance_km: float,
    behavior_states: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    if aid_type == "water":
        if donor.water_container_capacity_l <= 0.0:
            assisted_person = next(
                (
                    person
                    for person in requestor.members
                    if person.life_stage != "infant"
                    and person.mobility >= 0.5
                ),
                None,
            )
            if assisted_person is None:
                return False, {
                    "failure_reason": "no_mobile_person_to_escort"
                }
            requestor.pending_water_credit_l += 3.0
            donor.social_travel_debt_hours += distance_km * 2.0 / 4.5
            return True, {
                "assistance_type": "escort_to_water_source",
                "water_litres": 3.0,
                "execution_time": "next_day",
                "assisted_person_id": assisted_person.id,
            }
        delivered = min(
            max(0.0, 3.0 * len(requestor.members) - requestor.pending_water_credit_l),
            min(4.0, donor.water_container_capacity_l),
        )
        requestor.pending_water_credit_l += delivered
        donor.social_travel_debt_hours += distance_km * 2.0 / 4.5
        return delivered > 0.0, {"water_litres": delivered}
    if aid_type == "food":
        store = donor.food_store_kg
        if not store:
            return False, {"failure_reason": "donor_store_empty"}
        resource_id = max(store, key=store.get)
        donor_kcal = _store_kcal_from_runtime(donor)
        donor_surplus = max(0.0, donor_kcal - donor.last_consumed_kcal)
        requestor_need = max(
            0.0,
            sum(_daily_kcal_need(person) for person in requestor.members)
            - _store_kcal_from_runtime(requestor),
        )
        transfer_kcal = min(
            donor_surplus * 0.25,
            requestor_need,
        )
        if transfer_kcal <= 0.0:
            return False, {
                "failure_reason": "accepted_no_deliverable_surplus"
            }
        spec = world.resource_spec(resource_id)
        kg = min(
            store[resource_id],
            transfer_kcal / float(spec["kcal_per_kg"]),
        )
        store[resource_id] -= kg
        requestor.food_store_kg[resource_id] = (
            requestor.food_store_kg.get(resource_id, 0.0) + kg
        )
        transferred_kcal = kg * float(spec["kcal_per_kg"])
        donor.food_store_kcal = max(0.0, donor.food_store_kcal - transferred_kcal)
        requestor.food_store_kcal += transferred_kcal
        return kg > 0.0, {
            "food_resource": resource_id,
            "food_kg": round(kg, 6),
            "food_kcal": round(transferred_kcal, 3),
        }
    if aid_type == "fire":
        if distance_km * 2.0 / 4.5 > 1.0:
            return False, {"failure_reason": "fire_transport_too_far"}
        donor.fire_quality = max(0.3, donor.fire_quality - 0.1)
        requestor.fire_quality = max(requestor.fire_quality, 0.6)
        donor.social_travel_debt_hours += distance_km * 2.0 / 4.5
        return True, {
            "fire_quality_received": round(requestor.fire_quality, 3),
            "transport_hours": round(distance_km * 2.0 / 4.5, 4),
        }
    if aid_type == "care":
        available = max(
            0.0,
            donor.last_potential_hours - donor.last_labour_hours,
        )
        accepted_hours = min(2.0, available)
        requestor.pending_care_credit_hours += accepted_hours
        donor.social_travel_debt_hours += 0.25
        return accepted_hours > 0.0, {
            "care_hours": round(accepted_hours, 4),
            "execution_time": "next_day",
        }
    if aid_type == "shelter":
        if donor.shelter_quality < 0.55 or donor.shelter_guest_capacity_used >= 2:
            return False, {"failure_reason": "shelter_capacity_full"}
        protected_people = min(2, 2 - donor.shelter_guest_capacity_used)
        donor.shelter_guest_capacity_used += protected_people
        requestor.shelter_quality = max(requestor.shelter_quality, 0.65)
        return True, {
            "protected_people": protected_people,
            "duration": "temporary_one_night",
        }
    if aid_type == "teaching":
        skill_id = _teachable_skill(donor, requestor, behavior_states or {})
        if not skill_id or not behavior_states:
            return False, {"failure_reason": "teaching_opportunity_lost"}
        learner = next(
            (
                behavior_states[person.id]
                for person in requestor.members
                if person.id in behavior_states
                and not behavior_states[person.id].knows(
                    f"skill.{skill_id}", "demonstrated"
                )
            ),
            None,
        )
        teacher = next(
            (
                behavior_states[person.id]
                for person in donor.members
                if person.id in behavior_states
                and behavior_states[person.id].knows(
                    f"skill.{skill_id}", "can_teach"
                )
            ),
            None,
        )
        if learner is None or teacher is None:
            return False, {"failure_reason": "teacher_or_learner_unavailable"}
        learner.receive_knowledge(
            f"skill.{skill_id}",
            "demonstrated",
            teacher.person_id,
            day,
            0.6,
        )
        donor.social_travel_debt_hours += 0.5
        requestor.social_travel_debt_hours += 0.5
        return True, {"skill_id": skill_id, "stage": "demonstrated"}
    return False, {"failure_reason": "unsupported_aid_type"}


def _teachable_skill(
    donor: HouseholdRuntime,
    requestor: HouseholdRuntime,
    behavior_states: dict[str, Any],
) -> str | None:
    donor_skills = {
        skill["id"]
        for person in donor.members
        for skill in person.skills
        if person.id in behavior_states
        and behavior_states[person.id].knows(
            f"skill.{skill['id']}", "can_teach"
        )
    }
    requestor_skills = {
        skill["id"]
        for person in requestor.members
        for skill in person.skills
    }
    candidates = sorted(donor_skills - requestor_skills)
    return candidates[0] if candidates else None


def _relationship_trust(
    stats: dict[str, Any],
    first: HouseholdRuntime,
    second: HouseholdRuntime,
) -> float:
    counts = stats.get("contact_counts", {})
    contact_count = counts.get(first.household_id, {}).get(
        second.household_id, 0
    )
    return min(0.8, 0.2 + 0.08 * contact_count)


def _store_kcal_from_runtime(runtime: HouseholdRuntime) -> float:
    return runtime.food_store_kcal


def _record_social_reason(
    records: list[dict[str, Any]],
    stats: dict[str, Any],
    day: int,
    aid_type: str,
    requestor: HouseholdRuntime,
    donor: HouseholdRuntime | None,
    reason: str,
    *,
    distance_km: float | None = None,
    willingness: float | None = None,
) -> None:
    reasons = stats[aid_type]["not_continued_reasons"]
    reasons[reason] = reasons.get(reason, 0) + 1
    records.append(
        {
            "day": day,
            "aid_type": aid_type,
            "requestor_id": requestor.household_id,
            "donor_id": donor.household_id if donor else None,
            "distance_km": distance_km,
            "willingness": willingness,
            "accepted": False,
            "executed": False,
            "reason": reason,
        }
    )


def _summarize_body_day(
    behavior_states: dict[str, Any],
    day: int,
) -> dict[str, Any]:
    capacities = [
        state.body.work_capacity for state in behavior_states.values()
    ]
    return {
        "day": day,
        "mean_work_capacity": round(mean(capacities), 4),
        "minimum_work_capacity": round(min(capacities), 4),
        "people_with_hunger_at_cap": sum(
            state.body.hunger >= 0.999 for state in behavior_states.values()
        ),
        "people_with_thirst_at_cap": sum(
            state.body.thirst >= 0.999 for state in behavior_states.values()
        ),
    }


def _build_person_activity_records(
    runtime: HouseholdRuntime,
    day: int,
    potential_hours: float,
    care_hours: float,
    remaining_hours: float,
    category_hours: dict[str, float],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    capacities: dict[str, float] = {}
    for person in runtime.members:
        if person.life_stage in {"infant", "toddler"}:
            capacity = 0.0
        elif person.life_stage == "child":
            capacity = 1.6 if person.age_years >= 6 else 0.0
        elif person.life_stage == "adolescent":
            capacity = 3.5
        elif person.life_stage == "adult":
            capacity = 8.0
        else:
            capacity = 4.0
        body_state = runtime.body_states.get(person.id)
        body_factor = (
            body_state.body.work_capacity if body_state is not None else 1.0
        )
        capacities[person.id] = (
            capacity * person.mobility * body_factor
        )
    assigned = {person_id: 0.0 for person_id in capacities}
    care_by_person: dict[str, float] = defaultdict(float)
    care_targets_by_person: dict[str, list[str]] = defaultdict(list)
    for dependent in runtime.members:
        care = {
            "infant": 5.0,
            "toddler": 3.0,
            "child": 1.0,
        }.get(dependent.life_stage, 0.0)
        if care <= 0.0:
            continue
        caregivers = [
            person
            for person in runtime.members
            if person.id in dependent.caregiver_ids
            and capacities.get(person.id, 0.0) > 0.0
        ]
        if not caregivers:
            caregivers = [
                person
                for person in runtime.members
                if person.life_stage in {"adult", "elder"}
            ][:1]
        if not caregivers:
            continue
        share = care / len(caregivers)
        for caregiver in caregivers:
            actual = min(
                share,
                max(0.0, capacities[caregiver.id] - assigned[caregiver.id]),
            )
            care_by_person[caregiver.id] += actual
            if actual > 0.0:
                care_targets_by_person[caregiver.id].append(dependent.id)
            assigned[caregiver.id] += actual

    eligible_by_category = {
        "water": {
            person.id
            for person in runtime.members
            if person.mobility >= 0.5
            and person.life_stage not in {"infant"}
        },
        "food_harvest_and_processing": {
            person.id
            for person in runtime.members
            if person.life_stage
            in {"child", "adolescent", "adult", "elder"}
        },
        "shelter": {
            person.id
            for person in runtime.members
            if person.life_stage in {"adolescent", "adult", "elder"}
        },
        "fire": {
            person.id
            for person in runtime.members
            if any(
                skill["id"] in {"fire_friction", "fire_keeping"}
                for skill in person.skills
            )
        },
        "tools": {
            person.id
            for person in runtime.members
            if any(
                skill["id"] in {"stone_tool_making", "wood_working"}
                for skill in person.skills
            )
        },
    }
    category_assignments: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for category, hours in category_hours.items():
        eligible = eligible_by_category.get(
            category,
            {
                person.id
                for person in runtime.members
                if capacities.get(person.id, 0.0) > 0.0
            },
        )
        if not eligible:
            eligible = {
                person.id
                for person in runtime.members
                if person.life_stage in {"adult", "elder"}
            }
        capacity_total = sum(
            max(0.0, capacities[person_id] - assigned[person_id])
            for person_id in eligible
        )
        if capacity_total <= 0.0:
            continue
        for person_id in sorted(eligible):
            available = max(
                0.0, capacities[person_id] - assigned[person_id]
            )
            if available <= 0.0:
                continue
            share = hours * available / capacity_total
            category_assignments[category][person_id] += share
            assigned[person_id] += share

    for person in runtime.members:
        cursor = 6 * 60
        care = care_by_person.get(person.id, 0.0)
        if care > 0.0:
            care_location = runtime.camp_cell_index
            records.append(
                _activity_record(
                    day,
                    person.id,
                    "care",
                    cursor,
                    care,
                    "rule_based_dependency_assignment",
                    care_location,
                    target_person_ids=care_targets_by_person.get(
                        person.id, []
                    ),
                )
            )
            cursor += int(round(care * 60))
        for category in sorted(category_hours):
            hours = category_assignments[category].get(person.id, 0.0)
            if hours <= 0.0:
                continue
            records.append(
                _activity_record(
                    day,
                    person.id,
                    category,
                    cursor,
                    hours,
                    "state_limited_household_task_allocation",
                    _activity_location(runtime, category),
                    detail=(
                        runtime.last_water_method
                        if category == "water"
                        else runtime.last_harvested_resource
                        if category == "food_harvest_and_processing"
                        else None
                    ),
                )
            )
            cursor += int(round(hours * 60))
        rest_hours = max(0.0, capacities[person.id] - assigned[person.id])
        if rest_hours > 0.0:
            records.append(
                _activity_record(
                    day,
                    person.id,
                    "rest_or_unused_capacity",
                    cursor,
                    rest_hours,
                    "remaining_personal_capacity",
                    runtime.camp_cell_index,
                )
            )
    return records


def _activity_record(
    day: int,
    person_id: str,
    category: str,
    start_minute: int,
    hours: float,
    assignment_source: str,
    location_cell: int,
    target_person_ids: list[str] | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "day": day,
        "person_id": person_id,
        "category": category,
        "start_minute": start_minute,
        "end_minute": min(24 * 60, start_minute + int(round(hours * 60))),
        "hours": round(hours, 6),
        "assignment_source": assignment_source,
        "location_cell": location_cell,
        "location_precision": (
            "resource_or_water_cell"
            if category in {"water", "food_harvest_and_processing"}
            else "household_camp_only"
        ),
        "eligibility_checked": True,
        "target_person_ids": target_person_ids or [],
        "detail": detail,
    }


def _activity_location(
    runtime: HouseholdRuntime,
    category: str,
) -> int:
    if category == "water":
        return runtime.nearest_water_cell_index
    if category == "food_harvest_and_processing":
        return runtime.last_food_activity_cell or runtime.camp_cell_index
    return runtime.camp_cell_index


def _available_labour_hours(
    runtime: HouseholdRuntime,
) -> tuple[float, float, float]:
    hours_by_person: dict[str, float] = {}
    for person in runtime.members:
        if person.life_stage == "infant" or person.life_stage == "toddler":
            base = 0.0
        elif person.life_stage == "child":
            base = 1.6 if person.age_years >= 6 else 0.0
        elif person.life_stage == "adolescent":
            base = 3.5
        elif person.life_stage == "adult":
            base = 8.0
        else:
            base = 4.0
        hours_by_person[person.id] = (
            base * person.mobility * runtime.work_capacity_multiplier
        )

    potential_hours = max(0.0, sum(hours_by_person.values()))
    care_hours = {
        "infant": 5.0,
        "toddler": 3.0,
        "child": 1.0,
    }
    for dependent in runtime.members:
        care = care_hours.get(dependent.life_stage, 0.0)
        if care <= 0.0:
            continue
        caregivers = [
            person
            for person in runtime.members
            if person.id in dependent.caregiver_ids
        ]
        if not caregivers:
            caregivers = [
                person
                for person in runtime.members
                if person.life_stage in {"adult", "elder"}
            ][:1]
        if caregivers:
            share = care / len(caregivers)
            for caregiver in caregivers:
                hours_by_person[caregiver.id] = max(
                    0.0, hours_by_person[caregiver.id] - share
                )
    available_hours = max(0.0, sum(hours_by_person.values()))
    care_hours = max(0.0, potential_hours - available_hours)
    return available_hours, care_hours, potential_hours


def _fetch_water(
    world: WorldState,
    runtime: HouseholdRuntime,
    litres_needed: float,
    available_hours: float,
    day: int,
    water_distance_cache: dict[int, float],
) -> tuple[float, float, str]:
    distance_km = _cached_water_distance(
        world, runtime.camp_cell_index, water_distance_cache
    )
    mobile_people = [
        person
        for person in runtime.members
        if person.mobility >= 0.5 and person.life_stage not in {"infant"}
    ]
    dependent_count = sum(
        person.life_stage in {"infant", "toddler"}
        or person.mobility < 0.5
        for person in runtime.members
        if person not in mobile_people
    )
    runtime.last_water_distance_km = distance_km
    runtime.last_mobile_people = len(mobile_people)
    runtime.last_dependent_people = dependent_count
    if not mobile_people:
        runtime.last_water_method = "no_mobile_person"
        runtime.last_water_hours = 0.0
        runtime.last_water_delivered_l = 0.0
        return 0.0, 0.0, "no_mobile_person"
    if day == 1:
        escort_trips = math.ceil(dependent_count / 2.0)
        drinkers = len(mobile_people) + min(
            dependent_count, max(0, len(mobile_people) // 2)
        )
        runtime.last_direct_capacity_l = drinkers * 3.0
        required_hours = (
            max(1, len(mobile_people)) * (_distance_walk_hours(distance_km) + 0.2)
            + escort_trips * _distance_walk_hours(distance_km)
        )
        method = "travel_to_source_and_drink_without_container"
        if required_hours <= available_hours:
            runtime.last_water_method = method
            runtime.last_water_hours = required_hours
            runtime.last_water_delivered_l = litres_needed
            world.water_volume_m3 = max(
                0.0, world.water_volume_m3 - litres_needed / 1000.0
            )
            return required_hours, litres_needed, method
        fraction = available_hours / required_hours if required_hours else 1.0
        delivered = litres_needed * max(0.0, min(1.0, fraction))
        runtime.last_water_method = method
        runtime.last_water_hours = available_hours
        runtime.last_water_delivered_l = delivered
        world.water_volume_m3 = max(
            0.0, world.water_volume_m3 - delivered / 1000.0
        )
        return available_hours, delivered, method

    vessel = world.baseline.raw["hydrology"].get(
        "water_vessel",
        {
            "type": "legacy_expedient_container",
            "capacity_l": 1.5,
            "craft_hours": 0.5,
            "wood_kg": 0.5,
            "fiber_kg": 0.2,
            "clay_kg": 0.0,
            "minimum_tool_quality": 0.0,
            "required_skill_any": [],
            "success_rate": 1.0,
            "leak_loss_fraction": 0.0,
        },
    )
    target_capacity = float(vessel["capacity_l"]) * max(1, len(mobile_people))
    if (
        runtime.water_container_capacity_l < target_capacity
        and runtime.water_vessel_blocked_reason is None
        and day - runtime.last_water_vessel_attempt_day >= 5
    ):
        runtime.last_water_vessel_attempt_day = day
        maker = _choose_vessel_maker(runtime, vessel["required_skill_any"])
        if maker is None:
            runtime.water_vessel_blocked_reason = "no_skilled_maker"
            runtime.water_vessel_failure_reasons["no_skilled_maker"] = (
                runtime.water_vessel_failure_reasons.get(
                    "no_skilled_maker", 0
                )
                + 1
            )
        elif runtime.tool_quality < float(vessel["minimum_tool_quality"]):
            runtime.water_vessel_blocked_reason = "tools_not_ready"
            runtime.water_vessel_failure_reasons["tools_not_ready"] = (
                runtime.water_vessel_failure_reasons.get(
                    "tools_not_ready", 0
                )
                + 1
            )
        elif available_hours < float(vessel["craft_hours"]):
            runtime.water_vessel_failure_reasons["no_time"] = (
                runtime.water_vessel_failure_reasons.get("no_time", 0) + 1
            )
        else:
            fiber = _nearest_material_kg(
                world, runtime, "fiber", float(vessel["fiber_kg"])
            )
            wood = _nearest_material_kg(
                world, runtime, "wood", float(vessel["wood_kg"])
            )
            clay = _nearest_material_kg(
                world, runtime, "clay", float(vessel["clay_kg"])
            )
            available_hours -= float(vessel["craft_hours"])
            runtime.water_vessel_attempts += 1
            materials_ok = (
                fiber >= float(vessel["fiber_kg"]) * 0.95
                and wood >= float(vessel["wood_kg"]) * 0.95
                and clay >= float(vessel["clay_kg"]) * 0.95
            )
            if not materials_ok:
                runtime.water_vessel_failures += 1
                runtime.water_vessel_failure_reasons["missing_material"] = (
                    runtime.water_vessel_failure_reasons.get(
                        "missing_material", 0
                    )
                    + 1
                )
                if runtime.water_vessel_attempts >= 3:
                    runtime.water_vessel_blocked_reason = "missing_material"
            else:
                success_value = _stable_unit(
                    world.seed + day * 811, runtime.household_id
                )
                if success_value < float(vessel["success_rate"]):
                    runtime.water_container_capacity_l = min(
                        target_capacity,
                        runtime.water_container_capacity_l
                        + float(vessel["capacity_l"]),
                    )
                    runtime.water_container_built_day = day
                    runtime.water_vessel_maker_ids.append(maker.id)
                else:
                    runtime.water_vessel_failures += 1
                    runtime.water_vessel_failure_reasons["craft_failed"] = (
                        runtime.water_vessel_failure_reasons.get(
                            "craft_failed", 0
                        )
                        + 1
                    )
                    if runtime.water_vessel_attempts >= 3:
                        runtime.water_vessel_blocked_reason = "craft_failed"
    carry_capacity = runtime.water_container_capacity_l
    if carry_capacity <= 0.0:
        drinkers = len(mobile_people) + min(
            dependent_count, max(0, len(mobile_people) // 2)
        )
        direct_capacity = drinkers * 3.0
        runtime.last_direct_capacity_l = direct_capacity
        required_hours = (
            max(1, len(mobile_people))
            * (_distance_walk_hours(distance_km) + 0.2)
            + math.ceil(dependent_count / 2.0)
            * _distance_walk_hours(distance_km)
        )
        if required_hours <= available_hours:
            delivered = min(litres_needed, direct_capacity)
            runtime.last_water_method = "travel_to_source_without_vessel"
            runtime.last_water_hours = required_hours
            runtime.last_water_delivered_l = delivered
            world.water_volume_m3 = max(
                0.0, world.water_volume_m3 - delivered / 1000.0
            )
            return required_hours, delivered, "travel_to_source_without_vessel"
        fraction = available_hours / required_hours if required_hours else 1.0
        delivered = min(litres_needed, direct_capacity * fraction)
        runtime.last_water_method = "travel_to_source_without_vessel"
        runtime.last_water_hours = available_hours
        runtime.last_water_delivered_l = delivered
        world.water_volume_m3 = max(
            0.0, world.water_volume_m3 - delivered / 1000.0
        )
        return available_hours, delivered, "travel_to_source_without_vessel"
    effective_capacity = carry_capacity * (
        1.0 - float(vessel["leak_loss_fraction"])
    )
    trips = litres_needed / max(0.1, effective_capacity)
    hours_per_trip = _distance_walk_hours(distance_km) + 0.18
    required_hours = trips * hours_per_trip
    if required_hours <= available_hours:
        withdrawn = trips * carry_capacity
        runtime.last_water_method = "carried_in_expedient_vessels"
        runtime.last_water_hours = required_hours
        runtime.last_water_delivered_l = litres_needed
        world.water_volume_m3 = max(
            0.0, world.water_volume_m3 - withdrawn / 1000.0
        )
        return required_hours, litres_needed, "carried_in_expedient_vessels"
    fraction = available_hours / required_hours if required_hours else 1.0
    completed_trips = trips * max(0.0, min(1.0, fraction))
    delivered = min(
        litres_needed, completed_trips * effective_capacity
    )
    runtime.last_water_method = "carried_in_expedient_vessels"
    runtime.last_water_hours = available_hours
    runtime.last_water_delivered_l = delivered
    withdrawn = completed_trips * carry_capacity
    world.water_volume_m3 = max(
        0.0, world.water_volume_m3 - withdrawn / 1000.0
    )
    return available_hours, delivered, "carried_in_expedient_vessels"


def _advance_shelter(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
) -> None:
    if runtime.shelter_quality >= 1.0 or hours <= 0.0:
        return
    runtime.shelter_attempt_hours += hours
    wood = _nearest_material_kg(world, runtime, "wood", hours * 3.0)
    fiber = _nearest_material_kg(
        world, runtime, "fiber", hours * 0.7
    )
    if wood <= 0.0:
        runtime.shelter_material_failure_days += 1
        return
    material_factor = min(1.0, wood / 12.0) * min(1.0, fiber / 2.0 + 0.35)
    runtime.shelter_quality = min(
        1.0, runtime.shelter_quality + hours / 7.0 * material_factor
    )
    if (
        runtime.shelter_quality >= 0.75
        and runtime.shelter_completed_day is None
    ):
        runtime.shelter_completed_day = (
            world.elapsed_days if world.elapsed_days > 0 else None
        )


def _advance_tools(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
) -> None:
    if hours <= 0.0:
        return
    stone = _nearest_material_kg(world, runtime, "stone", hours * 2.0)
    wood = _nearest_material_kg(world, runtime, "wood", hours * 1.0)
    if stone <= 0.0 or wood <= 0.0:
        return
    can_make = bool(
        {"stone_tool_making", "wood_working"} & runtime.skills
    )
    gain = hours * (0.3 if can_make else 0.08)
    runtime.tool_quality = min(1.0, runtime.tool_quality + gain)
    if runtime.tool_quality >= 0.65 and runtime.tool_completed_day is None:
        runtime.tool_completed_day = (
            world.elapsed_days if world.elapsed_days > 0 else None
        )


def _advance_fire(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
    day: int,
) -> None:
    if runtime.fire_quality > 0.0:
        if hours <= 0.0:
            return
        wood = _nearest_material_kg(world, runtime, "wood", 1.2)
        runtime.fire_quality = 0.85 if wood >= 0.5 else 0.0
        return
    if hours <= 0.0:
        runtime.fire_days_without_time += 1
        return
    if day - runtime.last_fire_material_search_day < 5:
        return
    wood = _nearest_material_kg(world, runtime, "wood", 2.0)
    fiber = _nearest_material_kg(world, runtime, "fiber", 0.5)
    if wood < 0.5 or fiber < 0.1:
        runtime.last_fire_material_search_day = day
        runtime.fire_material_search_failures += 1
        return
    if runtime.fire_first_attempt_day is None:
        runtime.fire_first_attempt_day = day
    runtime.last_fire_material_search_day = day
    runtime.fire_attempts += 1
    skilled = bool({"fire_friction", "fire_keeping"} & runtime.skills)
    attempt_value = _stable_unit(
        world.seed + day * 131, runtime.household_id
    )
    success_threshold = hours * (0.27 if skilled else 0.035)
    if attempt_value < success_threshold:
        runtime.fire_quality = 0.9
        if runtime.fire_first_success_day is None:
            runtime.fire_first_success_day = day
    else:
        runtime.fire_quality = 0.0
        runtime.fire_failures += 1
        runtime.fire_failure_reasons["failed_attempt"] = (
            runtime.fire_failure_reasons.get("failed_attempt", 0) + 1
        )


def _harvest_food(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
    target_kcal: float,
    consumption: dict[str, float],
    harvest_details: dict[str, dict[str, float]],
    daily_harvest_details: list[dict[str, float | str]],
    time_account: dict[str, float],
    food_obstacles: dict[str, int],
    food_path_records: list[dict[str, Any]] | None,
) -> tuple[float, float]:
    if hours <= 0.0 or target_kcal <= 0.0:
        return 0.0, 0.0
    acquired = 0.0
    selected_resource: str | None = None
    selected_resources: list[str] = []
    selected_cells: list[int] = []
    known_resources: dict[str, float] = defaultdict(float)
    decision_reasons: dict[str, int] = defaultdict(int)
    remaining_hours = hours
    for resource_id, cell_index, _, _ in runtime.supply_options:
        if not world.is_available(resource_id):
            continue
        spec = world.resource_spec(resource_id)
        if not _can_harvest_by_member(spec, runtime):
            continue
        known_resources[resource_id] += _available_stock_kcal(
            world, resource_id, cell_index
        )
    for resource_id, cell_index, _, distance_km in runtime.supply_options:
        if remaining_hours <= 0.02 or acquired >= target_kcal:
            break
        spec = world.resource_spec(resource_id)
        if not world.is_available(resource_id):
            food_obstacles["not_mature_or_out_of_season"] += 1
            decision_reasons["not_mature_or_out_of_season"] += 1
            continue
        if not _can_harvest_by_member(spec, runtime):
            food_obstacles["no_household_member_with_knowledge"] += 1
            decision_reasons["no_household_member_with_knowledge"] += 1
            continue
        if resource_id in world.plant_stock_kg:
            stock = world.plant_stock_kg[resource_id][cell_index]
        else:
            stock = world.animal_stock_kg[resource_id][cell_index]
        if stock <= 0.001:
            food_obstacles["local_stock_depleted"] += 1
            decision_reasons["local_stock_depleted"] += 1
            continue
        travel_hours = _distance_walk_hours(distance_km)
        effective_hours = remaining_hours - travel_hours
        if effective_hours <= 0.02:
            food_obstacles["no_time_after_travel"] += 1
            decision_reasons["no_time_after_travel"] += 1
            continue
        edible_yield = float(spec.get("edible_yield_fraction", 1.0))
        if edible_yield <= 0.0:
            continue
        tool_factor = 0.65 + 0.45 * runtime.tool_quality
        harvest_rate = float(spec["harvest_kg_per_hour"]) * tool_factor
        processing_rate = float(spec["processing_hours_per_kg"])
        hours_per_stock_kg = (
            1.0 / max(0.05, harvest_rate)
            + processing_rate * edible_yield
        )
        stock_kg_by_hours = effective_hours / hours_per_stock_kg
        stock_kg_by_need = max(
            0.0,
            (target_kcal - acquired)
            / (float(spec["kcal_per_kg"]) * edible_yield),
        )
        stock_kg = min(stock, stock_kg_by_hours, stock_kg_by_need)
        if stock_kg <= 0.001:
            continue
        harvest_hours = stock_kg / max(0.05, harvest_rate)
        processing_hours = stock_kg * processing_rate * edible_yield
        used_hours = travel_hours + harvest_hours + processing_hours
        remaining_hours -= used_hours
        if resource_id in world.plant_stock_kg:
            array = world.plant_stock_kg[resource_id]
            capacity = world.plant_capacity_kg[resource_id][cell_index]
        else:
            array = world.animal_stock_kg[resource_id]
            capacity = world.animal_capacity_kg[resource_id][cell_index]
        array[cell_index] -= stock_kg
        if runtime.last_food_activity_cell is None:
            runtime.last_food_activity_cell = cell_index
        if capacity > 0.0 and stock_kg / capacity > 0.55:
            if resource_id in world.plant_regen_condition:
                world.plant_regen_condition[resource_id][cell_index] = max(
                    0.35,
                    world.plant_regen_condition[resource_id][cell_index] - 0.08,
                )
        success_rate = _processing_success_rate(resource_id, spec)
        attempt_value = _stable_unit(
            world.seed + world.elapsed_days * 997 + cell_index,
            runtime.household_id,
        )
        edible_kg = stock_kg * edible_yield
        details = harvest_details[resource_id]
        if attempt_value > success_rate:
            edible_kg = 0.0
            details["processing_failures"] += 1
            food_obstacles["processing_failed"] += 1
            decision_reasons["processing_failed"] += 1
        runtime.food_store_kg[resource_id] = (
            runtime.food_store_kg.get(resource_id, 0.0) + edible_kg
        )
        if selected_resource is None:
            selected_resource = resource_id
        selected_resources.append(resource_id)
        selected_cells.append(cell_index)
        runtime.food_store_kcal += edible_kg * float(spec["kcal_per_kg"])
        consumption[resource_id] = (
            consumption.get(resource_id, 0.0) + stock_kg
        )
        record_resource_harvest(world, resource_id, stock_kg)
        details["stock_kg_removed"] += stock_kg
        details["edible_food_kg"] += edible_kg
        details["edible_kcal"] += edible_kg * float(spec["kcal_per_kg"])
        details["harvest_hours"] += harvest_hours
        details["processing_hours"] += processing_hours
        details["travel_hours"] += travel_hours
        details["processing_attempts"] += 1
        time_account["food_harvest"] += harvest_hours
        time_account["food_processing"] += processing_hours
        time_account["food_travel"] += travel_hours
        daily_harvest_details.append(
            {
                "day": world.elapsed_days,
                "household_id": runtime.household_id,
                "resource_id": resource_id,
                "cell_index": cell_index,
                "stock_kg_removed": stock_kg,
                "edible_food_kg": edible_kg,
                "edible_kcal": edible_kg * float(spec["kcal_per_kg"]),
                "harvest_hours": harvest_hours,
                "processing_hours": processing_hours,
                "travel_hours": travel_hours,
                "processing_failure": 1.0 if edible_kg <= 0.0 else 0.0,
            }
        )
        acquired += edible_kg * float(spec["kcal_per_kg"])
    if selected_resource is not None:
        runtime.last_harvested_resource = selected_resource
    if food_path_records is not None:
        food_path_records.append(
            {
                "day": world.elapsed_days,
                "household_id": runtime.household_id,
                "camp_cell_index": runtime.camp_cell_index,
                "known_resources": {
                    resource_id: round(kcal, 3)
                    for resource_id, kcal in sorted(known_resources.items())
                },
                "selected_resources": selected_resources,
                "selected_cells": selected_cells,
                "decision_reasons": dict(sorted(decision_reasons.items())),
                "hours_available": round(hours, 4),
                "hours_used": round(hours - remaining_hours, 4),
            }
        )
    return acquired, hours - remaining_hours


def _consume_food(
    world: WorldState,
    runtime: HouseholdRuntime,
    demand_kcal: float,
) -> float:
    available = _store_kcal(world, runtime)
    consumed_target = min(demand_kcal, available)
    remaining = consumed_target
    priority = sorted(
        runtime.food_store_kg,
        key=lambda resource_id: (
            SPOILAGE_PER_DAY.get(resource_id, 0.1),
            -float(world.resource_spec(resource_id)["kcal_per_kg"]),
        ),
        reverse=True,
    )
    for resource_id in priority:
        if remaining <= 0.0:
            break
        spec = world.resource_spec(resource_id)
        available_kg = runtime.food_store_kg.get(resource_id, 0.0)
        available_kcal = available_kg * float(spec["kcal_per_kg"])
        used_kcal = min(available_kcal, remaining)
        used_kg = used_kcal / float(spec["kcal_per_kg"])
        runtime.food_store_kg[resource_id] = max(0.0, available_kg - used_kg)
        runtime.food_store_kcal = max(
            0.0, runtime.food_store_kcal - used_kcal
        )
        remaining -= used_kcal
    return consumed_target


def _spoil_food(world: WorldState, runtime: HouseholdRuntime) -> None:
    for resource_id, kg in list(runtime.food_store_kg.items()):
        rate = SPOILAGE_PER_DAY.get(resource_id, 0.05)
        new_kg = kg * (1.0 - rate)
        lost_kg = kg - new_kg
        runtime.food_store_kg[resource_id] = new_kg
        runtime.food_store_kcal = max(
            0.0,
            runtime.food_store_kcal
            - lost_kg
            * float(world.resource_spec(resource_id)["kcal_per_kg"]),
        )
        if runtime.food_store_kg[resource_id] < 0.0001:
            del runtime.food_store_kg[resource_id]


def _store_kcal(world: WorldState, runtime: HouseholdRuntime) -> float:
    return runtime.food_store_kcal


def _daily_kcal_need(person: Person) -> float:
    if person.life_stage == "infant":
        return 800.0
    if person.life_stage == "toddler":
        return 1250.0
    if person.life_stage == "child":
        return 1650.0
    if person.life_stage == "adolescent":
        return 2200.0
    if person.life_stage == "elder":
        return 1900.0
    if person.mobility < 0.7:
        return 1900.0
    return 2300.0


def _storage_target_fraction(day: int, start_day_of_year: int) -> float:
    day_of_year = ((start_day_of_year - 1 + day - 1) % 365) + 1
    if 225 <= day_of_year <= 335:
        return 180.0
    if day_of_year > 335 or day_of_year < 60:
        return 120.0
    if day_of_year < 120:
        return 60.0
    return 5.0


def _can_harvest_by_member(
    spec: dict[str, Any],
    runtime: HouseholdRuntime,
) -> bool:
    for person in runtime.members:
        if person.life_stage in {"infant", "toddler"}:
            continue
        if person.life_stage == "adult" or person.life_stage == "elder":
            if spec.get("common_knowledge"):
                return True
        if any(
            skill["id"] == spec["knowledge_skill"]
            for skill in person.skills
        ):
            return True
    return False


def _known_available_food_kcal(
    world: WorldState,
    runtime: HouseholdRuntime,
) -> float:
    return sum(
        _available_stock_kcal(world, resource_id, cell_index)
        for resource_id, cell_index in _known_food_cells(world, runtime)
    )


def _known_food_cells(
    world: WorldState,
    runtime: HouseholdRuntime,
) -> set[tuple[str, int]]:
    cells: set[tuple[str, int]] = set()
    for resource_id, cell_index, _, _ in runtime.supply_options:
        if not world.is_available(resource_id):
            continue
        spec = world.resource_spec(resource_id)
        if not _can_harvest_by_member(spec, runtime):
            continue
        cells.add((resource_id, cell_index))
    return cells


def _available_stock_kcal(
    world: WorldState,
    resource_id: str,
    cell_index: int,
) -> float:
    spec = world.resource_spec(resource_id)
    stock = (
        world.plant_stock_kg[resource_id][cell_index]
        if resource_id in world.plant_stock_kg
        else world.animal_stock_kg[resource_id][cell_index]
    )
    return (
        stock
        * float(spec.get("edible_yield_fraction", 1.0))
        * float(spec["kcal_per_kg"])
    )


def _processing_success_rate(
    resource_id: str,
    spec: dict[str, Any],
) -> float:
    rates = {
        "cattail": 0.78,
        "arrowhead": 0.72,
        "mixed_berries": 0.95,
        "hazelnut": 0.9,
        "oak_acorn": 0.65,
        "spring_greens": 0.82,
        "fish": 0.7,
        "waterfowl": 0.72,
        "hare": 0.7,
        "deer": 0.65,
    }
    return float(spec.get("processing_success_rate", rates.get(resource_id, 0.8)))


def _choose_explorer(runtime: HouseholdRuntime) -> Person | None:
    candidates = [
        person
        for person in runtime.members
        if person.life_stage in {"adolescent", "adult", "elder"}
        and person.mobility >= 0.5
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda person: person.id)


def _choose_vessel_maker(
    runtime: HouseholdRuntime,
    required_skills: list[str],
) -> Person | None:
    eligible = [
        person
        for person in runtime.members
        if person.life_stage in {"adolescent", "adult", "elder"}
        and person.mobility >= 0.5
    ]
    if not required_skills:
        return min(eligible, key=lambda person: person.id) if eligible else None
    candidates = [
        person
        for person in eligible
        if any(skill["id"] in required_skills for skill in person.skills)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda person: person.id)


def _build_supply_options(
    world: WorldState,
    camp_cell_index: int,
) -> list[tuple[str, int, float, float]]:
    candidates: list[tuple[str, int, float, float]] = []
    camp = world.cells[camp_cell_index]
    for cell in world.cells:
        distance = _distance_km(world, camp_cell_index, cell.index)
        if distance > 4.0:
            continue
        for resource_id, spec in world.baseline.resource_specs.items():
            if cell.land_class not in spec["habitats"]:
                continue
            capacity = (
                world.plant_capacity_kg[resource_id][cell.index]
                if resource_id in world.plant_capacity_kg
                else world.animal_capacity_kg[resource_id][cell.index]
            )
            if capacity <= 0.0:
                continue
            rate = float(spec["kcal_per_kg"]) / (
                1.0 / max(0.05, float(spec["harvest_kg_per_hour"]))
                + float(spec["processing_hours_per_kg"])
            )
            travel = _distance_walk_hours(distance)
            score = rate / (1.0 + travel * 2.0)
            candidates.append((resource_id, cell.index, score, distance))
    candidates.sort(key=lambda item: item[2], reverse=True)
    by_resource: dict[str, list[tuple[str, int, float, float]]] = {}
    for candidate in candidates:
        by_resource.setdefault(candidate[0], []).append(candidate)
    selected: list[tuple[str, int, float, float]] = []
    for resource_candidates in by_resource.values():
        resource_candidates.sort(key=lambda item: item[2], reverse=True)
        selected.extend(resource_candidates[:40])
    selected.sort(key=lambda item: item[2], reverse=True)
    return selected


def _build_material_options(
    world: WorldState,
    camp_cell_index: int,
) -> dict[str, list[int]]:
    options: dict[str, list[int]] = {}
    for material_id in world.material_stock_kg:
        ranked = sorted(
            (
                cell.index
                for cell in world.cells
                if world.material_stock_kg[material_id][cell.index] > 0.0
            ),
            key=lambda index: (
                _distance_km(world, camp_cell_index, index),
                -world.material_stock_kg[material_id][index],
            ),
        )
        options[material_id] = ranked[:40]
    return options


def _camp_score(world: WorldState, cell_index: int) -> float:
    cell = world.cells[cell_index]
    if not cell.habitable:
        return -1_000_000.0
    perennial_food = 0.0
    for resource_id, spec in world.baseline.resource_specs.items():
        capacity = (
            world.plant_capacity_kg[resource_id][cell_index]
            if resource_id in world.plant_capacity_kg
            else world.animal_capacity_kg[resource_id][cell_index]
        )
        perennial_food += capacity * float(spec["kcal_per_kg"])
    wood = world.material_capacity_kg["wood"][cell_index]
    water_distance = cell.distance_to_water_km
    return (
        perennial_food / 1_000_000.0
        + min(4.0, wood / 500.0)
        + 8.0 / (0.25 + water_distance)
        - cell.flood_risk * 3.0
        - cell.slope_percent * 0.08
        + (1.0 if cell.cultivable else 0.0)
    )


def _nearest_material_kg(
    world: WorldState,
    runtime: HouseholdRuntime,
    material_id: str,
    requested_kg: float,
) -> float:
    if requested_kg <= 0.0:
        return 0.0
    remaining = requested_kg
    gathered = 0.0
    for cell_index in runtime.material_options[material_id]:
        if remaining <= 0.0:
            break
        stock = world.material_stock_kg[material_id][cell_index]
        amount = min(stock, remaining)
        world.material_stock_kg[material_id][cell_index] -= amount
        record_material_harvest(world, material_id, amount)
        remaining -= amount
        gathered += amount
    return gathered


def _nearest_water_distance_km(world: WorldState, camp_index: int) -> float:
    return min(
        _distance_km(world, camp_index, cell.index)
        for cell in world.water_cells
    )


def _nearest_water_cell_index(world: WorldState, camp_index: int) -> int:
    return min(
        (cell.index for cell in world.water_cells),
        key=lambda index: _distance_km(world, camp_index, index),
    )


def _cached_water_distance(
    world: WorldState,
    camp_index: int,
    cache: dict[int, float],
) -> float:
    value = cache.get(camp_index)
    if value is None:
        value = _nearest_water_distance_km(world, camp_index)
        cache[camp_index] = value
    return value


def _nearby_habitable_indices(
    world: WorldState,
    center_index: int,
    radius_cells: int,
) -> set[int]:
    center = world.cells[center_index]
    result: set[int] = set()
    for y in range(max(0, center.y - radius_cells), min(world.height, center.y + radius_cells + 1)):
        for x in range(max(0, center.x - radius_cells), min(world.width, center.x + radius_cells + 1)):
            cell = world.cells[y * world.width + x]
            if cell.habitable:
                result.add(cell.index)
    return result


def _distance_km(world: WorldState, first: int, second: int) -> float:
    first_cell = world.cells[first]
    second_cell = world.cells[second]
    dx = (first_cell.x - second_cell.x) * world.cell_size_m / 1000.0
    dy = (first_cell.y - second_cell.y) * world.cell_size_m / 1000.0
    return math.hypot(dx, dy)


def _distance_walk_hours(distance_km: float) -> float:
    return distance_km * 2.0 / 4.5


def _exploration_radius_km(day: int) -> float:
    return min(5.0, 0.8 + 0.23 * day)


def _summarize_windows(metrics: list[DayMetric]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for window_id, start, end in WINDOWS:
        selected = [metric for metric in metrics if start <= metric.day <= end]
        if not selected:
            continue
        food_ratios = [metric.food_ratio for metric in selected]
        household_minimums = [
            metric.food_ratio_household_min for metric in selected
        ]
        household_p10 = [
            metric.food_ratio_household_p10 for metric in selected
        ]
        water_ratios = [metric.water_ratio for metric in selected]
        min_food = min(household_minimums)
        min_water = min(water_ratios)
        average_food = mean(food_ratios)
        average_water = mean(water_ratios)
        worst_metric = min(
            selected,
            key=lambda metric: min(metric.food_ratio, metric.water_ratio),
        )
        bottleneck = (
            "water access"
            if min_water < min_food
            else "food acquisition"
            if min_food < 0.9
            else "shelter, fire, and storage timing"
        )
        feasible_paths: list[str] = []
        if min_water >= 0.9:
            feasible_paths.append("reach water and allocate caregiver-assisted delivery")
        if average_food >= 0.85:
            feasible_paths.append("use known seasonal resources with the available labor")
        if selected[-1].shelter_fraction >= 0.75:
            feasible_paths.append("build a weather barrier from wood and fiber")
        if selected[-1].fire_fraction >= 0.5:
            feasible_paths.append("produce or maintain fire with suitable material")
        results[window_id] = {
            "elapsed_day_range": [selected[0].day, selected[-1].day],
            "day_of_year_range": [
                selected[0].day_of_year,
                selected[-1].day_of_year,
            ],
            "spans_calendar_year": (
                selected[0].day_of_year > selected[-1].day_of_year
            ),
            "status": (
                "evaluated"
                if min_water >= 0.9 and average_food >= 0.85
                else "failed"
            ),
            "bottleneck": bottleneck,
            "feasible_paths": feasible_paths,
            "likely_failure": (
                "food shortfall and care-related labor loss"
                if min_food < min_water
                else "water access failure"
                if min_water < 0.9
                else "seasonal storage or shelter failure"
            ),
            "capacity_margin": round(min(average_food, average_water) - 1.0, 4),
            "minimum_food_ratio": round(min_food, 4),
            "minimum_household_food_ratio": round(min_food, 4),
            "p10_household_food_ratio": round(mean(household_p10), 4),
            "minimum_water_ratio": round(min_water, 4),
            "average_food_ratio": round(average_food, 4),
            "food_ratio_definition": (
                "demand-weighted consumed calories divided by fixed daily demand; "
                "minimum is the worst household-day, not a population average"
            ),
            "days_with_household_min_below_080": sum(
                item.food_ratio_household_min < 0.8 for item in selected
            ),
            "household_days_below_080": sum(
                item.households_below_080 for item in selected
            ),
            "mean_households_below_080_per_day": round(
                mean(item.households_below_080 for item in selected), 3
            ),
            "longest_consecutive_household_min_below_080": (
                _longest_streak(
                    item.food_ratio_household_min < 0.8
                    for item in selected
                )
            ),
            "average_water_ratio": round(average_water, 4),
            "worst_day": worst_metric.day,
            "shelter_fraction_end": selected[-1].shelter_fraction,
            "fire_fraction_end": selected[-1].fire_fraction,
            "tool_fraction_end": selected[-1].tool_fraction,
            "evidence": ["SHORT-RUN-VALIDATION", "ENV-MODEL-4000"],
        }
    return results


def _evaluate_paths(
    world: WorldState,
    metrics: list[DayMetric],
) -> dict[str, dict[str, Any]]:
    water_ok = min(metric.water_ratio for metric in metrics) >= 0.9
    food_average = mean(metric.food_ratio for metric in metrics)
    food_min = min(metric.food_ratio for metric in metrics)
    shelter_metric = metrics[min(6, len(metrics) - 1)]
    shelter_ok = shelter_metric.shelter_fraction >= 0.75
    fire_cold = [
        metric
        for metric in metrics
        if metric.day_of_year >= 300 or metric.day_of_year <= 80
    ]
    fire_ok = bool(fire_cold) and mean(
        metric.fire_fraction for metric in fire_cold
    ) >= 0.45
    tool_ok = shelter_metric.tool_fraction >= 0.65
    stable_supply_ok = (
        food_average >= 0.9
        and food_min >= 0.55
        and world.water_volume_m3 > world.water_capacity_m3 * 0.12
    )
    return {
        "water": {
            "status": "evaluated" if water_ok else "failed",
            "solution": (
                "direct lakeshore drinking plus caregiver-assisted daily delivery"
                if water_ok
                else "water delivery is infeasible for at least one tested day"
            ),
            "evidence": ["SIM-WATER-001"],
        },
        "food": {
            "status": "evaluated" if food_average >= 0.85 else "failed",
            "solution": (
                "seasonal gathering supplemented by fishing and autumn mast storage"
                if food_average >= 0.85
                else "available labor and processing throughput cannot cover demand"
            ),
            "evidence": ["SIM-FOOD-001"],
        },
        "shelter": {
            "status": "evaluated" if shelter_ok else "failed",
            "solution": (
                "wood-and-fiber lean-to built within the first three days"
                if shelter_ok
                else "material access or labor timing delays shelter"
            ),
            "evidence": ["SIM-SHELTER-001"],
        },
        "fire": {
            "status": "evaluated" if fire_ok else "failed",
            "solution": (
                "skilled friction attempts and repeated maintenance using dry wood"
                if fire_ok
                else "practical fire coverage is insufficient in cold periods"
            ),
            "evidence": ["SIM-FIRE-001"],
        },
        "tools": {
            "status": "evaluated" if tool_ok else "failed",
            "solution": (
                "expedient stone edges improved by stone and wood working"
                if tool_ok
                else "tool production is too slow for the modeled labor schedule"
            ),
            "evidence": ["SIM-TOOLS-001"],
        },
        "stable_supply": {
            "status": "evaluated" if stable_supply_ok else "failed",
            "solution": (
                "seasonal gathering, mast storage, and aquatic resources balance one modeled year"
                if stable_supply_ok
                else "annual storage, regeneration, or labor creates a survival gap"
            ),
            "evidence": ["SIM-YEAR-001"],
        },
    }


def _build_distribution_diagnostics(
    observations: list[dict[str, float]],
) -> dict[str, Any]:
    by_day: dict[int, list[dict[str, float]]] = defaultdict(list)
    for observation in observations:
        by_day[int(observation["day"])].append(observation)
    daily: list[dict[str, float]] = []
    for day, households in sorted(by_day.items()):
        demand = sum(item["demand_kcal"] for item in households)
        if demand <= 0.0:
            continue
        basic = (
            sum(
                min(item["available_kcal"], item["demand_kcal"])
                for item in households
            )
            / demand
        )
        ideal = min(
            1.0,
            sum(item["available_kcal"] for item in households) / demand,
        )
        constrained = _constrained_transfer_ratio(households)
        daily.append(
            {
                "day": float(day),
                "basic_ratio": basic,
                "ideal_costless_ratio": ideal,
                "constrained_ratio": constrained,
            }
        )
    basic_failure_days = sum(item["basic_ratio"] < 0.9 for item in daily)
    ideal_failure_days = sum(
        item["ideal_costless_ratio"] < 0.9 for item in daily
    )
    constrained_failure_days = sum(
        item["constrained_ratio"] < 0.9 for item in daily
    )
    distribution_only_days = sum(
        item["basic_ratio"] < 0.9
        and item["ideal_costless_ratio"] >= 0.9
        for item in daily
    )
    residual_total_days = sum(
        item["ideal_costless_ratio"] < 0.9 for item in daily
    )
    return {
        "classification": "diagnostic_only",
        "costless_redistribution": {
            "purpose": "upper-bound decomposition only; not a proposed behavior",
            "basic_failure_days": basic_failure_days,
            "ideal_upper_bound_failure_days": ideal_failure_days,
            "distribution_only_failure_days": distribution_only_days,
            "residual_supply_or_labor_failure_days": residual_total_days,
        },
        "constrained_cooperation": {
            "assumptions": (
                "surplus can move to a household within 1 km with 20 percent "
                "labor and transfer loss"
            ),
            "failure_days": constrained_failure_days,
            "improvement_days": sum(
                item["constrained_ratio"] > item["basic_ratio"] + 0.05
                for item in daily
            ),
        },
        "daily": daily,
    }


def _constrained_transfer_ratio(
    households: list[dict[str, float]],
) -> float:
    demand = sum(item["demand_kcal"] for item in households)
    if demand <= 0.0:
        return 1.0
    satisfied = sum(
        min(item["available_kcal"], item["demand_kcal"])
        for item in households
    )
    deficits = [
        {
            "remaining": max(
                0.0, item["demand_kcal"] - item["available_kcal"]
            ),
            "x": item["camp_x"],
            "y": item["camp_y"],
        }
        for item in households
        if item["available_kcal"] < item["demand_kcal"]
    ]
    surpluses = [
        {
            "remaining": item["available_kcal"] - item["demand_kcal"],
            "x": item["camp_x"],
            "y": item["camp_y"],
        }
        for item in households
        if item["available_kcal"] > item["demand_kcal"]
    ]
    for deficit in sorted(deficits, key=lambda item: item["remaining"], reverse=True):
        while deficit["remaining"] > 0.0:
            candidates = [
                surplus
                for surplus in surpluses
                if surplus["remaining"] > 0.0
                and math.hypot(
                    (deficit["x"] - surplus["x"]) * 0.1,
                    (deficit["y"] - surplus["y"]) * 0.1,
                )
                <= 1.0
            ]
            if not candidates:
                break
            donor = min(
                candidates,
                key=lambda surplus: math.hypot(
                    deficit["x"] - surplus["x"],
                    deficit["y"] - surplus["y"],
                ),
            )
            distance_km = math.hypot(
                (deficit["x"] - donor["x"]) * 0.1,
                (deficit["y"] - donor["y"]) * 0.1,
            )
            efficiency = max(0.6, 0.9 - distance_km * 0.2)
            moved = min(
                deficit["remaining"] / efficiency,
                donor["remaining"],
            )
            satisfied += moved * efficiency
            deficit["remaining"] -= moved * efficiency
            donor["remaining"] -= moved
    return min(1.0, satisfied / demand)


def _build_acquisition_paths(
    runtimes: dict[str, HouseholdRuntime],
    metrics: list[DayMetric],
    harvest_details: dict[str, dict[str, float]],
    baseline: dict[str, Any],
    water_method_counts: dict[str, int],
    daily_harvest_details: list[dict[str, float | str]],
    time_account: dict[str, float],
) -> dict[str, Any]:
    household_count = len(runtimes)
    return {
        "water": {
            "day_one_method": "travel to source and drink without a container",
            "later_method": "daily refill of expedient fiber-and-wood carrying vessels",
            "vessel_spec": baseline["hydrology"]["water_vessel"],
            "water_is_not_added_without_fetch_labour": True,
            "method_household_days": dict(sorted(water_method_counts.items())),
            "container_built_households": sum(
                runtime.water_container_built_day is not None
                for runtime in runtimes.values()
            ),
            "vessel_attempts": sum(
                runtime.water_vessel_attempts
                for runtime in runtimes.values()
            ),
            "vessel_failures": sum(
                runtime.water_vessel_failures
                for runtime in runtimes.values()
            ),
            "maker_assignments": sum(
                len(runtime.water_vessel_maker_ids)
                for runtime in runtimes.values()
            ),
            "blocked_reasons": {
                reason: sum(
                    runtime.water_vessel_blocked_reason == reason
                    for runtime in runtimes.values()
                )
                for reason in sorted(
                    {
                        runtime.water_vessel_blocked_reason
                        for runtime in runtimes.values()
                        if runtime.water_vessel_blocked_reason is not None
                    }
                )
            },
            "minimum_container_capacity_l": min(
                (
                    runtime.water_container_capacity_l
                    for runtime in runtimes.values()
                ),
                default=0.0,
            ),
        },
        "food": {
            resource_id: {
                "stock_kg_removed_per_person_day": round(
                    values["stock_kg_removed"]
                    / max(1, len(metrics) * 4000),
                    6,
                ),
                "edible_food_kg_per_person_day": round(
                    values["edible_food_kg"]
                    / max(1, len(metrics) * 4000),
                    6,
                ),
                "edible_kcal_per_person_day": round(
                    values["edible_kcal"]
                    / max(1, len(metrics) * 4000),
                    6,
                ),
                "harvest_hours": round(values["harvest_hours"], 4),
                "processing_hours": round(values["processing_hours"], 4),
                "travel_hours": round(values["travel_hours"], 4),
            }
            for resource_id, values in sorted(harvest_details.items())
        },
        "food_by_window": {
            window_id: _summarize_daily_harvest(
                daily_harvest_details, start, end
            )
            for window_id, start, end in WINDOWS
        },
        "shelter": _completion_summary(
            runtimes,
            "shelter_completed_day",
            int(baseline["start_day_of_year"]),
        ),
        "shelter_evidence": {
            "attempt_hours": round(
                sum(
                    runtime.shelter_attempt_hours
                    for runtime in runtimes.values()
                ),
                6,
            ),
            "material_failure_days": sum(
                runtime.shelter_material_failure_days
                for runtime in runtimes.values()
            ),
            "mean_final_quality": round(
                mean(
                    runtime.shelter_quality
                    for runtime in runtimes.values()
                ),
                4,
            ),
            "households_with_partial_cover": sum(
                runtime.shelter_quality >= 0.25
                for runtime in runtimes.values()
            ),
            "people_with_partial_cover": sum(
                len(runtime.members)
                for runtime in runtimes.values()
                if runtime.shelter_quality >= 0.25
            ),
            "progress_is_retained": True,
        },
        "fire": _completion_summary(
            runtimes,
            "fire_first_success_day",
            int(baseline["start_day_of_year"]),
        ),
        "fire_attempts": {
            "households_with_attempts": sum(
                runtime.fire_first_attempt_day is not None
                for runtime in runtimes.values()
            ),
            "first_attempt_days": _completion_summary(
                runtimes,
                "fire_first_attempt_day",
                int(baseline["start_day_of_year"]),
            ),
            "total_attempts": sum(
                runtime.fire_attempts for runtime in runtimes.values()
            ),
            "total_failures": sum(
                runtime.fire_failures for runtime in runtimes.values()
            ),
            "days_without_time": sum(
                runtime.fire_days_without_time
                for runtime in runtimes.values()
            ),
            "material_search_failures": sum(
                runtime.fire_material_search_failures
                for runtime in runtimes.values()
            ),
            "failure_reasons": {
                reason: sum(
                    runtime.fire_failure_reasons.get(reason, 0)
                    for runtime in runtimes.values()
                )
                for reason in sorted(
                    {
                        reason
                        for runtime in runtimes.values()
                        for reason in runtime.fire_failure_reasons
                    }
                )
            },
        },
        "tools": _completion_summary(
            runtimes,
            "tool_completed_day",
            int(baseline["start_day_of_year"]),
        ),
        "time_models": {
            "household_count": household_count,
            "days": len(metrics),
            "test_kind": "fixed_population_demand_pressure_test",
            "body_consequences": "not implemented",
        },
        "time_account_hours": {
            **{
                key: round(value, 6)
                for key, value in sorted(time_account.items())
            },
            "pending_social_travel_hours": round(
                sum(
                    runtime.social_travel_debt_hours
                    for runtime in runtimes.values()
                ),
                6,
            ),
            "closure_error_hours": round(
                time_account.get("potential", 0.0)
                - sum(
                    value
                    for key, value in time_account.items()
                    if key != "potential"
                ),
                6,
            ),
        },
        "raw_baseline_reference": baseline["world_id"],
    }


def _summarize_daily_harvest(
    details: list[dict[str, float | str]],
    start_day: int,
    end_day: int,
) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for entry in details:
        day = int(entry["day"])
        if not start_day <= day <= end_day:
            continue
        resource_id = str(entry["resource_id"])
        aggregate = summary.setdefault(
            resource_id,
            {
                "stock_kg_removed": 0.0,
                "edible_food_kg": 0.0,
                "edible_kcal": 0.0,
                "harvest_hours": 0.0,
                "processing_hours": 0.0,
                "travel_hours": 0.0,
                "processing_attempts": 0.0,
                "processing_failures": 0.0,
            },
        )
        aggregate["stock_kg_removed"] += float(entry["stock_kg_removed"])
        aggregate["edible_food_kg"] += float(entry["edible_food_kg"])
        aggregate["edible_kcal"] += float(entry["edible_kcal"])
        aggregate["harvest_hours"] += float(entry["harvest_hours"])
        aggregate["processing_hours"] += float(entry["processing_hours"])
        aggregate["travel_hours"] += float(entry["travel_hours"])
        aggregate["processing_attempts"] += 1.0
        aggregate["processing_failures"] += float(
            entry["processing_failure"]
        )
    return {
        resource_id: {
            key: round(value, 6) for key, value in values.items()
        }
        for resource_id, values in sorted(summary.items())
    }


def _completion_summary(
    runtimes: dict[str, HouseholdRuntime],
    attribute: str,
    start_day_of_year: int,
) -> dict[str, Any]:
    values = sorted(
        int(getattr(runtime, attribute))
        for runtime in runtimes.values()
        if getattr(runtime, attribute) is not None
    )
    completed_runtimes = [
        runtime
        for runtime in runtimes.values()
        if getattr(runtime, attribute) is not None
    ]
    return {
        "households_completed": len(values),
        "households_total": len(runtimes),
        "people_in_completed_households": sum(
            len(runtime.members) for runtime in completed_runtimes
        ),
        "median_completion_day": (
            values[len(values) // 2] if values else None
        ),
        "median_day_of_year": (
            ((start_day_of_year - 1 + values[len(values) // 2] - 1) % 365)
            + 1
            if values
            else None
        ),
        "last_completion_day": values[-1] if values else None,
        "last_day_of_year": (
            ((start_day_of_year - 1 + values[-1] - 1) % 365) + 1
            if values
            else None
        ),
    }


def _build_food_audit(
    initial_world: WorldState,
    population: PopulationState,
    runtimes: dict[str, HouseholdRuntime],
    metrics: list[DayMetric],
    consumption: dict[str, float],
    harvest_details: dict[str, dict[str, float]],
) -> dict[str, Any]:
    initial_total_kcal = sum(
        sum(values)
        * float(initial_world.resource_spec(resource_id)["kcal_per_kg"])
        * float(
            initial_world.resource_spec(resource_id).get(
                "edible_yield_fraction", 1.0
            )
        )
        for resource_id, values in {
            **initial_world.plant_stock_kg,
            **initial_world.animal_stock_kg,
        }.items()
    )
    final_total_kcal = metrics[-1].remaining_wild_food_kcal
    skill_holders = sum(
        any(skill["id"] in {"basic_plant_identification", "fishing"} for skill in person.skills)
        for person in population.people
        if person.life_stage in {"adult", "elder"}
    )
    no_tool_households = [
        runtime
        for runtime in runtimes.values()
        if runtime.tool_quality < 0.7
    ]
    return {
        "dimensions": {
            "mature": {
                "status": "known",
                "value": "seasonal availability windows are enforced per resource",
                "evidence": ["SIM-MATURITY-001"],
            },
            "reachable": {
                "status": "known",
                "value": "each household harvests only from explored cells and pays travel time",
                "evidence": ["SIM-REACH-001"],
            },
            "identifiable_and_processable": {
                "status": "known",
                "value": f"{skill_holders} active people have modeled direct gathering or fishing knowledge",
                "evidence": ["SIM-KNOWLEDGE-001"],
            },
            "labor_and_energy_cost": {
                "status": "known",
                "value": "travel, care, mobility, tool quality, harvesting, and processing consume modeled hours",
                "evidence": ["SIM-LABOR-001"],
            },
            "transport_and_distribution": {
                "status": "assumption",
                "rationale": "Caregivers deliver to dependants within the same household; inter-household transfer is not assumed.",
                "accepted": True,
                "evidence": ["SIM-TRANSPORT-001"],
            },
            "preservation_duration": {
                "status": "known",
                "value": "species-specific daily spoilage is applied to household stores",
                "evidence": ["SIM-STORE-001"],
            },
            "household_capability_differences": {
                "status": "known",
                "value": f"{len(no_tool_households)} of {len(runtimes)} households ended below the improved-tool threshold",
                "evidence": ["SIM-CAPABILITY-001"],
            },
            "future_reproduction_impact": {
                "status": "known",
                "value": "overharvest above 55 percent of cell capacity reduces plant regeneration condition",
                "evidence": ["SIM-REGEN-001"],
            },
        },
        "initial_available_kcal": round(initial_total_kcal, 3),
        "final_available_kcal": round(final_total_kcal, 3),
        "consumption_kg": {
            key: round(value, 3)
            for key, value in sorted(consumption.items())
        },
        "harvest_details": {
            key: {metric: round(value, 6) for metric, value in values.items()}
            for key, values in sorted(harvest_details.items())
        },
        "unit_contract": {
            "plant_stock": "edible biomass kg",
            "animal_stock": "live biomass kg",
            "harvested_kg": "stock-basis kg removed from the environment",
            "edible_food_kg": "kg entering household food stores after yield and processing success",
        },
        "minimum_daily_household_food_success_rate": round(
            min(metric.food_ratio for metric in metrics), 4
        ),
        "average_daily_household_food_success_rate": round(
            mean(metric.food_ratio for metric in metrics), 4
        ),
    }


def _stable_unit(seed: int, label: str) -> float:
    value = 0
    for char in f"{seed}:{label}":
        value = (value * 131 + ord(char)) % 1_000_000_007
    return value / 1_000_000_007


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int((len(ordered) - 1) * fraction)),
    )
    return ordered[index]


def _longest_streak(values: Any) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
