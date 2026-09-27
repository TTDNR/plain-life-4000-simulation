"""Adapters between the R1 core and the existing Phase 1 state models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .environment import (
    Cell,
    EnvironmentBaseline,
    WorldState,
    advance_day,
)
from .population import Household, Person, PopulationState
from .core import SimulationCore


def world_to_state(world: WorldState) -> dict[str, Any]:
    return {
        "baseline": world.baseline.raw,
        "seed": world.seed,
        "start_day_of_year": world.start_day_of_year,
        "cells": [asdict(cell) for cell in world.cells],
        "plant_stock_kg": world.plant_stock_kg,
        "plant_capacity_kg": world.plant_capacity_kg,
        "plant_regen_condition": world.plant_regen_condition,
        "material_stock_kg": world.material_stock_kg,
        "material_capacity_kg": world.material_capacity_kg,
        "animal_stock_kg": world.animal_stock_kg,
        "animal_capacity_kg": world.animal_capacity_kg,
        "water_volume_m3": world.water_volume_m3,
        "water_capacity_m3": world.water_capacity_m3,
        "groundwater_volume_m3": world.groundwater_volume_m3,
        "water_quality": world.water_quality,
        "initial_fingerprint": world.initial_fingerprint,
        "resource_ledger": world.resource_ledger,
        "elapsed_days": world.elapsed_days,
        "spill_output_m3": world.spill_output_m3,
    }


def world_from_state(value: dict[str, Any]) -> WorldState:
    return WorldState(
        baseline=EnvironmentBaseline(raw=value["baseline"]),
        seed=int(value["seed"]),
        start_day_of_year=int(value["start_day_of_year"]),
        cells=[Cell(**cell) for cell in value["cells"]],
        plant_stock_kg=value["plant_stock_kg"],
        plant_capacity_kg=value["plant_capacity_kg"],
        plant_regen_condition=value["plant_regen_condition"],
        material_stock_kg=value["material_stock_kg"],
        material_capacity_kg=value["material_capacity_kg"],
        animal_stock_kg=value["animal_stock_kg"],
        animal_capacity_kg=value["animal_capacity_kg"],
        water_volume_m3=float(value["water_volume_m3"]),
        water_capacity_m3=float(value["water_capacity_m3"]),
        groundwater_volume_m3=float(
            value["groundwater_volume_m3"]
        ),
        water_quality=float(value["water_quality"]),
        initial_fingerprint=str(value["initial_fingerprint"]),
        resource_ledger=value["resource_ledger"],
        elapsed_days=int(value["elapsed_days"]),
        spill_output_m3=float(value["spill_output_m3"]),
    )


def population_to_state(population: PopulationState) -> dict[str, Any]:
    return {
        "target_total": population.target_total,
        "seed": population.seed,
        "people": [asdict(person) for person in population.people],
        "households": [
            asdict(household) for household in population.households
        ],
        "kinship_edges": population.kinship_edges,
        "pregnancy_events": population.pregnancy_events,
        "lactation_links": population.lactation_links,
        "fingerprint": population.fingerprint,
    }


def population_from_state(value: dict[str, Any]) -> PopulationState:
    return PopulationState(
        target_total=int(value["target_total"]),
        seed=int(value["seed"]),
        people=[Person(**person) for person in value["people"]],
        households=[
            Household(**household) for household in value["households"]
        ],
        kinship_edges=value["kinship_edges"],
        pregnancy_events=value["pregnancy_events"],
        lactation_links=value["lactation_links"],
        fingerprint=str(value["fingerprint"]),
    )


@dataclass
class WorldClockAdapter:
    """Let the core clock drive the existing daily environment model."""

    world: WorldState
    name: str = "environment_world"

    def bind(self, core: SimulationCore) -> None:
        core.register_advance_callback(self.name, self.advance)
        core.set_module_state(self.name, world_to_state(self.world))

    def advance(
        self,
        core: SimulationCore,
        start_world_seconds: int,
        end_world_seconds: int,
    ) -> None:
        target_elapsed_days = (
            end_world_seconds - core.clock.start_world_seconds
        ) // core.clock.day_seconds
        while self.world.elapsed_days < target_elapsed_days:
            advance_day(self.world)
        core.set_module_state(self.name, world_to_state(self.world))


@dataclass
class PopulationStateAdapter:
    population: PopulationState
    name: str = "body_population"

    def bind(self, core: SimulationCore) -> None:
        core.set_module_state(
            self.name, population_to_state(self.population)
        )

