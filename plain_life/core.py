"""Unified R1 clock, action lifecycle, event log, and persistence core."""

from __future__ import annotations

import copy
import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .contracts import (
    CONTRACT_VERSION,
    ContractVersionError,
    ActionIntent,
    ActionRecord,
    ActionValidation,
    Commitment,
    DecisionTrace,
    Event,
    ItemBatch,
    ItemReservation,
    Location,
    PerceivedState,
    PersonState,
    RunManifest,
    ScheduledEvent,
    SocialResponse,
    WORLD_SECONDS_PER_DAY,
)


CORE_SNAPSHOT_SCHEMA_VERSION = 1


class ModuleBindingError(RuntimeError):
    """Raised when a restored run lacks a required module callback."""


@dataclass
class SimulationClock:
    start_world_seconds: int
    current_world_seconds: int
    day_seconds: int
    initial_day_of_year: int

    @property
    def elapsed_seconds(self) -> int:
        return self.current_world_seconds - self.start_world_seconds

    @property
    def completed_days(self) -> int:
        return max(0, self.elapsed_seconds // self.day_seconds)

    @property
    def day_of_year(self) -> int:
        return (
            (self.initial_day_of_year - 1 + self.completed_days) % 365
        ) + 1

    @property
    def second_of_day(self) -> int:
        return self.current_world_seconds % self.day_seconds

    def to_dict(self) -> dict[str, int]:
        return {
            "start_world_seconds": self.start_world_seconds,
            "current_world_seconds": self.current_world_seconds,
            "day_seconds": self.day_seconds,
            "initial_day_of_year": self.initial_day_of_year,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SimulationClock:
        return cls(
            start_world_seconds=int(value["start_world_seconds"]),
            current_world_seconds=int(value["current_world_seconds"]),
            day_seconds=int(value["day_seconds"]),
            initial_day_of_year=int(value["initial_day_of_year"]),
        )


class ActionHandler(Protocol):
    action_type: str

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        ...

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        ...

    def on_progress(
        self,
        core: SimulationCore,
        action: ActionRecord,
        delta_seconds: int,
    ) -> None:
        ...

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        ...

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        ...


class BaseActionHandler:
    action_type = ""

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        return ActionValidation(True, "allowed")

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        return None

    def on_progress(
        self,
        core: SimulationCore,
        action: ActionRecord,
        delta_seconds: int,
    ) -> None:
        return None

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        return {}

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        return {"reason": reason}


class TransferItemHandler(BaseActionHandler):
    """Move a reserved item batch to another owner on successful completion."""

    action_type = "transfer_item"

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        batch_id = str(intent.target.get("batch_id", ""))
        quantity = float(intent.target.get("quantity", 0.0))
        batch = core.items.get(batch_id)
        if batch is None:
            return ActionValidation(False, "item_batch_not_found")
        if quantity <= 0.0:
            return ActionValidation(False, "transfer_quantity_not_positive")
        if batch.owner_kind != "person" or batch.owner_id != intent.person_id:
            return ActionValidation(False, "item_not_held_by_actor")
        available = core.available_item_quantity(batch_id)
        if quantity - available > 1e-9:
            return ActionValidation(
                False,
                "insufficient_unreserved_item",
                {"requested": quantity, "available": available},
            )
        return ActionValidation(
            True,
            "allowed",
            {"requested": quantity, "available": available},
        )

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        reservation = core.reserve_item(
            batch_id=str(action.target["batch_id"]),
            quantity=float(action.target["quantity"]),
            action_id=action.action_id,
            purpose=self.action_type,
        )
        action.reservations.append(reservation.reservation_id)

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        if not action.reservations:
            raise RuntimeError("transfer action has no reservation")
        target = action.target
        to_owner_kind = str(target.get("to_owner_kind", "person"))
        to_owner_id = str(target["to_owner_id"])
        to_location = Location.from_dict(target.get("to_location"))
        if (
            to_location is None
            and to_owner_kind == "person"
            and to_owner_id in core.people
        ):
            to_location = core.people[to_owner_id].location
        output_batch = core.transfer_reserved_item(
            action.reservations[0],
            to_owner_kind=to_owner_kind,
            to_owner_id=to_owner_id,
            to_location=to_location,
        )
        action.reservations.clear()
        return {
            "output_batch_id": output_batch.batch_id,
            "quantity": output_batch.quantity,
            "unit": output_batch.unit,
            "to_owner_kind": output_batch.owner_kind,
            "to_owner_id": output_batch.owner_id,
        }

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        released: list[str] = []
        for reservation_id in list(action.reservations):
            core.release_reservation(reservation_id)
            released.append(reservation_id)
        action.reservations.clear()
        return {"reason": reason, "released_reservations": released}


class ConsumeItemHandler(BaseActionHandler):
    """Consume a reserved batch only when the action completes."""

    action_type = "consume_item"

    def validate(
        self, core: SimulationCore, intent: ActionIntent
    ) -> ActionValidation:
        batch_id = str(intent.target.get("batch_id", ""))
        quantity = float(intent.target.get("quantity", 0.0))
        batch = core.items.get(batch_id)
        if batch is None:
            return ActionValidation(False, "item_batch_not_found")
        if quantity <= 0.0:
            return ActionValidation(False, "consume_quantity_not_positive")
        if batch.owner_kind != "person" or batch.owner_id != intent.person_id:
            return ActionValidation(False, "item_not_held_by_actor")
        available = core.available_item_quantity(batch_id)
        if quantity - available > 1e-9:
            return ActionValidation(
                False,
                "insufficient_unreserved_item",
                {"requested": quantity, "available": available},
            )
        return ActionValidation(True, "allowed")

    def begin(self, core: SimulationCore, action: ActionRecord) -> None:
        reservation = core.reserve_item(
            batch_id=str(action.target["batch_id"]),
            quantity=float(action.target["quantity"]),
            action_id=action.action_id,
            purpose=self.action_type,
        )
        action.reservations.append(reservation.reservation_id)

    def complete(
        self, core: SimulationCore, action: ActionRecord
    ) -> dict[str, Any]:
        if not action.reservations:
            raise RuntimeError("consume action has no reservation")
        consumed = core.consume_reserved_item(
            action.reservations[0],
            reason=str(action.target.get("reason", "consumed")),
        )
        action.reservations.clear()
        return consumed

    def interrupt(
        self,
        core: SimulationCore,
        action: ActionRecord,
        reason: str,
    ) -> dict[str, Any]:
        released: list[str] = []
        for reservation_id in list(action.reservations):
            core.release_reservation(reservation_id)
            released.append(reservation_id)
        action.reservations.clear()
        return {"reason": reason, "released_reservations": released}


class SimulationCore:
    """Owns world time and commits all externally visible state changes."""

    def __init__(
        self,
        manifest: RunManifest,
        handlers: dict[str, ActionHandler] | None = None,
        *,
        clock: SimulationClock | None = None,
        people: dict[str, PersonState] | None = None,
        items: dict[str, ItemBatch] | None = None,
        reservations: dict[str, ItemReservation] | None = None,
        relationships: dict[str, dict[str, float]] | None = None,
        knowledge: dict[str, list[dict[str, Any]]] | None = None,
        known_locations: dict[str, list[dict[str, Any]]] | None = None,
        stated_claims: dict[str, list[str]] | None = None,
        actions: dict[str, ActionRecord] | None = None,
        events: list[Event] | None = None,
        scheduled_events: list[ScheduledEvent] | None = None,
        decisions: dict[str, DecisionTrace] | None = None,
        social_responses: dict[str, SocialResponse] | None = None,
        commitments: dict[str, Commitment] | None = None,
        module_states: dict[str, dict[str, Any]] | None = None,
        event_sequence: int = 0,
        item_sequence: int = 0,
        reservation_sequence: int = 0,
        scheduled_sequence: int = 0,
        paused: bool = False,
        random_state: Any | None = None,
    ) -> None:
        if manifest.contract_version != CONTRACT_VERSION:
            raise ContractVersionError(
                f"unsupported contract version {manifest.contract_version}"
            )
        self.manifest = manifest
        self.handlers = dict(handlers or {})
        self.clock = clock or SimulationClock(
            start_world_seconds=manifest.start_world_seconds,
            current_world_seconds=manifest.start_world_seconds,
            day_seconds=manifest.day_seconds,
            initial_day_of_year=manifest.initial_day_of_year,
        )
        self.people = dict(people or {})
        self.items = dict(items or {})
        self.reservations = dict(reservations or {})
        self.relationships = dict(relationships or {})
        self.knowledge = dict(knowledge or {})
        self.known_locations = dict(known_locations or {})
        self.stated_claims = dict(stated_claims or {})
        self.actions = dict(actions or {})
        self.events = list(events or [])
        self.scheduled_events = list(scheduled_events or [])
        self.decisions = dict(decisions or {})
        self.social_responses = dict(social_responses or {})
        self.commitments = dict(commitments or {})
        self.module_states = dict(module_states or {})
        self.event_sequence = event_sequence
        self.item_sequence = item_sequence
        self.reservation_sequence = reservation_sequence
        self.scheduled_sequence = scheduled_sequence
        self.paused = paused
        self.random = random.Random(manifest.random_seed)
        if random_state is not None:
            self.random.setstate(_decode_rng_state(random_state))
        self._advance_callbacks: dict[
            str, Callable[[SimulationCore, int, int], None]
        ] = {}
        self._module_requirements: dict[str, dict[str, Any]] = {}

    @classmethod
    def create(
        cls,
        manifest: RunManifest,
        handlers: dict[str, ActionHandler] | None = None,
    ) -> SimulationCore:
        core = cls(manifest=manifest, handlers=handlers)
        core.emit_event(
            event_type="run_created",
            actor_ids=[],
            action_id=None,
            facts={
                "scenario_id": manifest.scenario_id,
                "mode": manifest.mode,
                "contract_version": manifest.contract_version,
            },
        )
        return core

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def advance_by(self, duration_seconds: int) -> None:
        if duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        self.advance_to(self.clock.current_world_seconds + duration_seconds)

    def advance_to(self, target_world_seconds: int) -> None:
        if self.paused:
            raise RuntimeError("simulation is paused")
        if target_world_seconds < self.clock.current_world_seconds:
            raise ValueError("world time cannot move backwards")
        self._process_current_boundary()
        while self.clock.current_world_seconds < target_world_seconds:
            next_time = target_world_seconds
            for scheduled in self.scheduled_events:
                if (
                    self.clock.current_world_seconds
                    < scheduled.due_world_seconds
                    < next_time
                ):
                    next_time = scheduled.due_world_seconds
            for action in self.actions.values():
                if action.status != "active":
                    continue
                if action.expected_end_world_seconds is None:
                    continue
                if (
                    self.clock.current_world_seconds
                    < action.expected_end_world_seconds
                    < next_time
                ):
                    next_time = action.expected_end_world_seconds
            start = self.clock.current_world_seconds
            self.clock.current_world_seconds = next_time
            delta = next_time - start
            for action in list(self.actions.values()):
                if action.status != "active":
                    continue
                action.progress_seconds = min(
                    action.expected_duration_seconds,
                    action.progress_seconds + delta,
                )
                self.handlers[action.action_type].on_progress(
                    self, action, delta
                )
            self._process_current_boundary()
            for callback in list(self._advance_callbacks.values()):
                callback(self, start, next_time)
            self._process_current_boundary()
        self._process_current_boundary()

    def register_advance_callback(
        self,
        name: str,
        callback: Callable[[SimulationCore, int, int], None],
        *,
        required_for_advance: bool = True,
        restore_factory: str | None = None,
    ) -> None:
        self._advance_callbacks[name] = callback
        if required_for_advance:
            self._module_requirements[name] = {
                "required_for_advance": True,
                "restore_factory": restore_factory or name,
            }

    def set_module_state(self, name: str, state: dict[str, Any]) -> None:
        self.module_states[name] = copy.deepcopy(state)

    def module_state(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self.module_states[name])

    def register_person(self, person: PersonState) -> None:
        if person.person_id in self.people:
            raise ValueError(f"duplicate person id {person.person_id}")
        self.people[person.person_id] = copy.deepcopy(person)

    def add_item(self, batch: ItemBatch) -> None:
        if batch.batch_id in self.items:
            raise ValueError(f"duplicate item batch id {batch.batch_id}")
        if batch.quantity < 0.0:
            raise ValueError("item quantity cannot be negative")
        self.items[batch.batch_id] = copy.deepcopy(batch)

    def available_item_quantity(self, batch_id: str) -> float:
        batch = self.items[batch_id]
        reserved = sum(
            reservation.quantity
            for reservation in self.reservations.values()
            if reservation.batch_id == batch_id
        )
        return max(0.0, batch.quantity - reserved)

    def reserve_item(
        self,
        *,
        batch_id: str,
        quantity: float,
        action_id: str,
        purpose: str,
    ) -> ItemReservation:
        if batch_id not in self.items:
            raise KeyError(f"unknown item batch {batch_id}")
        if quantity <= 0.0:
            raise ValueError("reservation quantity must be positive")
        available = self.available_item_quantity(batch_id)
        if quantity - available > 1e-9:
            raise ValueError("insufficient unreserved item quantity")
        action = self.actions.get(action_id)
        if action is None or action.status not in {"starting", "active"}:
            raise ValueError(
                "reservation requires a starting or active action"
            )
        self.reservation_sequence += 1
        reservation = ItemReservation(
            reservation_id=(
                f"{self.manifest.run_id}:r{self.reservation_sequence:08d}"
            ),
            batch_id=batch_id,
            action_id=action_id,
            quantity=quantity,
            created_at_world_seconds=self.clock.current_world_seconds,
            purpose=purpose,
        )
        self.reservations[reservation.reservation_id] = reservation
        self.emit_event(
            event_type="item_reserved",
            actor_ids=[action.person_id],
            action_id=action_id,
            facts={
                "reservation_id": reservation.reservation_id,
                "batch_id": batch_id,
                "quantity": quantity,
                "purpose": purpose,
            },
        )
        return reservation

    def release_reservation(self, reservation_id: str) -> None:
        reservation = self.reservations.pop(reservation_id, None)
        if reservation is None:
            raise KeyError(f"unknown reservation {reservation_id}")
        action = self.actions.get(reservation.action_id)
        self.emit_event(
            event_type="item_reservation_released",
            actor_ids=[action.person_id] if action else [],
            action_id=reservation.action_id,
            facts={
                "reservation_id": reservation_id,
                "batch_id": reservation.batch_id,
                "quantity": reservation.quantity,
            },
        )

    def transfer_reserved_item(
        self,
        reservation_id: str,
        *,
        to_owner_kind: str,
        to_owner_id: str,
        to_location: Location | None,
    ) -> ItemBatch:
        reservation = self.reservations.get(reservation_id)
        if reservation is None:
            raise KeyError(f"unknown reservation {reservation_id}")
        source = self.items[reservation.batch_id]
        if reservation.quantity - source.quantity > 1e-9:
            raise ValueError("reserved quantity exceeds source quantity")
        source.quantity -= reservation.quantity
        if source.quantity < -1e-9:
            raise ValueError("item quantity became negative")
        self.item_sequence += 1
        batch = ItemBatch(
            batch_id=f"{source.batch_id}:transfer:{self.item_sequence:06d}",
            category=source.category,
            quantity=reservation.quantity,
            unit=source.unit,
            state=source.state,
            owner_kind=to_owner_kind,
            owner_id=to_owner_id,
            location=to_location,
            source_event_id=None,
            kcal_per_kg=source.kcal_per_kg,
            attributes=dict(source.attributes),
        )
        self.items[batch.batch_id] = batch
        action = self.actions.get(reservation.action_id)
        event = self.emit_event(
            event_type="item_transferred",
            actor_ids=[action.person_id] if action else [],
            action_id=reservation.action_id,
            facts={
                "reservation_id": reservation_id,
                "source_batch_id": source.batch_id,
                "output_batch_id": batch.batch_id,
                "quantity": batch.quantity,
                "unit": batch.unit,
                "to_owner_kind": to_owner_kind,
                "to_owner_id": to_owner_id,
            },
            location=to_location,
        )
        batch.source_event_id = event.event_id
        del self.reservations[reservation_id]
        return batch

    def consume_reserved_item(
        self,
        reservation_id: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        reservation = self.reservations.get(reservation_id)
        if reservation is None:
            raise KeyError(f"unknown reservation {reservation_id}")
        batch = self.items[reservation.batch_id]
        if reservation.quantity - batch.quantity > 1e-9:
            raise ValueError("reserved quantity exceeds batch quantity")
        batch.quantity -= reservation.quantity
        if batch.quantity < -1e-9:
            raise ValueError("item quantity became negative")
        action = self.actions.get(reservation.action_id)
        event = self.emit_event(
            event_type="item_consumed",
            actor_ids=[action.person_id] if action else [],
            action_id=reservation.action_id,
            facts={
                "reservation_id": reservation_id,
                "batch_id": batch.batch_id,
                "quantity": reservation.quantity,
                "unit": batch.unit,
                "reason": reason,
            },
        )
        del self.reservations[reservation_id]
        return {
            "event_id": event.event_id,
            "batch_id": batch.batch_id,
            "quantity": reservation.quantity,
            "unit": batch.unit,
            "reason": reason,
        }

    def submit_action(self, intent: ActionIntent) -> ActionRecord:
        if intent.action_id in self.actions:
            raise ValueError(f"duplicate action id {intent.action_id}")
        if intent.person_id not in self.people:
            raise KeyError(f"unknown person {intent.person_id}")
        if intent.expected_duration_seconds <= 0:
            raise ValueError("physical action duration must be positive")
        if intent.formed_at_world_seconds != self.clock.current_world_seconds:
            raise ValueError("intent formation time must equal current world time")
        action = ActionRecord(
            action_id=intent.action_id,
            person_id=intent.person_id,
            action_type=intent.action_type,
            status="submitted",
            created_at_world_seconds=intent.formed_at_world_seconds,
            expected_duration_seconds=intent.expected_duration_seconds,
            target=copy.deepcopy(intent.target),
            known_conditions=copy.deepcopy(intent.known_conditions),
            expected_outcome=intent.expected_outcome,
            requested_participants=copy.deepcopy(
                intent.requested_participants
            ),
        )
        self.actions[action.action_id] = action
        event = self.emit_event(
            event_type="action_intent_submitted",
            actor_ids=[action.person_id],
            action_id=action.action_id,
            facts={
                "action_type": action.action_type,
                "known_conditions": action.known_conditions,
                "expected_outcome": action.expected_outcome,
            },
        )
        action.reason_event_ids.append(event.event_id)
        return action

    def start_action(self, action_id: str) -> ActionRecord:
        action = self.actions[action_id]
        if action.status != "submitted":
            raise ValueError(f"action {action_id} is not submitted")
        handler = self.handlers.get(action.action_type)
        if handler is None:
            raise KeyError(f"no handler for action type {action.action_type}")
        person = self.people[action.person_id]
        if not person.alive:
            return self._block_action(
                action,
                reason="actor_not_alive",
                facts={"person_id": person.person_id},
            )
        if person.current_action_id is not None:
            return self._block_action(
                action,
                reason="actor_busy",
                facts={
                    "person_id": person.person_id,
                    "current_action_id": person.current_action_id,
                },
            )
        intent = ActionIntent(
            action_id=action.action_id,
            person_id=action.person_id,
            action_type=action.action_type,
            formed_at_world_seconds=action.created_at_world_seconds,
            expected_duration_seconds=action.expected_duration_seconds,
            target=copy.deepcopy(action.target),
            known_conditions=copy.deepcopy(action.known_conditions),
            expected_outcome=action.expected_outcome,
            requested_participants=copy.deepcopy(
                action.requested_participants
            ),
        )
        validation = handler.validate(self, intent)
        if not validation.allowed:
            return self._block_action(
                action,
                reason=validation.reason,
                facts=validation.facts,
            )
        backup_action = copy.deepcopy(action)
        backup_reservations = copy.deepcopy(self.reservations)
        backup_items = copy.deepcopy(self.items)
        backup_person = copy.deepcopy(person)
        backup_scheduled_events = copy.deepcopy(self.scheduled_events)
        backup_event_sequence = self.event_sequence
        backup_event_count = len(self.events)
        backup_scheduled_sequence = self.scheduled_sequence
        action.status = "starting"
        action.started_at_world_seconds = self.clock.current_world_seconds
        action.expected_end_world_seconds = (
            self.clock.current_world_seconds
            + action.expected_duration_seconds
        )
        action.participants = [action.person_id]
        try:
            handler.begin(self, action)
        except Exception as exc:
            self.actions[action.action_id] = backup_action
            self.reservations = backup_reservations
            self.items = backup_items
            self.people[person.person_id] = backup_person
            self.scheduled_events = backup_scheduled_events
            self.event_sequence = backup_event_sequence
            self.scheduled_sequence = backup_scheduled_sequence
            del self.events[backup_event_count:]
            action = self.actions[action.action_id]
            return self._block_action(
                action,
                reason="handler_begin_failed",
                facts={
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                },
            )
        action.status = "active"
        person.current_action_id = action.action_id
        event = self.emit_event(
            event_type="action_started",
            actor_ids=action.participants,
            action_id=action.action_id,
            facts={
                "action_type": action.action_type,
                "expected_end_world_seconds": (
                    action.expected_end_world_seconds
                ),
                "validation": validation.facts,
            },
        )
        action.reason_event_ids.append(event.event_id)
        return action

    def _block_action(
        self,
        action: ActionRecord,
        *,
        reason: str,
        facts: dict[str, Any] | None = None,
    ) -> ActionRecord:
        action.status = "blocked"
        action.ended_at_world_seconds = self.clock.current_world_seconds
        action.result = {
            "reason": reason,
            "facts": copy.deepcopy(facts or {}),
        }
        event = self.emit_event(
            event_type="action_blocked",
            actor_ids=[action.person_id],
            action_id=action.action_id,
            facts=action.result,
        )
        action.reason_event_ids.append(event.event_id)
        return action

    def interrupt_action(
        self, action_id: str, *, reason: str
    ) -> ActionRecord:
        action = self.actions[action_id]
        if action.status != "active":
            raise ValueError(f"action {action_id} is not active")
        result = self.handlers[action.action_type].interrupt(
            self, action, reason
        )
        action.status = "interrupted"
        action.ended_at_world_seconds = self.clock.current_world_seconds
        action.result = result
        person = self.people[action.person_id]
        if person.current_action_id == action.action_id:
            person.current_action_id = None
        event = self.emit_event(
            event_type="action_interrupted",
            actor_ids=action.participants,
            action_id=action.action_id,
            facts={
                "reason": reason,
                "progress_seconds": action.progress_seconds,
                "result": result,
            },
        )
        action.reason_event_ids.append(event.event_id)
        return action

    def _complete_due_actions(self) -> None:
        for action in sorted(
            self.actions.values(),
            key=lambda item: (
                item.expected_end_world_seconds
                if item.expected_end_world_seconds is not None
                else 10**30,
                item.action_id,
            ),
        ):
            if action.status != "active":
                continue
            if (
                action.expected_end_world_seconds is None
                or action.expected_end_world_seconds
                > self.clock.current_world_seconds
            ):
                continue
            handler = self.handlers[action.action_type]
            result = handler.complete(self, action)
            action.status = "completed"
            action.ended_at_world_seconds = action.expected_end_world_seconds
            action.result = result
            output = result.get("output_batch_id")
            if output is not None:
                action.output_batch_ids.append(str(output))
            person = self.people[action.person_id]
            if person.current_action_id == action.action_id:
                person.current_action_id = None
            event = self.emit_event(
                event_type="action_completed",
                actor_ids=action.participants,
                action_id=action.action_id,
                facts=result,
            )
            action.reason_event_ids.append(event.event_id)

    def schedule_event(
        self,
        *,
        due_world_seconds: int,
        event_type: str,
        actor_ids: list[str] | None = None,
        facts: dict[str, Any] | None = None,
        action_id: str | None = None,
        cause_event_ids: list[str] | None = None,
        observed_by: list[str] | None = None,
        location: Location | None = None,
    ) -> ScheduledEvent:
        if due_world_seconds < self.clock.current_world_seconds:
            raise ValueError("scheduled event cannot be in the past")
        self.scheduled_sequence += 1
        scheduled = ScheduledEvent(
            scheduled_id=(
                f"{self.manifest.run_id}:q{self.scheduled_sequence:08d}"
            ),
            due_world_seconds=due_world_seconds,
            event_type=event_type,
            actor_ids=copy.deepcopy(actor_ids or []),
            facts=copy.deepcopy(facts or {}),
            action_id=action_id,
            cause_event_ids=copy.deepcopy(cause_event_ids or []),
            observed_by=copy.deepcopy(observed_by or []),
            location=location,
        )
        self.scheduled_events.append(scheduled)
        return scheduled

    def _process_current_boundary(self) -> None:
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for _ in range(10_000):
            due_events = tuple(
                sorted(
                    event.scheduled_id
                    for event in self.scheduled_events
                    if event.due_world_seconds
                    <= self.clock.current_world_seconds
                )
            )
            due_actions = tuple(
                sorted(
                    action.action_id
                    for action in self.actions.values()
                    if action.status == "active"
                    and action.expected_end_world_seconds is not None
                    and action.expected_end_world_seconds
                    <= self.clock.current_world_seconds
                )
            )
            if not due_events and not due_actions:
                return
            signature = (due_events, due_actions)
            if signature in seen:
                raise RuntimeError(
                    "current-time event/action loop made no progress"
                )
            seen.add(signature)
            self._emit_due_scheduled_events()
            self._complete_due_actions()
        raise RuntimeError(
            "current-time event/action loop exceeded safety limit"
        )

    def _emit_due_scheduled_events(self) -> None:
        due = [
            event
            for event in self.scheduled_events
            if event.due_world_seconds <= self.clock.current_world_seconds
        ]
        for scheduled in sorted(
            due, key=lambda item: (item.due_world_seconds, item.scheduled_id)
        ):
            self.scheduled_events.remove(scheduled)
            self.emit_event(
                event_type=scheduled.event_type,
                actor_ids=scheduled.actor_ids,
                action_id=scheduled.action_id,
                cause_event_ids=scheduled.cause_event_ids,
                facts=scheduled.facts,
                observed_by=scheduled.observed_by,
                location=scheduled.location,
            )

    def emit_event(
        self,
        *,
        event_type: str,
        actor_ids: list[str],
        action_id: str | None,
        facts: dict[str, Any],
        cause_event_ids: list[str] | None = None,
        observed_by: list[str] | None = None,
        location: Location | None = None,
    ) -> Event:
        if self.events and (
            self.clock.current_world_seconds < self.events[-1].world_seconds
        ):
            raise ValueError("event time cannot move backwards")
        self.event_sequence += 1
        event = Event(
            event_id=(
                f"{self.manifest.run_id}:e{self.event_sequence:08d}"
            ),
            run_id=self.manifest.run_id,
            sequence=self.event_sequence,
            world_seconds=self.clock.current_world_seconds,
            event_type=event_type,
            actor_ids=copy.deepcopy(actor_ids),
            action_id=action_id,
            cause_event_ids=copy.deepcopy(cause_event_ids or []),
            facts=copy.deepcopy(facts),
            observed_by=copy.deepcopy(observed_by or []),
            location=location,
        )
        self.events.append(event)
        return event

    def record_decision(self, trace: DecisionTrace) -> None:
        if trace.decision_id in self.decisions:
            raise ValueError(f"duplicate decision id {trace.decision_id}")
        self.decisions[trace.decision_id] = copy.deepcopy(trace)

    def record_knowledge(
        self,
        *,
        person_id: str,
        subject: str,
        stage: str,
        source_event_id: str | None,
        certainty: float,
    ) -> None:
        if person_id not in self.people:
            raise KeyError(f"unknown person {person_id}")
        self.knowledge.setdefault(person_id, []).append(
            {
                "subject": subject,
                "stage": stage,
                "source_event_id": source_event_id,
                "learned_at_world_seconds": (
                    self.clock.current_world_seconds
                ),
                "certainty": certainty,
            }
        )

    def record_known_location(
        self,
        *,
        person_id: str,
        location: Location,
        label: str,
        source_event_id: str | None,
        certainty: float,
    ) -> None:
        if person_id not in self.people:
            raise KeyError(f"unknown person {person_id}")
        self.known_locations.setdefault(person_id, []).append(
            {
                "label": label,
                "location": location.to_dict(),
                "source_event_id": source_event_id,
                "learned_at_world_seconds": (
                    self.clock.current_world_seconds
                ),
                "certainty": certainty,
            }
        )

    def set_relationship(
        self,
        *,
        person_id: str,
        other_person_id: str,
        domain: str,
        value: float,
    ) -> None:
        self.relationships.setdefault(person_id, {})[
            f"{other_person_id}:{domain}"
        ] = value

    def add_social_response(self, response: SocialResponse) -> None:
        self.social_responses[response.response_id] = copy.deepcopy(response)

    def add_commitment(self, commitment: Commitment) -> None:
        self.commitments[commitment.commitment_id] = copy.deepcopy(
            commitment
        )

    def stated_claim(self, person_id: str, claim: str) -> None:
        self.stated_claims.setdefault(person_id, []).append(claim)

    def perceived_state(self, person_id: str) -> PerceivedState:
        person = self.people[person_id]
        known_items = [
            batch.batch_id
            for batch in self.items.values()
            if (
                batch.owner_kind == "person"
                and batch.owner_id == person_id
            )
            or (
                batch.owner_kind == "household"
                and batch.owner_id == person.household_id
            )
        ]
        commitments = [
            commitment.to_dict()
            for commitment in self.commitments.values()
            if commitment.responder_id == person_id
            or commitment.beneficiary_id == person_id
        ]
        return PerceivedState(
            person_id=person_id,
            generated_at_world_seconds=self.clock.current_world_seconds,
            location=person.location,
            body=copy.deepcopy(person.body),
            current_action_id=person.current_action_id,
            knowledge=copy.deepcopy(self.knowledge.get(person_id, [])),
            known_locations=copy.deepcopy(
                self.known_locations.get(person_id, [])
            ),
            known_item_ids=list(known_items),
            pending_commitments=copy.deepcopy(commitments),
            stated_claims=list(self.stated_claims.get(person_id, [])),
        )

    def query_events(
        self,
        *,
        person_id: str | None = None,
        action_id: str | None = None,
        event_type: str | None = None,
        since_world_seconds: int | None = None,
        until_world_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        selected: list[Event] = []
        for event in self.events:
            if person_id is not None and person_id not in event.actor_ids:
                if person_id not in event.observed_by:
                    continue
            if action_id is not None and event.action_id != action_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if (
                since_world_seconds is not None
                and event.world_seconds < since_world_seconds
            ):
                continue
            if (
                until_world_seconds is not None
                and event.world_seconds > until_world_seconds
            ):
                continue
            selected.append(event)
        return copy.deepcopy([event.to_dict() for event in selected])

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "schema_version": CORE_SNAPSHOT_SCHEMA_VERSION,
            "manifest": self.manifest.to_dict(),
            "clock": self.clock.to_dict(),
            "paused": self.paused,
            "random_state": _encode_rng_state(self.random.getstate()),
            "people": {
                key: value.to_dict()
                for key, value in sorted(self.people.items())
            },
            "items": {
                key: value.to_dict()
                for key, value in sorted(self.items.items())
            },
            "reservations": {
                key: value.to_dict()
                for key, value in sorted(self.reservations.items())
            },
            "relationships": self.relationships,
            "knowledge": self.knowledge,
            "known_locations": self.known_locations,
            "stated_claims": self.stated_claims,
            "actions": {
                key: value.to_dict()
                for key, value in sorted(self.actions.items())
            },
            "events": [event.to_dict() for event in self.events],
            "scheduled_events": [
                event.to_dict() for event in self.scheduled_events
            ],
            "decisions": {
                key: value.to_dict()
                for key, value in sorted(self.decisions.items())
            },
            "social_responses": {
                key: value.to_dict()
                for key, value in sorted(self.social_responses.items())
            },
            "commitments": {
                key: value.to_dict()
                for key, value in sorted(self.commitments.items())
            },
            "module_states": self.module_states,
            "module_requirements": self._module_requirements,
            "sequences": {
                "event": self.event_sequence,
                "item": self.item_sequence,
                "reservation": self.reservation_sequence,
                "scheduled": self.scheduled_sequence,
            },
        }
        return copy.deepcopy(snapshot)

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any],
        *,
        handlers: dict[str, ActionHandler] | None = None,
        advance_callbacks: dict[
            str, Callable[[SimulationCore, int, int], None]
        ]
        | None = None,
        module_factories: dict[
            str,
            Callable[
                [SimulationCore, dict[str, Any]],
                Callable[[SimulationCore, int, int], None] | None,
            ],
        ]
        | None = None,
    ) -> SimulationCore:
        snapshot = copy.deepcopy(snapshot)
        if int(snapshot["schema_version"]) != CORE_SNAPSHOT_SCHEMA_VERSION:
            raise ContractVersionError("unsupported core snapshot schema")
        sequences = snapshot["sequences"]
        core = cls(
            manifest=RunManifest.from_dict(snapshot["manifest"]),
            handlers=handlers,
            clock=SimulationClock.from_dict(snapshot["clock"]),
            people={
                key: PersonState.from_dict(value)
                for key, value in snapshot["people"].items()
            },
            items={
                key: ItemBatch.from_dict(value)
                for key, value in snapshot["items"].items()
            },
            reservations={
                key: ItemReservation.from_dict(value)
                for key, value in snapshot["reservations"].items()
            },
            relationships=snapshot["relationships"],
            knowledge=snapshot["knowledge"],
            known_locations=snapshot["known_locations"],
            stated_claims=snapshot["stated_claims"],
            actions={
                key: ActionRecord.from_dict(value)
                for key, value in snapshot["actions"].items()
            },
            events=[
                Event.from_dict(value) for value in snapshot["events"]
            ],
            scheduled_events=[
                ScheduledEvent.from_dict(value)
                for value in snapshot["scheduled_events"]
            ],
            decisions={
                key: DecisionTrace.from_dict(value)
                for key, value in snapshot["decisions"].items()
            },
            social_responses={
                key: SocialResponse.from_dict(value)
                for key, value in snapshot["social_responses"].items()
            },
            commitments={
                key: Commitment.from_dict(value)
                for key, value in snapshot["commitments"].items()
            },
            module_states=snapshot["module_states"],
            event_sequence=int(sequences["event"]),
            item_sequence=int(sequences["item"]),
            reservation_sequence=int(sequences["reservation"]),
            scheduled_sequence=int(sequences["scheduled"]),
            paused=bool(snapshot["paused"]),
            random_state=snapshot["random_state"],
        )
        for name, callback in (advance_callbacks or {}).items():
            core.register_advance_callback(name, callback)
        core._module_requirements.update(
            copy.deepcopy(snapshot.get("module_requirements", {}))
        )
        return core

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        snapshot_json = json.dumps(
            self.snapshot(), ensure_ascii=False, sort_keys=True
        )
        connection = sqlite3.connect(temporary)
        try:
            connection.execute(
                """
                CREATE TABLE run_state (
                    run_id TEXT PRIMARY KEY,
                    contract_version TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                )
                """
            )
            connection.execute(
                "INSERT INTO run_state VALUES (?, ?, ?, ?)",
                (
                    self.manifest.run_id,
                    self.manifest.contract_version,
                    json.dumps(
                        self.manifest.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    snapshot_json,
                ),
            )
            connection.executemany(
                "INSERT INTO events VALUES (?, ?, ?)",
                [
                    (
                        self.manifest.run_id,
                        event.sequence,
                        json.dumps(
                            event.to_dict(),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    for event in self.events
                ],
            )
            connection.commit()
        finally:
            connection.close()
        temporary.replace(path)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        handlers: dict[str, ActionHandler] | None = None,
        advance_callbacks: dict[
            str, Callable[[SimulationCore, int, int], None]
        ]
        | None = None,
        module_factories: dict[
            str,
            Callable[
                [SimulationCore, dict[str, Any]],
                Callable[[SimulationCore, int, int], None] | None,
            ],
        ]
        | None = None,
    ) -> SimulationCore:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                """
                SELECT contract_version, snapshot_json
                FROM run_state
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ValueError("save file contains no run state")
        contract_version, snapshot_json = row
        if contract_version != CONTRACT_VERSION:
            raise ContractVersionError(
                f"save contract {contract_version} does not match "
                f"{CONTRACT_VERSION}"
            )
        snapshot = json.loads(snapshot_json)
        active_types = {
            action.action_type
            for action in (
                ActionRecord.from_dict(value)
                for value in snapshot["actions"].values()
            )
            if action.status == "active"
        }
        missing_handlers = active_types - set((handlers or {}).keys())
        if missing_handlers:
            raise ValueError(
                "missing handlers for active actions: "
                f"{sorted(missing_handlers)}"
            )
        core = cls.from_snapshot(
            snapshot,
            handlers=handlers,
            advance_callbacks=advance_callbacks,
        )
        for name, requirement in core._module_requirements.items():
            if not requirement.get("required_for_advance", False):
                continue
            if name in core._advance_callbacks:
                continue
            factory = (module_factories or {}).get(name)
            if factory is None:
                raise ModuleBindingError(
                    f"required module {name!r} is not bound after restore; "
                    "provide module_factories or advance_callbacks"
                )
            callback = factory(core, core.module_state(name))
            if callback is not None:
                core.register_advance_callback(
                    name,
                    callback,
                    required_for_advance=True,
                    restore_factory=str(
                        requirement.get("restore_factory", name)
                    ),
                )
            if name not in core._advance_callbacks:
                raise ModuleBindingError(
                    f"module factory for {name!r} did not bind a callback"
                )
        return core


def create_run(
    manifest: RunManifest,
    handlers: dict[str, ActionHandler] | None = None,
) -> SimulationCore:
    return SimulationCore.create(manifest, handlers)


def _encode_rng_state(state: tuple[Any, ...]) -> list[Any]:
    version, internal_state, gauss = state
    return [version, list(internal_state), gauss]


def _decode_rng_state(value: list[Any]) -> tuple[Any, ...]:
    version, internal_state, gauss = value
    return (version, tuple(internal_state), gauss)
