"""Deterministic household and population initialization."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any, Iterable


SKILL_PROFILES: dict[str, float] = {
    "basic_plant_identification": 0.78,
    "water_finding": 0.72,
    "water_safety": 0.42,
    "fire_keeping": 0.15,
    "fire_friction": 0.08,
    "shelter_building": 0.30,
    "stone_tool_making": 0.12,
    "wood_working": 0.22,
    "fiber_cordage": 0.28,
    "wetland_plant_knowledge": 0.45,
    "tree_food_knowledge": 0.45,
    "acorn_processing": 0.35,
    "fishing": 0.22,
    "hunting_or_trapping": 0.12,
    "cooking": 0.65,
    "childcare": 0.62,
}

OCCUPATIONS = (
    "domestic_care",
    "plant_gatherer",
    "fisher",
    "hunter",
    "wood_worker",
    "stone_worker",
    "fiber_worker",
    "cook",
    "herder",
    "craft_assistant",
)


@dataclass
class Person:
    id: str
    age_years: int
    life_stage: str
    sex: str
    household_id: str
    occupation: str
    caregiver_ids: list[str]
    skills: list[dict[str, Any]]
    life_history: list[str]
    mobility: float
    health_status: str


@dataclass
class Household:
    id: str
    member_ids: list[str]
    relation_notes: list[str]
    initial_cell_index: int | None = None
    current_cell_index: int | None = None


@dataclass
class PopulationState:
    target_total: int
    seed: int
    people: list[Person]
    households: list[Household]
    kinship_edges: list[dict[str, str]]
    pregnancy_events: list[dict[str, Any]]
    lactation_links: list[dict[str, Any]]
    fingerprint: str

    @property
    def people_by_id(self) -> dict[str, Person]:
        return {person.id: person for person in self.people}

    @property
    def households_by_id(self) -> dict[str, Household]:
        return {household.id: household for household in self.households}

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "people": [asdict(person) for person in self.people],
            "households": [
                {
                    "id": household.id,
                    "member_ids": household.member_ids,
                    "relation_notes": household.relation_notes,
                    "initial_cell_index": household.initial_cell_index,
                    "current_cell_index": household.current_cell_index,
                }
                for household in self.households
            ],
            "kinship_edges": self.kinship_edges,
            "pregnancy_events": self.pregnancy_events,
            "lactation_links": self.lactation_links,
            "fingerprint": self.fingerprint,
        }

    def summary(self) -> dict[str, Any]:
        age_bands = {
            "under_1": 0,
            "age_1_4": 0,
            "age_5_12": 0,
            "age_13_17": 0,
            "age_18_44": 0,
            "age_45_64": 0,
            "age_65_plus": 0,
        }
        for person in self.people:
            if person.age_years < 1:
                age_bands["under_1"] += 1
            elif person.age_years <= 4:
                age_bands["age_1_4"] += 1
            elif person.age_years <= 12:
                age_bands["age_5_12"] += 1
            elif person.age_years <= 17:
                age_bands["age_13_17"] += 1
            elif person.age_years <= 44:
                age_bands["age_18_44"] += 1
            elif person.age_years <= 64:
                age_bands["age_45_64"] += 1
            else:
                age_bands["age_65_plus"] += 1

        household_sizes: dict[str, int] = {}
        for household in self.households:
            key = str(len(household.member_ids))
            household_sizes[key] = household_sizes.get(key, 0) + 1

        skill_counts = {skill_id: 0 for skill_id in SKILL_PROFILES}
        for person in self.people:
            for skill in person.skills:
                skill_counts[skill["id"]] = skill_counts.get(skill["id"], 0) + 1

        infants = [person for person in self.people if person.life_stage == "infant"]
        dependent_people = [
            person
            for person in self.people
            if person.life_stage in {"infant", "toddler", "child"}
        ]
        active_people = [
            person
            for person in self.people
            if person.life_stage in {"adult", "elder"}
            and person.mobility >= 0.5
        ]
        caregiver_ids = {
            caregiver_id
            for person in dependent_people
            for caregiver_id in person.caregiver_ids
        }
        return {
            "target_total": self.target_total,
            "actual_total": len(self.people),
            "fingerprint": self.fingerprint,
            "age_bands": age_bands,
            "households": len(self.households),
            "household_sizes": household_sizes,
            "kinship_edges": len(self.kinship_edges),
            "pregnancy_events": len(self.pregnancy_events),
            "ongoing_pregnancies": sum(
                event["outcome"] == "ongoing"
                for event in self.pregnancy_events
            ),
            "lactation_links": len(self.lactation_links),
            "infants": len(infants),
            "infants_with_caregiver": sum(
                bool(person.caregiver_ids) for person in infants
            ),
            "dependent_people": len(dependent_people),
            "active_people": len(active_people),
            "caregiver_people": len(caregiver_ids),
            "skill_counts": skill_counts,
        }


def generate_population(seed: int, target_total: int = 4000) -> PopulationState:
    if target_total != 4000:
        raise ValueError("Phase 1 population target must be exactly 4000")
    rng = random.Random(seed)
    compositions = _household_compositions()
    if sum(base_size for base_size, _, _ in compositions) != target_total:
        raise AssertionError("Household composition does not sum to target total")

    child_ages = _child_age_pool()
    rng.shuffle(child_ages)
    child_cursor = 0
    people: list[Person] = []
    households: list[Household] = []
    kinship_edges: list[dict[str, str]] = []
    pregnancy_events: list[dict[str, Any]] = []
    lactation_links: list[dict[str, Any]] = []
    next_person_number = 1

    for household_number, (_, roles, child_count) in enumerate(
        compositions, start=1
    ):
        household_id = f"h{household_number:04d}"
        household_children_ages = child_ages[
            child_cursor : child_cursor + child_count
        ]
        child_cursor += child_count
        adult_people: list[Person] = []
        child_people: list[Person] = []

        youngest_child = min(household_children_ages) if household_children_ages else None
        for role_index, role in enumerate(roles):
            person_id = f"p{next_person_number:06d}"
            next_person_number += 1
            age, sex = _age_for_role(
                rng, role, youngest_child, previous=adult_people
            )
            person = _make_person(
                person_id,
                age,
                sex,
                household_id,
                rng,
            )
            adult_people.append(person)

        for child_index, age in enumerate(household_children_ages):
            child_id = f"p{next_person_number:06d}"
            next_person_number += 1
            sex = "female" if _stable_fraction(rng.random(), 0.5) == 1 else "male"
            child = _make_person(
                child_id,
                age,
                sex,
                household_id,
                rng,
            )
            child_people.append(child)
            caregivers = _choose_caregivers(adult_people)
            child.caregiver_ids = [person.id for person in caregivers]
            for caregiver in caregivers:
                kinship_edges.append(
                    {
                        "kind": "parent_child",
                        "from": caregiver.id,
                        "to": child.id,
                    }
                )
            if child.life_stage == "infant":
                mother = next(
                    (
                        person
                        for person in caregivers
                        if person.sex == "female"
                        and 15 <= person.age_years <= 49
                    ),
                    next(
                        (
                            person
                            for person in adult_people
                            if person.sex == "female"
                            and person.age_years <= 49
                        ),
                        None,
                    ),
                )
                if mother is not None:
                    pregnancy_events.append(
                        {
                            "person_id": mother.id,
                            "outcome": "live_birth",
                            "infant_id": child.id,
                            "days_before_initial_state": int(
                                (child.age_years + 0.5) * 365
                            ),
                        }
                    )
                    lactation_links.append(
                        {
                            "person_id": mother.id,
                            "infant_id": child.id,
                            "status": "active",
                        }
                    )

        for index in range(0, max(0, len(adult_people) - 1), 2):
            first = adult_people[index]
            second = adult_people[index + 1]
            if (
                first.sex != second.sex
                and abs(first.age_years - second.age_years) <= 12
                and _stable_fraction(rng.random(), 0.75) == 1
            ):
                kinship_edges.append(
                    {
                        "kind": "partner",
                        "from": first.id,
                        "to": second.id,
                    }
                )

        household_people = [*adult_people, *child_people]
        people.extend(household_people)
        households.append(
            Household(
                id=household_id,
                member_ids=[person.id for person in household_people],
                relation_notes=[
                    "household members may depend on, disagree with, or have unequal access to household labor"
                ],
            )
        )

    if child_cursor != len(child_ages):
        raise AssertionError("Not all child age slots were consumed")
    if len(people) != target_total:
        raise AssertionError(
            f"Generated {len(people)} people instead of {target_total}"
        )
    _add_ongoing_pregnancies(rng, people, households, pregnancy_events)
    state = PopulationState(
        target_total=target_total,
        seed=seed,
        people=people,
        households=households,
        kinship_edges=kinship_edges,
        pregnancy_events=pregnancy_events,
        lactation_links=lactation_links,
        fingerprint="",
    )
    state.fingerprint = _population_fingerprint(state)
    return state


def _household_compositions() -> list[tuple[int, list[str], int]]:
    compositions: list[tuple[int, list[str], int]] = []
    compositions.extend([(1, ["adult"], 0)] * 60)
    compositions.extend([(1, ["elder"], 0)] * 20)
    compositions.extend([(2, ["adult_f", "adult_m"], 0)] * 100)
    compositions.extend([(2, ["elder", "elder"], 0)] * 20)
    compositions.extend([(3, ["adult_f", "adult_m"], 1)] * 100)
    compositions.extend([(3, ["adult_f", "elder"], 1)] * 40)
    compositions.extend([(3, ["adult_f", "adult", "adult"], 0)] * 40)
    compositions.extend([(4, ["adult_f", "adult_m"], 2)] * 60)
    compositions.extend([(4, ["adult_f", "adult", "adult"], 1)] * 100)
    compositions.extend([(4, ["adult", "adult", "adult", "adult"], 0)] * 60)
    compositions.extend([(5, ["adult_f", "adult_m"], 3)] * 50)
    compositions.extend([(5, ["adult_f", "adult", "adult", "adult"], 1)] * 120)
    compositions.extend([(5, ["adult", "adult", "adult", "adult", "adult"], 0)] * 60)
    compositions.extend([(6, ["adult_f", "adult_m"], 4)] * 20)
    compositions.extend(
        [(6, ["adult_f", "adult", "adult", "adult", "adult"], 1)] * 80
    )
    compositions.extend([(7, ["adult_f", "adult_m"], 5)] * 10)
    compositions.extend(
        [(7, ["adult_f", "adult", "adult", "adult", "adult", "adult"], 1)] * 40
    )
    compositions.extend([(8, ["adult_f", "adult_m"], 6)] * 5)
    compositions.extend(
        [
            (
                8,
                [
                    "adult_f",
                    "adult",
                    "adult",
                    "adult",
                    "adult",
                    "adult",
                    "adult",
                ],
                1,
            )
        ]
        * 15
    )
    return compositions


def _child_age_pool() -> list[int]:
    ages = (
        [0] * 70
        + [1, 2] * 25
        + list(range(3, 5)) * 90
        + list(range(5, 13)) * 46
        + [12] * 7
        + list(range(13, 18)) * 50
    )
    if len(ages) != 925:
        raise AssertionError(f"Expected 925 child slots, got {len(ages)}")
    return ages


def _age_for_role(
    rng: random.Random,
    role: str,
    youngest_child: int | None,
    previous: list[Person],
) -> tuple[int, str]:
    if role == "elder":
        return rng.randint(65, 84), "female" if rng.random() < 0.52 else "male"
    if role in {"adult_f", "adult_m"}:
        if youngest_child is not None:
            lower = max(19, youngest_child + 18)
            upper = min(52, lower + 16)
        else:
            lower, upper = 18, 44
        age = rng.randint(lower, max(lower, upper))
        return age, "female" if role == "adult_f" else "male"
    if role == "adult" and previous and rng.random() < 0.18:
        return rng.randint(65, 76), "female" if rng.random() < 0.52 else "male"
    return rng.randint(18, 64), "female" if rng.random() < 0.5 else "male"


def _make_person(
    person_id: str,
    age: int,
    sex: str,
    household_id: str,
    rng: random.Random,
) -> Person:
    life_stage = _life_stage(age)
    occupation = "dependent" if age < 13 else rng.choice(OCCUPATIONS)
    mobility = 1.0
    health_status = "healthy"
    if age >= 13 and _stable_fraction(rng.random(), 0.04) == 1:
        mobility = 0.45
        health_status = "limited_mobility"
    elif age >= 65 and _stable_fraction(rng.random(), 0.12) == 1:
        mobility = 0.65
        health_status = "age_related_limitation"
    skills = _skills_for_person(person_id, age, occupation, rng)
    life_history = [f"born_in_origin_region_at_age_0"]
    if age >= 6:
        life_history.append("raised_in_origin_community")
    if age >= 13:
        life_history.append(f"learned_daily_work_as_{occupation}")
    if age >= 18:
        life_history.append("has_no_carried_in_property_or_office_in_new_world")
    if age >= 30:
        life_history.append("has_experience_with_seasonal_food_shortages")
    return Person(
        id=person_id,
        age_years=age,
        life_stage=life_stage,
        sex=sex,
        household_id=household_id,
        occupation=occupation,
        caregiver_ids=[],
        skills=skills,
        life_history=life_history,
        mobility=mobility,
        health_status=health_status,
    )


def _skills_for_person(
    person_id: str,
    age: int,
    occupation: str,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if age < 8:
        return []
    skills: list[dict[str, Any]] = []
    for skill_id, probability in SKILL_PROFILES.items():
        adjusted = probability
        if occupation == "plant_gatherer" and skill_id in {
            "basic_plant_identification",
            "wetland_plant_knowledge",
            "tree_food_knowledge",
            "acorn_processing",
        }:
            adjusted = min(0.95, adjusted + 0.3)
        if occupation == "fisher" and skill_id == "fishing":
            adjusted = min(0.95, adjusted + 0.55)
        if occupation in {"hunter", "fisher"} and skill_id == "hunting_or_trapping":
            adjusted = min(0.9, adjusted + 0.35)
        if occupation == "wood_worker" and skill_id in {
            "wood_working",
            "shelter_building",
        }:
            adjusted = min(0.95, adjusted + 0.35)
        if occupation == "stone_worker" and skill_id == "stone_tool_making":
            adjusted = min(0.95, adjusted + 0.5)
        if occupation == "domestic_care" and skill_id in {"cooking", "childcare"}:
            adjusted = min(0.98, adjusted + 0.25)
        if _stable_fraction(rng.random(), adjusted) != 1:
            continue
        practice = max(1, int(max(1, age - 12) * (0.3 + adjusted * 0.8)))
        skills.append(
            {
                "id": skill_id,
                "learned_via": (
                    f"household_and_origin_community_training:{occupation}"
                ),
                "practice_opportunities": practice,
                "proficiency": round(min(0.95, 0.2 + practice / 150.0), 3),
            }
        )
    return skills


def _choose_caregivers(adults: Iterable[Person]) -> list[Person]:
    choices = list(adults)
    mothers = [
        person
        for person in choices
        if person.sex == "female" and 15 <= person.age_years <= 55
    ]
    fathers = [
        person
        for person in choices
        if person.sex == "male" and 15 <= person.age_years <= 65
    ]
    caregivers: list[Person] = []
    if mothers:
        caregivers.append(mothers[0])
    if fathers:
        caregivers.append(fathers[0])
    if not caregivers and choices:
        caregivers.append(choices[0])
    return caregivers[:2]


def _add_ongoing_pregnancies(
    rng: random.Random,
    people: list[Person],
    households: list[Household],
    events: list[dict[str, Any]],
) -> None:
    people_by_id = {person.id: person for person in people}
    active_infant_mothers = {
        event["person_id"]
        for event in events
        if event.get("outcome") == "live_birth"
    }
    candidates: list[Person] = []
    for household in households:
        women = [
            people_by_id[person_id]
            for person_id in household.member_ids
            if people_by_id[person_id].sex == "female"
            and 18 <= people_by_id[person_id].age_years <= 40
            and people_by_id[person_id].id not in active_infant_mothers
        ]
        if women:
            candidates.append(women[0])
    rng.shuffle(candidates)
    for mother in candidates[:30]:
        events.append(
            {
                "person_id": mother.id,
                "outcome": "ongoing",
                "due_in_days": rng.randint(20, 120),
            }
        )


def _life_stage(age: int) -> str:
    if age < 1:
        return "infant"
    if age <= 4:
        return "toddler"
    if age <= 12:
        return "child"
    if age <= 17:
        return "adolescent"
    if age <= 64:
        return "adult"
    return "elder"


def _stable_fraction(value: float, threshold: float) -> int:
    return 1 if value < threshold else 0


def _population_fingerprint(state: PopulationState) -> str:
    payload = {
        "target_total": state.target_total,
        "seed": state.seed,
        "people": [asdict(person) for person in state.people],
        "households": [
            {
                "id": household.id,
                "member_ids": household.member_ids,
                "relation_notes": household.relation_notes,
            }
            for household in state.households
        ],
        "kinship_edges": state.kinship_edges,
        "pregnancy_events": state.pregnancy_events,
        "lactation_links": state.lactation_links,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
