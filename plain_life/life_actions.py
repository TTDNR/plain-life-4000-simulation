"""S01 production and body actions built on the unified core."""

from __future__ import annotations

import math
from typing import Any

from .contracts import (
    ActionIntent,
    ActionRecord,
    ActionValidation,
    Location,
)
from .core import BaseActionHandler, SimulationCore


WALKING_SPEED_M_PER_SECOND = 1.25
DRINK_THIRST_RELIEF_PER_LITRE = 0.35


def distance_m(first: Location, second: Location) -> float:
    return math.hypot(first.x_m - second.x_m, first.y_m - second.y_m)


def move_duration_seconds(
    origin: Location,
    target: Location,
    *,
    speed_m_per_second: float = WALKING_SPEED_M_PER_SECOND,
) -> int:
    if speed_m_per_second <= 0.0:
        raise ValueError("speed must be positive")
    return max(1, int(math.ceil(distance_m(origin, target) / speed_m_per_second)))


class MoveToLocationHandler(BaseActionHandler):
    """Move one person to a target location over real world time."""

    action_type = "move_to_location"

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        target = Location.from_dict(intent.target.get("location"))
        if target is None:
            return ActionValidation(False, "target_location_missing")
        person = core.people[intent.person_id]
        actual_distance = distance_m(person.location, target)
        if actual_distance <= 0.001:
            return ActionValidation(False, "already_at_target_location")
        expected_duration = move_duration_seconds(person.location, target)
        if intent.expected_duration_seconds != expected_duration:
            return ActionValidation(
                False,
                "move_duration_does_not_match_distance",
                {
                    "distance_m": actual_distance,
                    "expected_duration_seconds": expected_duration,
                    "provided_duration_seconds": (
                        intent.expected_duration_seconds
                    ),
                },
            )
        return ActionValidation(
            True,
            "allowed",
            {
                "distance_m": actual_distance,
                "expected_duration_seconds": expected_duration,
            },
        )

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        person = core.people[action.person_id]
        target = Location.from_dict(action.target["location"])
        action.handler_state = {
            "origin": person.location.to_dict(),
            "target": target.to_dict() if target is not None else None,
            "distance_m": distance_m(person.location, target),
        }

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        target = Location.from_dict(action.target["location"])
        if target is None:
            raise RuntimeError("move target disappeared")
        result = core.set_person_location(
            person_id=action.person_id,
            location=target,
            action_id=action.action_id,
            reason="move_completed",
        )
        return {
            **result,
            "distance_m": action.handler_state.get("distance_m"),
        }

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        origin = Location.from_dict(action.handler_state.get("origin"))
        target = Location.from_dict(action.handler_state.get("target"))
        if origin is None or target is None:
            return {"reason": reason, "moved_fraction": 0.0}
        fraction = min(
            1.0,
            max(
                0.0,
                action.progress_seconds
                / max(1, action.expected_duration_seconds),
            ),
        )
        partial = Location(
            x_m=origin.x_m + (target.x_m - origin.x_m) * fraction,
            y_m=origin.y_m + (target.y_m - origin.y_m) * fraction,
            cell_index=(
                target.cell_index if fraction >= 1.0 else origin.cell_index
            ),
        )
        result = core.set_person_location(
            person_id=action.person_id,
            location=partial,
            action_id=action.action_id,
            reason="move_interrupted",
        )
        return {
            "reason": reason,
            "moved_fraction": fraction,
            **result,
        }


class DrinkAtWaterHandler(BaseActionHandler):
    """Drink at an actual water location and persist both water and body use."""

    action_type = "drink_at_water"

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        target = Location.from_dict(intent.target.get("water_location"))
        if target is None:
            return ActionValidation(False, "water_location_missing")
        litres = float(intent.target.get("litres", 0.0))
        if litres <= 0.0:
            return ActionValidation(False, "drink_volume_not_positive")
        person = core.people[intent.person_id]
        tolerance = float(
            intent.target.get("distance_tolerance_m", 5.0)
        )
        actual_distance = distance_m(person.location, target)
        if actual_distance > tolerance:
            return ActionValidation(
                False,
                "person_not_at_water_location",
                {
                    "distance_m": actual_distance,
                    "tolerance_m": tolerance,
                },
            )
        module_name = str(
            intent.target.get("water_module", "environment_world")
        )
        module_state = core.module_states.get(module_name)
        if module_state is not None:
            available_m3 = float(module_state.get("water_volume_m3", 0.0))
            required_m3 = litres / 1000.0
            if available_m3 < required_m3:
                return ActionValidation(
                    False,
                    "insufficient_water_stock",
                    {
                        "available_m3": available_m3,
                        "required_m3": required_m3,
                    },
                )
        return ActionValidation(
            True,
            "allowed",
            {"distance_m": actual_distance, "litres": litres},
        )

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        person = core.people[action.person_id]
        module_name = str(
            action.target.get("water_module", "environment_world")
        )
        module_state = core.module_states.get(module_name)
        action.handler_state = {
            "thirst_before": float(person.body.get("thirst", 0.0)),
            "water_volume_before_m3": (
                float(module_state.get("water_volume_m3", 0.0))
                if module_state is not None
                else None
            ),
            "water_module": module_name,
        }

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        litres = float(action.target["litres"])
        module_name = str(action.handler_state["water_module"])
        module_state = core.module_states.get(module_name)
        water_volume_before = None
        water_volume_after = None
        if module_state is not None:
            copied_state = core.module_state(module_name)
            water_volume_before = float(
                copied_state.get("water_volume_m3", 0.0)
            )
            water_volume_after = max(
                0.0, water_volume_before - litres / 1000.0
            )
            copied_state["water_volume_m3"] = water_volume_after
            core.set_module_state(module_name, copied_state)
        body_result = core.apply_body_delta(
            person_id=action.person_id,
            delta={
                "thirst": -litres * DRINK_THIRST_RELIEF_PER_LITRE,
                "water_intake_litres": litres,
            },
            action_id=action.action_id,
            reason="drink_at_water",
        )
        return {
            "litres": litres,
            "water_volume_before_m3": water_volume_before,
            "water_volume_after_m3": water_volume_after,
            "body_event_id": body_result["event_id"],
            "thirst_before": body_result["before"].get("thirst"),
            "thirst_after": body_result["after"].get("thirst"),
        }

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "reason": reason,
            "litres_consumed": 0.0,
            "body_changed": False,
        }

