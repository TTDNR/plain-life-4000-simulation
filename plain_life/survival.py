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
            "resource_consumption_kg": self.resource_consumption_kg,
            "migration_summary": self.migration_summary,
            "final_resource_stock_kg": self.final_resource_stock_kg,
        }


def run_survival_validation(
    initial_world: WorldState,
    population: PopulationState,
    days: int = 365,
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
    camps_after_day_one_selection: set[int] = set()

    for day in range(1, days + 1):
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
        )
        metrics.append(day_metric)

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
        test_kind="fixed_population_demand_pressure_test",
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
    household_order = sorted(
        runtimes,
        key=lambda household_id: (
            (sum(ord(char) for char in household_id) + day * 37) % 997,
            household_id,
        ),
    )

    for household_id in household_order:
        runtime = runtimes[household_id]
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
        time_account["care"] += care_hours
        time_account["potential"] += potential_hours
        migration_hours = min(hours, runtime.migration_travel_debt_hours)
        hours -= migration_hours
        time_account["migration_travel"] += migration_hours
        runtime.migration_travel_debt_hours = max(
            0.0, runtime.migration_travel_debt_hours - migration_hours
        )
        knowledge_hours = min(hours, runtime.knowledge_sharing_hours)
        hours -= knowledge_hours
        time_account["exploration_and_communication"] += knowledge_hours
        runtime.knowledge_sharing_hours = max(
            0.0, runtime.knowledge_sharing_hours - knowledge_hours
        )
        water_hours, delivered_litres, water_method = _fetch_water(
            world,
            runtime,
            litres,
            hours,
            day,
            water_distance_cache,
        )
        time_account["water"] += water_hours
        hours -= water_hours

        if day <= 3:
            task_hours = min(hours * 0.25, 2.0)
            _advance_shelter(world, runtime, task_hours)
            hours -= task_hours
            time_account["shelter"] += task_hours
        if day == 1:
            task_hours = min(hours * 0.15, 1.0)
            _advance_tools(world, runtime, task_hours)
            hours -= task_hours
            time_account["tools"] += task_hours
        if day >= 2:
            task_hours = min(hours * 0.15, 1.0)
            _advance_fire(world, runtime, task_hours, day)
            hours -= task_hours
            time_account["fire"] += task_hours
        if day > 3:
            if runtime.shelter_quality < 0.8:
                task_hours = min(hours * 0.18, 1.2)
                _advance_shelter(world, runtime, task_hours)
                hours -= task_hours
                time_account["shelter"] += task_hours
            maintenance = min(hours, 0.35)
            hours -= maintenance
            time_account["fire_maintenance"] += maintenance

        target_kcal = demand + max(
            0.0,
            demand
            * _storage_target_fraction(day, world.start_day_of_year)
            - _store_kcal(world, runtime),
        )
        acquired, food_hours_used = _harvest_food(
            world,
            runtime,
            hours,
            target_kcal,
            resource_consumption,
            harvest_details,
            daily_harvest_details,
            time_account,
        )
        hours -= food_hours_used
        time_account["unallocated_or_rest"] += max(0.0, hours)
        food_available_before_consumption = _store_kcal(world, runtime)
        consumed = _consume_food(world, runtime, demand)
        _spoil_food(runtime)
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
    )


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
        hours_by_person[person.id] = base * person.mobility

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
    if day == 1:
        escort_trips = math.ceil(dependent_count / 2.0)
        required_hours = (
            max(1, len(mobile_people)) * (_distance_walk_hours(distance_km) + 0.2)
            + escort_trips * _distance_walk_hours(distance_km)
        )
        method = "travel_to_source_and_drink_without_container"
        if required_hours <= available_hours:
            world.water_volume_m3 = max(
                0.0, world.water_volume_m3 - litres_needed / 1000.0
            )
            return required_hours, litres_needed, method
        fraction = available_hours / required_hours if required_hours else 1.0
        delivered = litres_needed * max(0.0, min(1.0, fraction))
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
        direct_capacity = drinkers * 1.8
        required_hours = (
            max(1, len(mobile_people))
            * (_distance_walk_hours(distance_km) + 0.2)
            + math.ceil(dependent_count / 2.0)
            * _distance_walk_hours(distance_km)
        )
        if required_hours <= available_hours:
            delivered = min(litres_needed, direct_capacity)
            world.water_volume_m3 = max(
                0.0, world.water_volume_m3 - delivered / 1000.0
            )
            return required_hours, delivered, "travel_to_source_without_vessel"
        fraction = available_hours / required_hours if required_hours else 1.0
        delivered = min(litres_needed, direct_capacity * fraction)
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
        world.water_volume_m3 = max(
            0.0, world.water_volume_m3 - withdrawn / 1000.0
        )
        return required_hours, litres_needed, "carried_in_expedient_vessels"
    fraction = available_hours / required_hours if required_hours else 1.0
    completed_trips = trips * max(0.0, min(1.0, fraction))
    delivered = min(
        litres_needed, completed_trips * effective_capacity
    )
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
    wood = _nearest_material_kg(world, runtime, "wood", hours * 3.0)
    fiber = _nearest_material_kg(
        world, runtime, "fiber", hours * 0.7
    )
    if wood <= 0.0:
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
) -> tuple[float, float]:
    if hours <= 0.0 or target_kcal <= 0.0:
        return 0.0, 0.0
    acquired = 0.0
    remaining_hours = hours
    for resource_id, cell_index, _, distance_km in runtime.supply_options:
        if remaining_hours <= 0.02 or acquired >= target_kcal:
            break
        spec = world.resource_spec(resource_id)
        if not world.is_available(resource_id):
            continue
        if not _can_harvest_by_member(spec, runtime):
            continue
        if resource_id in world.plant_stock_kg:
            stock = world.plant_stock_kg[resource_id][cell_index]
        else:
            stock = world.animal_stock_kg[resource_id][cell_index]
        if stock <= 0.001:
            continue
        travel_hours = _distance_walk_hours(distance_km)
        effective_hours = remaining_hours - travel_hours
        if effective_hours <= 0.02:
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
        runtime.food_store_kg[resource_id] = (
            runtime.food_store_kg.get(resource_id, 0.0) + edible_kg
        )
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
                "resource_id": resource_id,
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
        remaining -= used_kcal
    return consumed_target


def _spoil_food(runtime: HouseholdRuntime) -> None:
    for resource_id, kg in list(runtime.food_store_kg.items()):
        rate = SPOILAGE_PER_DAY.get(resource_id, 0.05)
        runtime.food_store_kg[resource_id] = kg * (1.0 - rate)
        if runtime.food_store_kg[resource_id] < 0.0001:
            del runtime.food_store_kg[resource_id]


def _store_kcal(world: WorldState, runtime: HouseholdRuntime) -> float:
    return sum(
        kg * float(world.resource_spec(resource_id)["kcal_per_kg"])
        for resource_id, kg in runtime.food_store_kg.items()
    )


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
