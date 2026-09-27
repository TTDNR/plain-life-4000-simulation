"""Shared R1 contracts for the unified simulation core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CONTRACT_VERSION = "R1"
WORLD_SECONDS_PER_DAY = 24 * 60 * 60


class ContractVersionError(ValueError):
    """Raised when a run or save file uses an unsupported contract."""


@dataclass(frozen=True)
class Location:
    x_m: float
    y_m: float
    cell_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> Location | None:
        if value is None:
            return None
        return cls(
            x_m=float(value["x_m"]),
            y_m=float(value["y_m"]),
            cell_index=(
                int(value["cell_index"])
                if value.get("cell_index") is not None
                else None
            ),
        )


@dataclass
class RunManifest:
    run_id: str
    code_commit: str
    contract_version: str
    scenario_id: str
    scenario_fingerprint: str
    parameter_fingerprint: str
    random_seed: int
    environment_fingerprint: str
    population_fingerprint: str
    initial_day_of_year: int
    start_world_seconds: int
    day_seconds: int
    mode: str
    end_world_seconds: int | None = None
    unsupported_capabilities: list[str] = field(default_factory=list)
    dependency_versions: dict[str, str] = field(default_factory=dict)
    created_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunManifest:
        return cls(**value)


@dataclass
class PersonState:
    person_id: str
    household_id: str
    location: Location
    body: dict[str, Any] = field(default_factory=dict)
    current_action_id: str | None = None
    alive: bool = True
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "household_id": self.household_id,
            "location": self.location.to_dict(),
            "body": self.body,
            "current_action_id": self.current_action_id,
            "alive": self.alive,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PersonState:
        return cls(
            person_id=str(value["person_id"]),
            household_id=str(value["household_id"]),
            location=Location.from_dict(value["location"]),  # type: ignore[arg-type]
            body=dict(value.get("body", {})),
            current_action_id=value.get("current_action_id"),
            alive=bool(value.get("alive", True)),
            attributes=dict(value.get("attributes", {})),
        )


@dataclass
class ItemBatch:
    batch_id: str
    category: str
    quantity: float
    unit: str
    state: str
    owner_kind: str
    owner_id: str
    location: Location | None = None
    source_event_id: str | None = None
    kcal_per_kg: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "category": self.category,
            "quantity": self.quantity,
            "unit": self.unit,
            "state": self.state,
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "location": (
                self.location.to_dict() if self.location is not None else None
            ),
            "source_event_id": self.source_event_id,
            "kcal_per_kg": self.kcal_per_kg,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ItemBatch:
        return cls(
            batch_id=str(value["batch_id"]),
            category=str(value["category"]),
            quantity=float(value["quantity"]),
            unit=str(value["unit"]),
            state=str(value["state"]),
            owner_kind=str(value["owner_kind"]),
            owner_id=str(value["owner_id"]),
            location=Location.from_dict(value.get("location")),
            source_event_id=value.get("source_event_id"),
            kcal_per_kg=(
                float(value["kcal_per_kg"])
                if value.get("kcal_per_kg") is not None
                else None
            ),
            attributes=dict(value.get("attributes", {})),
        )


@dataclass
class ItemReservation:
    reservation_id: str
    batch_id: str
    action_id: str
    quantity: float
    created_at_world_seconds: int
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ItemReservation:
        return cls(**value)


@dataclass
class ActionIntent:
    action_id: str
    person_id: str
    action_type: str
    formed_at_world_seconds: int
    expected_duration_seconds: int
    target: dict[str, Any] = field(default_factory=dict)
    known_conditions: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    requested_participants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ActionIntent:
        return cls(**value)


@dataclass
class ActionValidation:
    allowed: bool
    reason: str
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRecord:
    action_id: str
    person_id: str
    action_type: str
    status: str
    created_at_world_seconds: int
    expected_duration_seconds: int
    target: dict[str, Any]
    known_conditions: list[str]
    expected_outcome: str
    requested_participants: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    started_at_world_seconds: int | None = None
    expected_end_world_seconds: int | None = None
    ended_at_world_seconds: int | None = None
    progress_seconds: int = 0
    reservations: list[str] = field(default_factory=list)
    consumed_resources: list[dict[str, Any]] = field(default_factory=list)
    output_batch_ids: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    reason_event_ids: list[str] = field(default_factory=list)
    handler_state: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.expected_duration_seconds - self.progress_seconds)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ActionRecord:
        return cls(**value)


@dataclass
class SocialResponse:
    response_id: str
    request_id: str
    responder_id: str
    responded_at_world_seconds: int
    response_type: str
    commitment_id: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SocialResponse:
        return cls(**value)


@dataclass
class Commitment:
    commitment_id: str
    request_id: str
    responder_id: str
    beneficiary_id: str
    service_or_item: str
    quantity: float | None
    unit: str | None
    due_start_world_seconds: int | None
    due_end_world_seconds: int | None
    status: str
    source_response_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Commitment:
        return cls(**value)


@dataclass
class DecisionTrace:
    decision_id: str
    person_id: str
    made_at_world_seconds: int
    trigger: str
    information_refs: list[str]
    considered_options: list[str]
    chosen_option: str
    reasons: list[str]
    expected_outcome: str
    actual_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DecisionTrace:
        return cls(**value)


@dataclass
class Event:
    event_id: str
    run_id: str
    sequence: int
    world_seconds: int
    event_type: str
    actor_ids: list[str]
    action_id: str | None
    cause_event_ids: list[str]
    facts: dict[str, Any]
    observed_by: list[str] = field(default_factory=list)
    location: Location | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "world_seconds": self.world_seconds,
            "event_type": self.event_type,
            "actor_ids": self.actor_ids,
            "action_id": self.action_id,
            "cause_event_ids": self.cause_event_ids,
            "facts": self.facts,
            "observed_by": self.observed_by,
            "location": (
                self.location.to_dict() if self.location is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Event:
        return cls(
            event_id=str(value["event_id"]),
            run_id=str(value["run_id"]),
            sequence=int(value["sequence"]),
            world_seconds=int(value["world_seconds"]),
            event_type=str(value["event_type"]),
            actor_ids=list(value.get("actor_ids", [])),
            action_id=value.get("action_id"),
            cause_event_ids=list(value.get("cause_event_ids", [])),
            facts=dict(value.get("facts", {})),
            observed_by=list(value.get("observed_by", [])),
            location=Location.from_dict(value.get("location")),
        )


@dataclass
class ScheduledEvent:
    scheduled_id: str
    due_world_seconds: int
    event_type: str
    actor_ids: list[str]
    facts: dict[str, Any]
    action_id: str | None = None
    cause_event_ids: list[str] = field(default_factory=list)
    observed_by: list[str] = field(default_factory=list)
    location: Location | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled_id": self.scheduled_id,
            "due_world_seconds": self.due_world_seconds,
            "event_type": self.event_type,
            "actor_ids": self.actor_ids,
            "facts": self.facts,
            "action_id": self.action_id,
            "cause_event_ids": self.cause_event_ids,
            "observed_by": self.observed_by,
            "location": (
                self.location.to_dict() if self.location is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ScheduledEvent:
        return cls(
            scheduled_id=str(value["scheduled_id"]),
            due_world_seconds=int(value["due_world_seconds"]),
            event_type=str(value["event_type"]),
            actor_ids=list(value.get("actor_ids", [])),
            facts=dict(value.get("facts", {})),
            action_id=value.get("action_id"),
            cause_event_ids=list(value.get("cause_event_ids", [])),
            observed_by=list(value.get("observed_by", [])),
            location=Location.from_dict(value.get("location")),
        )


@dataclass
class PerceivedState:
    person_id: str
    generated_at_world_seconds: int
    location: Location
    body: dict[str, Any]
    current_action_id: str | None
    knowledge: list[dict[str, Any]]
    known_locations: list[dict[str, Any]]
    known_item_ids: list[str]
    pending_commitments: list[dict[str, Any]]
    stated_claims: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "generated_at_world_seconds": self.generated_at_world_seconds,
            "location": self.location.to_dict(),
            "body": self.body,
            "current_action_id": self.current_action_id,
            "knowledge": self.knowledge,
            "known_locations": self.known_locations,
            "known_item_ids": self.known_item_ids,
            "pending_commitments": self.pending_commitments,
            "stated_claims": self.stated_claims,
        }
