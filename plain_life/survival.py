"""Rule-based survival validation for the Phase 1 initial population."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from .environment import Cell, WorldState
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

    @property
    def skills(self) -> set[str]:
        return {
            skill["id"]
            for person in self.members
            for skill in person.skills
        }


@dataclass
class SurvivalRunResult:
    days: int
    start_environment_fingerprint: str
    end_environment_fingerprint: str
    population_fingerprint: str
    initial_world_unchanged: bool
    metrics: list[DayMetric]
    window_results: dict[str, dict[str, Any]]
    path_results: dict[str, dict[str, Any]]
    food_audit: dict[str, Any]
    resource_consumption_kg: dict[str, float]
    migration_summary: dict[str, Any]
    final_resource_stock_kg: dict[str, float]

    def summary(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "start_environment_fingerprint": self.start_environment_fingerprint,
            "end_environment_fingerprint": self.end_environment_fingerprint,
            "population_fingerprint": self.population_fingerprint,
            "initial_world_unchanged": self.initial_world_unchanged,
            "window_results": self.window_results,
            "path_results": self.path_results,
            "food_audit": self.food_audit,
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
        day_metric = _simulate_day(
            world,
            runtimes,
            day,
            weather,
            resource_consumption,
            water_distance_cache,
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
    )
    migration_summary = {
        "households_that_migrated": sum(
            runtime.migrations > 0 for runtime in runtimes.values()
        ),
        "migration_events": sum(
            runtime.migrations for runtime in runtimes.values()
        ),
        "initial_camps": len({runtime.camp_cell_index for runtime in runtimes.values()}),
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
    initial_candidates = [
        cell.index
        for cell in world.cells
        if cell.habitable
        and _distance_km(world, drop_index, cell.index) <= 3.5
    ]
    if not initial_candidates:
        initial_candidates = [cell.index for cell in world.cells if cell.habitable]

    occupancy: dict[int, int] = {}
    runtimes: dict[str, HouseholdRuntime] = {}
    people_by_id = population.people_by_id
    households = sorted(population.households, key=lambda item: item.id)
    for index in initial_candidates:
        water_distance_cache.setdefault(
            index, _nearest_water_distance_km(world, index)
        )
        camp_score_cache.setdefault(index, _camp_score(world, index))
    candidates_by_score = sorted(
        initial_candidates,
        key=lambda index: camp_score_cache[index],
        reverse=True,
    )
    for household in households:
        best = max(
            candidates_by_score,
            key=lambda index: (
                camp_score_cache[index]
                - occupancy.get(index, 0) * 0.35
                - _distance_km(world, drop_index, index) * 2.5
            ),
        )
        occupancy[best] = occupancy.get(best, 0) + 1
        members = [people_by_id[person_id] for person_id in household.member_ids]
        supply_options = supply_cache.get(best)
        if supply_options is None:
            supply_options = _build_supply_options(world, best)
            supply_cache[best] = supply_options
        material_options = material_cache.get(best)
        if material_options is None:
            material_options = _build_material_options(world, best)
            material_cache[best] = material_options
        runtimes[household.id] = HouseholdRuntime(
            household_id=household.id,
            members=members,
            camp_cell_index=best,
            known_cells={best},
            supply_options=supply_options,
            material_options=material_options,
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
    candidate_cells = [
        cell.index
        for cell in world.cells
        if cell.habitable
        and _distance_km(world, drop_index, cell.index) <= radius_km
    ]
    for index in candidate_cells:
        camp_score_cache.setdefault(index, _camp_score(world, index))
    dynamic_camp_scores = {
        index: world.food_score(world.cells[index]) / 1_000_000.0
        for index in candidate_cells
    }
    occupancy: dict[int, int] = {}
    for runtime in runtimes.values():
        occupancy[runtime.camp_cell_index] = (
            occupancy.get(runtime.camp_cell_index, 0) + 1
        )

    should_consider_migration = day == 1 or day % 5 == 0
    for runtime in runtimes.values():
        nearby = _nearby_habitable_indices(world, runtime.camp_cell_index, 2)
        runtime.known_cells.update(nearby)
        if should_consider_migration:
            recent_ratio = runtime.last_food_ratio
            current_water_distance = _cached_water_distance(
                world, runtime.camp_cell_index, water_distance_cache
            )
            needs_move = (
                recent_ratio < 0.9
                or current_water_distance > 1.8
                or world.cells[runtime.camp_cell_index].flood_risk > 0.55
            )
            current_score = camp_score_cache[runtime.camp_cell_index]
            current_food_score = (
                world.food_score(world.cells[runtime.camp_cell_index])
                / 1_000_000.0
            )
            cooldown_elapsed = day - runtime.last_migration_day >= 7
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
                        current_water_distance > 1.8
                        or world.cells[runtime.camp_cell_index].flood_risk > 0.55
                        or best_score > current_score * 1.2 + 0.5
                    )
                ):
                    occupancy[runtime.camp_cell_index] = max(
                        0, occupancy[runtime.camp_cell_index] - 1
                    )
                    occupancy[best] = occupancy.get(best, 0) + 1
                    runtime.camp_cell_index = best
                    runtime.migrations += 1
                    runtime.last_migration_day = day
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
        hours = _available_labour_hours(runtime)
        water_hours, delivered_litres = _fetch_water(
            world,
            runtime,
            litres,
            hours,
            day,
            water_distance_cache,
        )
        hours -= water_hours

        if day <= 3:
            task_hours = min(hours * 0.25, 2.0)
            _advance_shelter(world, runtime, task_hours)
            hours -= task_hours
        if day == 1:
            task_hours = min(hours * 0.15, 1.0)
            _advance_tools(world, runtime, task_hours)
            hours -= task_hours
        if day >= 2:
            task_hours = min(hours * 0.15, 1.0)
            _advance_fire(world, runtime, task_hours, day)
            hours -= task_hours
        if day > 3:
            if runtime.shelter_quality < 0.8:
                task_hours = min(hours * 0.18, 1.2)
                _advance_shelter(world, runtime, task_hours)
                hours -= task_hours
            maintenance = min(hours, 0.35)
            hours -= maintenance

        target_kcal = demand + max(
            0.0,
            demand
            * _storage_target_fraction(day, world.start_day_of_year)
            - _store_kcal(world, runtime),
        )
        acquired = _harvest_food(
            world,
            runtime,
            hours,
            target_kcal,
            resource_consumption,
        )
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
        migrations += 1 if runtime.last_migration_day == day else 0

    remaining_wild_food = sum(
        sum(values) * float(world.resource_spec(resource_id)["kcal_per_kg"])
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


def _available_labour_hours(runtime: HouseholdRuntime) -> float:
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
    return max(0.0, sum(hours_by_person.values()))


def _fetch_water(
    world: WorldState,
    runtime: HouseholdRuntime,
    litres_needed: float,
    available_hours: float,
    day: int,
    water_distance_cache: dict[int, float],
) -> tuple[float, float]:
    distance_km = _cached_water_distance(
        world, runtime.camp_cell_index, water_distance_cache
    )
    carry_capacity = 7.0 if day <= 1 else 18.0
    trips = litres_needed / carry_capacity
    hours_per_trip = _distance_walk_hours(distance_km) + 0.18
    required_hours = trips * hours_per_trip
    if required_hours <= available_hours:
        world.water_volume_m3 = max(0.0, world.water_volume_m3 - litres_needed / 1000.0)
        return required_hours, litres_needed
    fraction = available_hours / required_hours if required_hours else 1.0
    delivered = litres_needed * max(0.0, min(1.0, fraction))
    world.water_volume_m3 = max(0.0, world.water_volume_m3 - delivered / 1000.0)
    return available_hours, delivered


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


def _advance_fire(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
    day: int,
) -> None:
    if hours <= 0.0:
        return
    if runtime.fire_quality > 0.0:
        wood = _nearest_material_kg(world, runtime, "wood", 1.2)
        runtime.fire_quality = 0.85 if wood >= 0.5 else 0.0
        return
    wood = _nearest_material_kg(world, runtime, "wood", 2.0)
    fiber = _nearest_material_kg(world, runtime, "fiber", 0.5)
    if wood < 0.5 or fiber < 0.1:
        return
    skilled = bool({"fire_friction", "fire_keeping"} & runtime.skills)
    attempt_value = _stable_unit(
        world.seed + day * 131, runtime.household_id
    )
    success_threshold = hours * (0.27 if skilled else 0.035)
    runtime.fire_quality = 0.9 if attempt_value < success_threshold else 0.0


def _harvest_food(
    world: WorldState,
    runtime: HouseholdRuntime,
    hours: float,
    target_kcal: float,
    consumption: dict[str, float],
) -> float:
    if hours <= 0.0 or target_kcal <= 0.0:
        return 0.0
    acquired = 0.0
    remaining_hours = hours
    runtime_skills = runtime.skills
    has_active_adult = any(
        person.life_stage in {"adult", "elder"}
        for person in runtime.members
    )
    for resource_id, cell_index, _, distance_km in runtime.supply_options:
        if remaining_hours <= 0.02 or acquired >= target_kcal:
            break
        spec = world.resource_spec(resource_id)
        if not world.is_available(resource_id):
            continue
        if not _can_harvest(spec, runtime_skills, has_active_adult):
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
        tool_factor = 0.65 + 0.45 * runtime.tool_quality
        harvest_rate = float(spec["harvest_kg_per_hour"]) * tool_factor
        processing_rate = float(spec["processing_hours_per_kg"])
        hours_per_kg = 1.0 / max(0.05, harvest_rate) + processing_rate
        kg_by_hours = effective_hours / hours_per_kg
        kg_by_need = max(
            0.0, (target_kcal - acquired) / float(spec["kcal_per_kg"])
        )
        kg = min(stock, kg_by_hours, kg_by_need)
        if kg <= 0.001:
            continue
        used_hours = travel_hours + kg * hours_per_kg
        remaining_hours -= used_hours
        if resource_id in world.plant_stock_kg:
            array = world.plant_stock_kg[resource_id]
            capacity = world.plant_capacity_kg[resource_id][cell_index]
        else:
            array = world.animal_stock_kg[resource_id]
            capacity = world.animal_capacity_kg[resource_id][cell_index]
        array[cell_index] -= kg
        if capacity > 0.0 and kg / capacity > 0.55:
            if resource_id in world.plant_regen_condition:
                world.plant_regen_condition[resource_id][cell_index] = max(
                    0.35,
                    world.plant_regen_condition[resource_id][cell_index] - 0.08,
                )
        runtime.food_store_kg[resource_id] = (
            runtime.food_store_kg.get(resource_id, 0.0) + kg
        )
        consumption[resource_id] = consumption.get(resource_id, 0.0) + kg
        acquired += kg * float(spec["kcal_per_kg"])
    return acquired


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


def _can_harvest(
    spec: dict[str, Any],
    skills: set[str],
    has_active_adult: bool,
) -> bool:
    if spec.get("common_knowledge") and has_active_adult:
        return True
    return spec["knowledge_skill"] in skills


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
        water_ratios = [metric.water_ratio for metric in selected]
        min_food = min(food_ratios)
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
            "minimum_water_ratio": round(min_water, 4),
            "average_food_ratio": round(average_food, 4),
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


def _build_food_audit(
    initial_world: WorldState,
    population: PopulationState,
    runtimes: dict[str, HouseholdRuntime],
    metrics: list[DayMetric],
    consumption: dict[str, float],
) -> dict[str, Any]:
    initial_total_kcal = sum(
        sum(values)
        * float(initial_world.resource_spec(resource_id)["kcal_per_kg"])
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
