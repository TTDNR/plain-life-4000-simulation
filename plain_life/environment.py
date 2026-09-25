"""Deterministic 50 square kilometer environment generation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import deque
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any


LAND_CLASSES = (
    "water",
    "wetland",
    "floodplain",
    "meadow",
    "forest_edge",
    "woodland",
    "upland",
)


@dataclass(frozen=True)
class EnvironmentBaseline:
    raw: dict[str, Any]

    @cached_property
    def width(self) -> int:
        return int(self.raw["grid"]["width_cells"])

    @cached_property
    def height(self) -> int:
        return int(self.raw["grid"]["height_cells"])

    @cached_property
    def cell_size_m(self) -> float:
        return float(self.raw["grid"]["cell_size_m"])

    @cached_property
    def cell_area_m2(self) -> float:
        return self.cell_size_m * self.cell_size_m

    @cached_property
    def resource_specs(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.raw["resources"]}

    @cached_property
    def material_specs(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.raw["materials"]}


@dataclass
class Cell:
    index: int
    x: int
    y: int
    elevation_m: float
    slope_percent: float
    land_class: str
    flood_risk: float
    fertility: float
    drainage: float
    distance_to_water_km: float
    water_depth_m: float

    @property
    def habitable(self) -> bool:
        return (
            self.land_class not in {"water", "wetland"}
            and self.slope_percent <= 8.0
            and self.flood_risk <= 0.5
        )

    @property
    def cultivable(self) -> bool:
        return (
            self.land_class not in {"water", "wetland", "upland"}
            and self.slope_percent <= 3.0
            and self.fertility >= 0.55
            and self.drainage >= 0.4
            and self.flood_risk < 0.65
        )


@dataclass
class WorldState:
    baseline: EnvironmentBaseline
    seed: int
    start_day_of_year: int
    cells: list[Cell]
    plant_stock_kg: dict[str, list[float]]
    plant_capacity_kg: dict[str, list[float]]
    plant_regen_condition: dict[str, list[float]]
    material_stock_kg: dict[str, list[float]]
    material_capacity_kg: dict[str, list[float]]
    animal_stock_kg: dict[str, list[float]]
    animal_capacity_kg: dict[str, list[float]]
    water_volume_m3: float
    water_capacity_m3: float
    groundwater_volume_m3: float
    water_quality: float
    initial_fingerprint: str
    resource_ledger: dict[str, dict[str, float]]
    elapsed_days: int = 0
    spill_output_m3: float = 0.0

    @property
    def width(self) -> int:
        return self.baseline.width

    @property
    def height(self) -> int:
        return self.baseline.height

    @property
    def cell_size_m(self) -> float:
        return self.baseline.cell_size_m

    @property
    def cell_area_m2(self) -> float:
        return self.baseline.cell_area_m2

    @property
    def cells_by_index(self) -> list[Cell]:
        return self.cells

    @cached_property
    def water_cells(self) -> list[Cell]:
        return [cell for cell in self.cells if cell.land_class == "water"]

    @property
    def day_of_year(self) -> int:
        return ((self.start_day_of_year - 1 + self.elapsed_days) % 365) + 1

    @cached_property
    def drop_point(self) -> Cell:
        return min(self.cells, key=lambda cell: _drop_point_score(self, cell))

    def clone(self) -> WorldState:
        return copy.deepcopy(self)

    def resource_spec(self, resource_id: str) -> dict[str, Any]:
        return self.baseline.resource_specs[resource_id]

    def material_spec(self, material_id: str) -> dict[str, Any]:
        return self.baseline.material_specs[material_id]

    def is_available(self, resource_id: str, day_of_year: int | None = None) -> bool:
        day = self.day_of_year if day_of_year is None else day_of_year
        start, end = self.resource_spec(resource_id)["availability_day_range"]
        return int(start) <= day <= int(end)

    def food_score(self, cell: Cell, day_of_year: int | None = None) -> float:
        day = self.day_of_year if day_of_year is None else day_of_year
        score = 0.0
        for resource_id in self.plant_stock_kg:
            if not self.is_available(resource_id, day):
                continue
            spec = self.resource_spec(resource_id)
            kg = self.plant_stock_kg[resource_id][cell.index]
            score += kg * float(spec["kcal_per_kg"])
        for resource_id in self.animal_stock_kg:
            if not self.is_available(resource_id, day):
                continue
            spec = self.resource_spec(resource_id)
            kg = self.animal_stock_kg[resource_id][cell.index]
            score += kg * float(spec["kcal_per_kg"]) * 0.15
        return score

    def fingerprint(self) -> str:
        payload = {
            "world_id": self.baseline.raw["world_id"],
            "seed": self.seed,
            "start_day_of_year": self.start_day_of_year,
            "cells": [
                [
                    round(cell.elevation_m, 5),
                    round(cell.slope_percent, 5),
                    cell.land_class,
                    round(cell.flood_risk, 5),
                    round(cell.fertility, 5),
                    round(cell.drainage, 5),
                ]
                for cell in self.cells
            ],
            "plants": {
                resource_id: [round(value, 5) for value in values]
                for resource_id, values in sorted(self.plant_stock_kg.items())
            },
            "animals": {
                resource_id: [round(value, 5) for value in values]
                for resource_id, values in sorted(self.animal_stock_kg.items())
            },
            "materials": {
                material_id: [round(value, 5) for value in values]
                for material_id, values in sorted(self.material_stock_kg.items())
            },
            "water": [
                round(self.water_volume_m3, 5),
                round(self.water_capacity_m3, 5),
                round(self.groundwater_volume_m3, 5),
                round(self.water_quality, 5),
            ],
            "ledger": {
                resource_id: {
                    key: round(value, 5)
                    for key, value in ledger.items()
                }
                for resource_id, ledger in sorted(
                    self.resource_ledger.items()
                )
            },
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def load_environment_baseline(path: Path) -> EnvironmentBaseline:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return EnvironmentBaseline(raw)


def generate_environment(baseline: EnvironmentBaseline) -> WorldState:
    width = baseline.width
    height = baseline.height
    seed = int(baseline.raw["seed"])
    rng = random.Random(seed)

    noise = _smooth_field(rng, width, height, 13, 7, passes=2)
    detail = _smooth_field(rng, width, height, 31, 16, passes=1)
    elevations: list[float] = []
    for y in range(height):
        for x in range(width):
            central_bowl = 14.0 * math.exp(
                -(((x - 50.0) / 16.0) ** 2 + ((y - 25.0) / 7.0) ** 2)
            )
            river_path = 25.0 + 3.4 * math.sin((x - 12.0) / 10.0)
            river_bowl = 4.0 * math.exp(-((y - river_path) / 2.6) ** 2)
            value = (
                48.0
                + 20.0 * noise[y][x]
                + 4.0 * detail[y][x]
                - central_bowl
                - river_bowl
            )
            elevations.append(value)

    water_level = _percentile(elevations, 0.065) + 0.25
    provisional_classes = [
        (
            "water"
            if elevation <= water_level
            else "wetland"
            if elevation <= water_level + 1.3
            else "unclassified"
        )
        for elevation in elevations
    ]
    distance_to_water = _distance_to_mask(
        provisional_classes, width, height
    )

    cells: list[Cell] = []
    for index, elevation in enumerate(elevations):
        x = index % width
        y = index // width
        if provisional_classes[index] == "water":
            land_class = "water"
        elif provisional_classes[index] == "wetland" or distance_to_water[index] <= 1:
            land_class = "wetland"
        elif elevation >= 67.0:
            land_class = "upland"
        elif distance_to_water[index] <= 3.5:
            land_class = "floodplain"
        elif noise[y][x] >= 0.61:
            land_class = "woodland"
        elif noise[y][x] >= 0.52:
            land_class = "forest_edge"
        else:
            land_class = "meadow"

        distance_km = distance_to_water[index] * baseline.cell_size_m / 1000.0
        flood_risk = 0.0
        if land_class == "water":
            flood_risk = 1.0
        elif land_class == "wetland":
            flood_risk = 0.72
        elif distance_km <= 0.45:
            flood_risk = max(0.0, 0.9 - distance_km)
        fertility = float(
            baseline.raw["land"]["baseline_fertility_by_land_class"][land_class]
        )
        fertility *= 0.9 + 0.2 * noise[y][x]
        drainage = {
            "water": 1.0,
            "wetland": 0.18,
            "floodplain": 0.42,
            "meadow": 0.68,
            "forest_edge": 0.66,
            "woodland": 0.61,
            "upland": 0.86,
        }[land_class]
        drainage *= 0.9 + 0.2 * detail[y][x]
        depth = (
            max(0.35, water_level - elevation + 0.65)
            if land_class == "water"
            else 0.08
            if land_class == "wetland"
            else 0.0
        )
        cells.append(
            Cell(
                index=index,
                x=x,
                y=y,
                elevation_m=elevation,
                slope_percent=_slope_at(elevations, width, height, x, y),
                land_class=land_class,
                flood_risk=min(1.0, flood_risk),
                fertility=min(1.0, max(0.0, fertility)),
                drainage=min(1.0, max(0.0, drainage)),
                distance_to_water_km=distance_km,
                water_depth_m=depth,
            )
        )

    plant_stock: dict[str, list[float]] = {}
    plant_capacity: dict[str, list[float]] = {}
    plant_condition: dict[str, list[float]] = {}
    animal_stock: dict[str, list[float]] = {}
    animal_capacity: dict[str, list[float]] = {}
    start_day = int(baseline.raw["start_day_of_year"])
    for resource_id, spec in baseline.resource_specs.items():
        capacities = [0.0] * len(cells)
        stocks = [0.0] * len(cells)
        for cell in cells:
            if cell.land_class not in spec["habitats"]:
                continue
            local_noise = _cell_noise(seed, resource_id, cell.index)
            capacity = float(spec["base_capacity_kg_ha"]) * (
                0.65 + 0.7 * local_noise
            )
            capacities[cell.index] = capacity
            stocks[cell.index] = capacity * _maturity_fraction(
                start_day, spec["availability_day_range"]
            )
        if spec["kind"] == "plant":
            plant_capacity[resource_id] = capacities
            plant_stock[resource_id] = stocks
            plant_condition[resource_id] = [1.0] * len(cells)
        else:
            animal_capacity[resource_id] = capacities
            animal_stock[resource_id] = stocks

    material_stock: dict[str, list[float]] = {}
    material_capacity: dict[str, list[float]] = {}
    for material_id, spec in baseline.material_specs.items():
        capacities = [0.0] * len(cells)
        stocks = [0.0] * len(cells)
        for cell in cells:
            if cell.land_class not in spec["habitats"]:
                continue
            local_noise = _cell_noise(seed, material_id, cell.index)
            capacity = float(spec["base_capacity_kg_ha"]) * (
                0.6 + 0.8 * local_noise
            )
            capacities[cell.index] = capacity
            stocks[cell.index] = capacity * (0.75 + 0.25 * local_noise)
        material_capacity[material_id] = capacities
        material_stock[material_id] = stocks

    water_cells = [cell for cell in cells if cell.land_class == "water"]
    water_capacity = (
        sum(cell.water_depth_m for cell in water_cells) * baseline.cell_area_m2
    )
    water_volume = water_capacity * 0.78
    state = WorldState(
        baseline=baseline,
        seed=seed,
        start_day_of_year=start_day,
        cells=cells,
        plant_stock_kg=plant_stock,
        plant_capacity_kg=plant_capacity,
        plant_regen_condition=plant_condition,
        material_stock_kg=material_stock,
        material_capacity_kg=material_capacity,
        animal_stock_kg=animal_stock,
        animal_capacity_kg=animal_capacity,
        water_volume_m3=water_volume,
        water_capacity_m3=water_capacity,
        groundwater_volume_m3=float(
            baseline.raw["hydrology"]["base_groundwater_storage_m3"]
        ),
        water_quality=float(
            baseline.raw["hydrology"]["base_water_quality"]
        ),
        initial_fingerprint="",
        resource_ledger={
            resource_id: {
                "opening_stock_kg": round(sum(stock), 6),
                "additions_kg": 0.0,
                "harvested_kg": 0.0,
                "natural_loss_kg": 0.0,
                "internal_transfer_kg": 0.0,
            }
            for resource_id, stock in {
                **plant_stock,
                **animal_stock,
                **material_stock,
            }.items()
        },
    )
    state.initial_fingerprint = state.fingerprint()
    return state


def advance_day(state: WorldState) -> dict[str, float]:
    state.elapsed_days += 1
    day = state.day_of_year
    weather = weather_for_day(state, day)
    hydrology = state.baseline.raw["hydrology"]
    lake_area_m2 = len(state.water_cells) * state.cell_area_m2
    runoff_area_m2 = 0.36 * len(state.cells) * state.cell_area_m2
    rainfall_input_m3 = (
        weather["rainfall_mm"]
        / 1000.0
        * runoff_area_m2
        * float(hydrology["runoff_coefficient"])
    )
    evaporation_output_m3 = (
        weather["evaporation_mm"] / 1000.0 * lake_area_m2
    )
    recharge_m3 = rainfall_input_m3 * float(
        hydrology["groundwater_recharge_fraction"]
    )
    state.groundwater_volume_m3 += recharge_m3 * 0.04
    state.water_volume_m3 += rainfall_input_m3 - evaporation_output_m3 - recharge_m3
    if state.water_volume_m3 > state.water_capacity_m3:
        overflow = state.water_volume_m3 - state.water_capacity_m3
        state.spill_output_m3 += overflow
        state.water_volume_m3 = state.water_capacity_m3
    state.water_volume_m3 = max(0.0, state.water_volume_m3)
    state.water_quality = max(
        float(hydrology["human_contamination_dilution_limit"]),
        min(1.0, state.water_quality + 0.0002),
    )

    for resource_id, spec in state.baseline.resource_specs.items():
        if spec["kind"] == "plant":
            capacity = state.plant_capacity_kg[resource_id]
            stock = state.plant_stock_kg[resource_id]
            condition = state.plant_regen_condition[resource_id]
            season_start, season_end = spec["availability_day_range"]
            previous_day = ((day - 2) % 365) + 1
            if previous_day == int(season_end) and day != int(season_end):
                natural_loss_fraction = float(
                    spec.get("season_end_natural_loss_fraction", 0.0)
                )
                if natural_loss_fraction > 0.0:
                    for index in range(len(stock)):
                        lost = stock[index] * natural_loss_fraction
                        stock[index] -= lost
                        state.resource_ledger[resource_id][
                            "natural_loss_kg"
                        ] += lost
            annual_fraction = float(spec["annual_recovery_fraction"])
            if day == int(season_start):
                for index, cap in enumerate(capacity):
                    before = stock[index]
                    stock[index] = min(
                        cap,
                        before + cap * annual_fraction * condition[index],
                    )
                    state.resource_ledger[resource_id][
                        "additions_kg"
                    ] += max(0.0, stock[index] - before)
            outside = not (int(season_start) <= day <= int(season_end))
            if outside:
                daily_growth = annual_fraction / 365.0 * 0.35
                for index, cap in enumerate(capacity):
                    before = stock[index]
                    stock[index] = min(
                        cap,
                        before + cap * daily_growth * condition[index],
                    )
                    state.resource_ledger[resource_id][
                        "additions_kg"
                    ] += max(0.0, stock[index] - before)
            for index in range(len(condition)):
                condition[index] = min(1.0, condition[index] + 0.0015)
        else:
            capacity = state.animal_capacity_kg[resource_id]
            stock = state.animal_stock_kg[resource_id]
            growth = float(spec["daily_growth_rate"])
            for index, cap in enumerate(capacity):
                if cap <= 0.0:
                    continue
                current = max(0.0, stock[index])
                stock[index] = min(
                    cap, current + growth * current * (1.0 - current / cap)
                )
                state.resource_ledger[resource_id]["additions_kg"] += max(
                    0.0, stock[index] - current
                )

    if day == 1:
        for material_id, spec in state.baseline.material_specs.items():
            capacity = state.material_capacity_kg[material_id]
            stock = state.material_stock_kg[material_id]
            renewal = float(spec["renewal_fraction_per_year"])
            for index, cap in enumerate(capacity):
                before = stock[index]
                stock[index] = min(cap, before + cap * renewal)
                state.resource_ledger[material_id]["additions_kg"] += max(
                    0.0, stock[index] - before
                )
    return weather


def record_resource_harvest(
    state: WorldState,
    resource_id: str,
    stock_kg: float,
) -> None:
    if stock_kg < 0.0:
        raise ValueError("resource harvest cannot be negative")
    state.resource_ledger[resource_id]["harvested_kg"] += stock_kg


def record_material_harvest(
    state: WorldState,
    material_id: str,
    stock_kg: float,
) -> None:
    if stock_kg < 0.0:
        raise ValueError("material harvest cannot be negative")
    state.resource_ledger[material_id]["harvested_kg"] += stock_kg


def resource_ledger_snapshot(state: WorldState) -> dict[str, dict[str, float]]:
    snapshot: dict[str, dict[str, float]] = {}
    for resource_id, ledger in state.resource_ledger.items():
        stock = (
            state.plant_stock_kg[resource_id]
            if resource_id in state.plant_stock_kg
            else state.animal_stock_kg[resource_id]
            if resource_id in state.animal_stock_kg
            else state.material_stock_kg[resource_id]
        )
        closing = sum(stock)
        closure_error = (
            ledger["opening_stock_kg"]
            + ledger["additions_kg"]
            - ledger["harvested_kg"]
            - ledger["natural_loss_kg"]
            - ledger["internal_transfer_kg"]
            - closing
        )
        spec = (
            state.resource_spec(resource_id)
            if resource_id in state.baseline.resource_specs
            else state.material_spec(resource_id)
        )
        snapshot[resource_id] = {
            "opening_stock_kg": round(ledger["opening_stock_kg"], 6),
            "additions_kg": round(ledger["additions_kg"], 6),
            "harvested_kg": round(ledger["harvested_kg"], 6),
            "natural_loss_kg": round(ledger["natural_loss_kg"], 6),
            "internal_transfer_kg": round(
                ledger["internal_transfer_kg"], 6
            ),
            "closing_stock_kg": round(closing, 6),
            "closure_error_kg": round(closure_error, 6),
            "non_negative": all(value >= 0.0 for value in stock),
            "stock_basis": spec.get(
                "stock_basis", "legacy_unspecified_kg"
            ),
            "edible_yield_fraction": spec.get(
                "edible_yield_fraction", 1.0
            ),
        }
    return snapshot


def weather_for_day(state: WorldState, day_of_year: int) -> dict[str, float]:
    month = min(11, max(0, (int(day_of_year) - 1) // 30))
    climate = state.baseline.raw["climate"]
    local_rng = random.Random(state.seed * 100_000 + int(day_of_year))
    rainy_fraction = float(climate["rainy_day_fraction"][month])
    is_rainy = local_rng.random() < rainy_fraction
    if is_rainy:
        factor = 0.25 + 1.75 * local_rng.random()
        rainfall = (
            float(climate["rainfall_mm"][month])
            / 30.0
            / rainy_fraction
            * factor
        )
    else:
        rainfall = 0.0
    evaporation = float(climate["evaporation_mm"][month]) / 30.0 * (
        0.8 + 0.4 * local_rng.random()
    )
    temperature = (
        float(climate["temperature_c"][month])
        + 4.0 * math.sin(2.0 * math.pi * day_of_year / 365.0)
        - (2.5 if is_rainy else 0.0)
    )
    return {
        "rainfall_mm": round(rainfall, 4),
        "evaporation_mm": round(evaporation, 4),
        "temperature_c": round(temperature, 4),
    }


def environment_summary(state: WorldState) -> dict[str, Any]:
    ledger_snapshot = resource_ledger_snapshot(state)
    habitat_counts = {
        land_class: sum(cell.land_class == land_class for cell in state.cells)
        for land_class in LAND_CLASSES
    }
    resource_totals = {
        resource_id: {
            "stock_kg_at_start": round(sum(values), 3),
            "capacity_kg": round(
                sum(
                    state.plant_capacity_kg[resource_id]
                    if resource_id in state.plant_capacity_kg
                    else state.animal_capacity_kg[resource_id]
                ),
                3,
            ),
            "cells": sum(value > 0.0 for value in values),
            "kcal_per_kg": float(spec["kcal_per_kg"]),
            "stock_basis": spec.get("stock_basis", "legacy_unspecified_kg"),
            "edible_yield_fraction": float(
                spec.get("edible_yield_fraction", 1.0)
            ),
            "availability_day_range": spec["availability_day_range"],
            "annual_recovery_fraction": float(
                spec["annual_recovery_fraction"]
            ),
            "regeneration_model": spec.get(
                "regeneration_model", spec.get("growth_model")
            ),
            "growth_rate_unit": spec.get("growth_rate_unit"),
            "evidence": spec["evidence"],
            **ledger_snapshot[resource_id],
        }
        for resource_id, spec in state.baseline.resource_specs.items()
        for values in [
            state.plant_stock_kg[resource_id]
            if resource_id in state.plant_stock_kg
            else state.animal_stock_kg[resource_id]
        ]
    }
    material_totals = {
        material_id: {
            "stock_kg_at_start": round(sum(values), 3),
            "capacity_kg": round(
                sum(state.material_capacity_kg[material_id]), 3
            ),
            "cells": sum(value > 0.0 for value in values),
            "renewal_fraction_per_year": float(
                state.baseline.material_specs[material_id][
                    "renewal_fraction_per_year"
                ]
            ),
            "evidence": state.baseline.material_specs[material_id]["evidence"],
            **ledger_snapshot[material_id],
        }
        for material_id, values in state.material_stock_kg.items()
    }
    return {
        "world_id": state.baseline.raw["world_id"],
        "seed": state.seed,
        "fingerprint": state.initial_fingerprint,
        "start_day_of_year": state.start_day_of_year,
        "habitat_counts": habitat_counts,
        "habitable_cells": sum(cell.habitable for cell in state.cells),
        "cultivable_cells": sum(cell.cultivable for cell in state.cells),
        "drop_point": {
            "x": state.drop_point.x,
            "y": state.drop_point.y,
            "elevation_m": round(state.drop_point.elevation_m, 3),
            "distance_to_water_km": round(
                state.drop_point.distance_to_water_km, 3
            ),
        },
        "water": {
            "surface_volume_m3": round(state.water_volume_m3, 3),
            "surface_capacity_m3": round(state.water_capacity_m3, 3),
            "groundwater_m3": round(state.groundwater_volume_m3, 3),
            "quality": round(state.water_quality, 4),
        },
        "resources": resource_totals,
        "resource_ledgers": ledger_snapshot,
        "materials": material_totals,
        "status_provenance": {
            "climate": state.baseline.raw["climate"]["status"],
            "hydrology": state.baseline.raw["hydrology"]["status"],
            "resources": "assumption",
            "materials": "assumption",
            "land": state.baseline.raw["land"]["status"],
        },
    }


def evaluate_boundary_attempt(
    state: WorldState,
    cell_index: int,
    dx: int,
    dy: int,
) -> dict[str, Any]:
    """Return the stable result of one movement attempt across the world edge."""
    if not 0 <= cell_index < len(state.cells):
        raise IndexError("cell_index is outside the world")
    cell = state.cells[cell_index]
    target_x = cell.x + int(dx)
    target_y = cell.y + int(dy)
    inside = 0 <= target_x < state.width and 0 <= target_y < state.height
    if inside:
        target_index = target_y * state.width + target_x
        return {
            "outcome": "moved",
            "rule_id": "closed-edge-v1",
            "from_cell_index": cell_index,
            "to_cell_index": target_index,
            "damage": 0.0,
            "hint": None,
        }
    return {
        "outcome": "blocked",
        "rule_id": "closed-edge-v1",
        "from_cell_index": cell_index,
        "to_cell_index": None,
        "damage": 0.0,
        "hint": None,
    }


def _cell_noise(seed: int, label: str, index: int) -> float:
    digest = hashlib.sha256(f"{seed}:{label}:{index}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _maturity_fraction(day: int, season: list[int]) -> float:
    start, end = int(season[0]), int(season[1])
    if day < start or day > end:
        return 0.0
    progress = (day - start + 1) / max(1, end - start + 1)
    return 0.15 + 0.85 * math.sin(math.pi * min(1.0, progress * 1.25))


def _smooth_field(
    rng: random.Random,
    width: int,
    height: int,
    coarse_width: int,
    coarse_height: int,
    passes: int,
) -> list[list[float]]:
    coarse = [
        [rng.random() for _ in range(coarse_width)]
        for _ in range(coarse_height)
    ]
    field: list[list[float]] = []
    for y in range(height):
        gy = y / max(1, height - 1) * (coarse_height - 1)
        y0 = int(math.floor(gy))
        y1 = min(coarse_height - 1, y0 + 1)
        fy = gy - y0
        row: list[float] = []
        for x in range(width):
            gx = x / max(1, width - 1) * (coarse_width - 1)
            x0 = int(math.floor(gx))
            x1 = min(coarse_width - 1, x0 + 1)
            fx = gx - x0
            top = coarse[y0][x0] * (1.0 - fx) + coarse[y0][x1] * fx
            bottom = coarse[y1][x0] * (1.0 - fx) + coarse[y1][x1] * fx
            row.append(top * (1.0 - fy) + bottom * fy)
        field.append(row)

    for _ in range(passes):
        smoothed = [[0.0] * width for _ in range(height)]
        for y in range(height):
            for x in range(width):
                total = 0.0
                count = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            total += field[ny][nx]
                            count += 1
                smoothed[y][x] = total / count
        field = smoothed
    return field


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction)))
    return ordered[index]


def _distance_to_mask(
    classes: list[str], width: int, height: int
) -> list[float]:
    distances = [float("inf")] * len(classes)
    queue: deque[int] = deque()
    for index, land_class in enumerate(classes):
        if land_class == "water":
            distances[index] = 0.0
            queue.append(index)
    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            neighbor = ny * width + nx
            candidate = distances[index] + 1.0
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                queue.append(neighbor)
    return distances


def _slope_at(
    elevations: list[float],
    width: int,
    height: int,
    x: int,
    y: int,
) -> float:
    center = elevations[y * width + x]
    max_difference = 0.0
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            max_difference = max(
                max_difference,
                abs(center - elevations[ny * width + nx]),
            )
    return max_difference / 1.0


def _drop_point_score(state: WorldState, cell: Cell) -> float:
    if not cell.habitable:
        return 10_000.0 + abs(cell.x - 50) + abs(cell.y - 25)
    water_distance_penalty = abs(cell.distance_to_water_km - 0.45)
    center_penalty = 0.01 * (abs(cell.x - 50) + abs(cell.y - 25))
    slope_penalty = 0.02 * cell.slope_percent
    return water_distance_penalty * 100.0 + center_penalty + slope_penalty
