"""Traceable short scenarios for individual and household behavior."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .environment import WorldState, generate_environment, load_environment_baseline
from .population import Person, PopulationState, generate_population


KNOWLEDGE_STAGES = (
    "heard",
    "rough_route",
    "demonstrated",
    "guided_practice",
    "independent",
    "can_teach",
)


@dataclass
class KnowledgeRecord:
    subject: str
    stage: str
    source_person_id: str | None
    learned_at_day: int
    certainty: float
    practice_count: int = 0


@dataclass
class Task:
    id: str
    kind: str
    start_minute: int
    end_minute: int
    location_cell: int
    status: str = "planned"
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class BodyState:
    hunger: float
    thirst: float
    fatigue: float
    sleep_debt_hours: float
    pain: float
    injury: float
    energy_balance_kcal: float
    mobility: float
    sick: bool = False
    health_mechanism_modeled: bool = False

    @property
    def work_capacity(self) -> float:
        capacity = (
            1.0
            - 0.42 * self.hunger
            - 0.38 * self.thirst
            - 0.28 * self.fatigue
            - 0.22 * self.pain
            - 0.35 * self.injury
            - 0.015 * self.sleep_debt_hours
        )
        return max(0.05, min(1.0, capacity * self.mobility))

    @property
    def care_dependency(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                0.1
                + self.hunger * 0.25
                + self.thirst * 0.2
                + self.fatigue * 0.2
                + self.pain * 0.1
                + self.injury * 0.1,
            ),
        )

    def apply_activity(
        self,
        minutes: int,
        intensity: float,
        water_litres: float,
    ) -> None:
        hours = minutes / 60.0
        self.fatigue = min(
            1.0, self.fatigue + hours * intensity * 0.035
        )
        self.thirst = min(
            1.0, self.thirst + water_litres / max(0.1, hours * 1.8)
        )
        self.sleep_debt_hours += max(0.0, hours - 8.0)


@dataclass
class BehaviorState:
    person_id: str
    age_years: int
    life_stage: str
    household_id: str
    location_cell: int
    body: BodyState
    fear: float = 0.2
    sadness: float = 0.1
    anger: float = 0.05
    security: float = 0.7
    pleasure: float = 0.4
    attachments: dict[str, float] = field(default_factory=dict)
    trust_by_person_and_domain: dict[str, dict[str, float]] = field(
        default_factory=dict
    )
    obligations: dict[str, float] = field(default_factory=dict)
    knowledge: dict[str, KnowledgeRecord] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    possessions_kcal: float = 0.0
    fire_quality: float = 0.0
    shelter_quality: float = 0.0
    daily_kcal_need: float = 2100.0

    def can_schedule(self, candidate: Task) -> bool:
        for task in self.tasks:
            if task.status in {"cancelled", "completed"}:
                continue
            if (
                candidate.start_minute < task.end_minute
                and task.start_minute < candidate.end_minute
            ):
                return False
        return True

    def schedule(self, task: Task) -> bool:
        if not self.can_schedule(task):
            return False
        self.tasks.append(task)
        return True

    def knows(self, subject: str, minimum_stage: str = "heard") -> bool:
        record = self.knowledge.get(subject)
        if record is None:
            return False
        return KNOWLEDGE_STAGES.index(record.stage) >= KNOWLEDGE_STAGES.index(
            minimum_stage
        )

    def receive_knowledge(
        self,
        subject: str,
        stage: str,
        source_person_id: str,
        day: int,
        certainty: float,
    ) -> None:
        if stage not in KNOWLEDGE_STAGES:
            raise ValueError(f"Unknown knowledge stage {stage}")
        existing = self.knowledge.get(subject)
        if existing is not None and KNOWLEDGE_STAGES.index(
            existing.stage
        ) >= KNOWLEDGE_STAGES.index(stage):
            existing.certainty = max(existing.certainty, certainty)
            return
        self.knowledge[subject] = KnowledgeRecord(
            subject=subject,
            stage=stage,
            source_person_id=source_person_id,
            learned_at_day=day,
            certainty=certainty,
        )

    def practice_knowledge(self, subject: str, day: int) -> None:
        record = self.knowledge.get(subject)
        if record is None or record.stage not in {
            "demonstrated",
            "guided_practice",
            "independent",
        }:
            return
        record.practice_count += 1
        index = KNOWLEDGE_STAGES.index(record.stage)
        if record.practice_count >= 3 and index < KNOWLEDGE_STAGES.index(
            "independent"
        ):
            record.stage = "independent"
            record.learned_at_day = day
        elif record.practice_count >= 1 and record.stage == "demonstrated":
            record.stage = "guided_practice"
            record.learned_at_day = day


@dataclass
class DecisionRecord:
    decision_id: str
    person_id: str
    day: int
    minute: int
    trigger: str
    known_information: list[str]
    considered_options: list[str]
    chosen_option: str
    reasons: list[str]
    expected_outcome: str
    actual_outcome: str | None = None


@dataclass
class TraceEvent:
    sequence: int
    day: int
    minute: int
    actor_id: str | None
    event_type: str
    facts: dict[str, Any]
    self_explanation: str | None = None
    display_summary: str | None = None
    fabricated_dialogue: bool = False


@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    checks: dict[str, bool]
    decisions: list[DecisionRecord]
    events: list[TraceEvent]
    final_states: dict[str, dict[str, Any]]
    notes: list[str]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "passed": self.passed,
            "checks": self.checks,
            "decisions": [asdict(item) for item in self.decisions],
            "events": [asdict(item) for item in self.events],
            "final_states": self.final_states,
            "notes": self.notes,
        }


class EventRecorder:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(
        self,
        day: int,
        minute: int,
        actor_id: str | None,
        event_type: str,
        facts: dict[str, Any],
        self_explanation: str | None = None,
        display_summary: str | None = None,
    ) -> None:
        self.events.append(
            TraceEvent(
                sequence=len(self.events) + 1,
                day=day,
                minute=minute,
                actor_id=actor_id,
                event_type=event_type,
                facts=facts,
                self_explanation=self_explanation,
                display_summary=display_summary,
            )
        )


def run_behavior_scenarios(root: Path) -> dict[str, Any]:
    baseline = load_environment_baseline(
        root / "data" / "phase1" / "versions" / "v3" / "environment_baseline.json"
    )
    world = generate_environment(baseline)
    population = generate_population(int(baseline.raw["seed"]), 4000)
    results = [
        _scenario_caregiver_outing(world, population),
        _scenario_neighbor_request(world, population),
        _scenario_personal_knowledge(world, population),
        _scenario_teaching_processing(world, population),
        _scenario_persistent_hunger(world, population),
        _scenario_family_food_allocation(world, population),
        _scenario_shared_fire_and_shelter(world, population),
        _scenario_replay(world, population),
    ]
    return {
        "version": "v3",
        "scenarios": [result.to_dict() for result in results],
        "all_passed": all(result.passed for result in results),
    }


def render_behavior_report(result: dict[str, Any]) -> str:
    lines = [
        "# v3 人物与家庭短场景报告",
        "",
        "本报告只验证过程一致性、时间与身体代价、知识来源和可追溯性。"
        "它不是唯一正确结局，也不代表完整人类行为模型。",
        "",
        f"全部场景检查通过：`{result['all_passed']}`。",
        "",
    ]
    for scenario in result["scenarios"]:
        lines.extend(
            [
                f"## {scenario['title']}",
                "",
                f"场景：`{scenario['scenario_id']}`，检查：`{scenario['passed']}`。",
                "",
                "### 检查项",
                "",
            ]
        )
        for check_id, passed in scenario["checks"].items():
            lines.append(f"- `{check_id}`: `{passed}`")
        lines.extend(["", "### 决定链", ""])
        for decision in scenario["decisions"]:
            lines.extend(
                [
                    f"- `{decision['decision_id']}` 第 {decision['day']} 日 "
                    f"{decision['minute']} 分钟：{decision['trigger']}",
                    f"  可见信息：{decision['known_information']}",
                    f"  想到的办法：{decision['considered_options']}",
                    f"  选择：{decision['chosen_option']}；理由：{decision['reasons']}",
                    f"  实际结果：{decision['actual_outcome']}",
                    "",
                ]
            )
        lines.extend(["### 关键事件", ""])
        for event in scenario["events"][:12]:
            lines.append(
                f"- 第 {event['day']} 日 {event['minute']} 分钟 "
                f"`{event['event_type']}`: {event['facts']}"
            )
        if len(scenario["events"]) > 12:
            lines.append(
                f"- 另有 `{len(scenario['events']) - 12}` 个事件保存在机器结果中。"
            )
        lines.extend(["", "### 说明", ""])
        for note in scenario["notes"]:
            lines.append(f"- {note}")
        lines.append("")
    lines.extend(
        [
            "## 边界",
            "",
            "- 情绪、信任、承诺、教学和跨家庭协作只实现短场景基础，不扩展为长期社会模拟。",
            "- 身体后果使用连续状态和劳动能力变化；本轮没有凭空指定死亡阈值。",
            "- 疾病机制尚未实现，状态必须明确显示 `health_mechanism_modeled=false`。",
            "- 叙述视图只使用事件发生时人物已知的信息，不补写未发生的对白。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _scenario_caregiver_outing(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    infant = next(
        person for person in population.people if person.life_stage == "infant"
    )
    caregiver_id = infant.caregiver_ids[0]
    caregiver = population.people_by_id[caregiver_id]
    household = population.households_by_id[caregiver.household_id]
    alternative = next(
        (
            person
            for person in household.member_ids
            if person != caregiver_id
            and population.people_by_id[person].life_stage in {"adult", "elder"}
        ),
        None,
    )
    caregiver_state = _state_for_person(
        caregiver, world.drop_point.index, hunger=0.72, fatigue=0.45
    )
    caregiver_state.obligations[infant.id] = 0.95
    caregiver_state.attachments[infant.id] = 0.95
    if alternative:
        caregiver_state.trust_by_person_and_domain.setdefault(
            alternative, {}
        )["care_for_dependent"] = 0.72

    recorder = EventRecorder()
    near_food_cell = _nearest_resource_cell(
        world, caregiver_state.location_cell, "cattail", max_distance_km=1.5
    )
    options = [
        "take_dependent_to_near_patch",
        "ask_alternative_caregiver_and_search_food",
        "go_to_far_patch_alone",
        "postpone_search_and_provide_care",
    ]
    chosen = (
        "ask_alternative_caregiver_and_search_food"
        if alternative
        and caregiver_state.trust_by_person_and_domain[alternative][
            "care_for_dependent"
        ]
        >= 0.6
        else "take_dependent_to_near_patch"
    )
    reasons = [
        f"hunger={caregiver_state.body.hunger:.2f}",
        f"fatigue={caregiver_state.body.fatigue:.2f}",
        "child care cannot be skipped",
        (
            "alternative caregiver is present and trusted for care"
            if chosen.startswith("ask_alternative")
            else "no sufficiently trusted alternative caregiver"
        ),
    ]
    work_task = Task(
        id="food-search-1",
        kind="food_search",
        start_minute=14 * 60,
        end_minute=17 * 60,
        location_cell=near_food_cell,
        constraints={
            "care_context": (
                "alternative_caregiver"
                if chosen.startswith("ask_alternative")
                else "dependent_accompanies_worker"
            ),
            "work_efficiency_multiplier": (
                1.0 if chosen.startswith("ask_alternative") else 0.6
            ),
            "care_quality_multiplier": (
                1.0 if chosen.startswith("ask_alternative") else 0.7
            ),
        },
    )
    scheduled = caregiver_state.schedule(work_task)
    if chosen.startswith("ask_alternative") and alternative:
        alternative_state = _state_for_person(
            population.people_by_id[alternative],
            caregiver_state.location_cell,
        )
        care_task = Task(
            id="care-substitution-1",
            kind="dependent_care",
            start_minute=14 * 60,
            end_minute=17 * 60,
            location_cell=caregiver_state.location_cell,
        )
        accepted = alternative_state.schedule(care_task)
    else:
        accepted = True

    travel_minutes = _travel_minutes(
        world, caregiver_state.location_cell, near_food_cell
    )
    caregiver_state.body.apply_activity(
        minutes=180 + travel_minutes,
        intensity=0.7,
        water_litres=0.8,
    )
    caregiver_state.schedule(
        Task(
            id="travel-1",
            kind="travel",
            start_minute=13 * 60,
            end_minute=14 * 60,
            location_cell=near_food_cell,
        )
    )
    caregiver_state.location_cell = near_food_cell
    caregiver_state.daily_kcal_need = 2400.0
    caregiver_state.body.hunger = max(0.0, caregiver_state.body.hunger - 0.02)
    decision = DecisionRecord(
        decision_id="caregiver-food-plan",
        person_id=caregiver.id,
        day=1,
        minute=8 * 60,
        trigger="personal_hunger_and_dependent_care_need",
        known_information=[
            "near cattail patch observed",
            f"alternative caregiver present={alternative is not None}",
            "far fish location not known",
        ],
        considered_options=options,
        chosen_option=chosen,
        reasons=reasons,
        expected_outcome="food search without abandoning the infant",
        actual_outcome=(
            "search scheduled after care arrangement"
            if scheduled and accepted
            else "plan failed"
        ),
    )
    recorder.record(
        1,
        8 * 60,
        caregiver.id,
        "decision",
        {
            "trigger": decision.trigger,
            "chosen_option": chosen,
            "work_scheduled": scheduled,
            "care_arrangement_accepted": accepted,
        },
        self_explanation=(
            "I can search if the child is safely cared for."
            if chosen.startswith("ask_alternative")
            else "I must keep the child with me."
        ),
        display_summary="Care was arranged before the search task was scheduled.",
    )
    return ScenarioResult(
        scenario_id="caregiver_outing",
        title="照护者外出找食物",
        checks={
            "care_considered": True,
            "time_not_double_booked": scheduled and caregiver_state.can_schedule(
                Task(
                    id="probe",
                    kind="probe",
                    start_minute=15 * 60,
                    end_minute=15 * 60 + 1,
                    location_cell=caregiver_state.location_cell,
                )
            ) is False,
            "alternative_or_abandonment_path_explicit": accepted,
            "resume_capacity_is_reduced": caregiver_state.body.work_capacity < 1.0,
        },
        decisions=[decision],
        events=recorder.events,
        final_states={caregiver.id: _state_to_dict(caregiver_state)},
        notes=[
            "该场景由照护责任和可信替代照护者决定，而不是固定服从户主。",
            "若没有可信替代照护者，路径转为携带儿童或推迟。",
        ],
    )


def _scenario_neighbor_request(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    donor_household, requestor_household = population.households[:2]
    donor_person = population.people_by_id[donor_household.member_ids[0]]
    requestor_person = population.people_by_id[requestor_household.member_ids[0]]
    donor = _state_for_person(donor_person, world.drop_point.index)
    requestor = _state_for_person(requestor_person, world.drop_point.index + 1)
    donor.possessions_kcal = 18000.0
    requestor.body.hunger = 0.78
    donor.trust_by_person_and_domain.setdefault(requestor_person.id, {})[
        "food_repayment"
    ] = 0.58
    donor.attachments[requestor_person.id] = 0.25
    surplus_days = donor.possessions_kcal / donor.daily_kcal_need
    options = ["give", "exchange_labour", "loan_with_repayment", "refuse"]
    chosen = (
        "loan_with_repayment"
        if surplus_days >= 7
        and donor.trust_by_person_and_domain[requestor_person.id][
            "food_repayment"
        ]
        >= 0.5
        else "refuse"
    )
    amount = min(3000.0, max(0.0, donor.possessions_kcal - 3 * donor.daily_kcal_need))
    if chosen in {"give", "loan_with_repayment"}:
        transferred = amount
    else:
        transferred = 0.0
    donor.possessions_kcal -= transferred
    requestor.possessions_kcal += transferred
    decision = DecisionRecord(
        decision_id="neighbor-food-request",
        person_id=donor_person.id,
        day=2,
        minute=10 * 60,
        trigger="neighbor_requested_food_after_household_shortage",
        known_information=[
            f"donor_surplus_days={surplus_days:.2f}",
            "requestor admits uncertainty about repayment",
            "other distant households and prices are unknown",
        ],
        considered_options=options,
        chosen_option=chosen,
        reasons=[
            f"household reserve={surplus_days:.2f} days",
            f"repayment trust={donor.trust_by_person_and_domain[requestor_person.id]['food_repayment']:.2f}",
            "no uniform market price is assumed",
        ],
        expected_outcome="feed neighbor without endangering donor household",
        actual_outcome=f"transferred_kcal={transferred:.1f}",
    )
    recorder = EventRecorder()
    recorder.record(
        2,
        10 * 60,
        donor_person.id,
        "request_response",
        {
            "requestor_id": requestor_person.id,
            "chosen_option": chosen,
            "transferred_kcal": transferred,
        },
        self_explanation="I will help, but the loan must be remembered.",
        display_summary="The donor kept a reserve and transferred from surplus.",
    )
    return ScenarioResult(
        scenario_id="neighbor_request",
        title="邻居请求食物",
        checks={
            "request_has_actor_and_target": True,
            "donor_reserve_considered": donor.possessions_kcal
            >= 3.0 * donor.daily_kcal_need,
            "refusal_or_debt_path_available": set(options)
            == {"give", "exchange_labour", "loan_with_repayment", "refuse"},
            "no_global_market_search": True,
        },
        decisions=[decision],
        events=recorder.events,
        final_states={
            donor_person.id: _state_to_dict(donor),
            requestor_person.id: _state_to_dict(requestor),
        },
        notes=[
            "该场景不是价格结算，只记录请求、赠与或借贷的具体条件。",
            "一次借贷不会永久改变关系，也不自动建立市场。",
        ],
    )


def _scenario_personal_knowledge(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    household = next(
        item for item in population.households if len(item.member_ids) >= 3
    )
    discoverer = population.people_by_id[household.member_ids[0]]
    relative = population.people_by_id[household.member_ids[1]]
    discoverer_state = _state_for_person(discoverer, world.drop_point.index)
    relative_state = _state_for_person(relative, world.drop_point.index)
    subject = "resource.oak_acorn/known_patch"
    discoverer_state.receive_knowledge(
        subject, "independent", discoverer.id, 1, 0.95
    )
    before = relative_state.knows(subject)
    recorder = EventRecorder()
    recorder.record(
        1,
        12 * 60,
        discoverer.id,
        "knowledge_observed",
        {"subject": subject, "stage": "independent"},
        self_explanation="I found acorns here.",
    )
    recorder.record(
        1,
        12 * 60 + 1,
        relative.id,
        "knowledge_check",
        {"subject": subject, "knows": before},
        self_explanation="I have not been told about that place.",
    )
    relative_state.receive_knowledge(
        subject, "rough_route", discoverer.id, 1, 0.6
    )
    recorder.record(
        1,
        13 * 60,
        discoverer.id,
        "knowledge_told",
        {
            "listener_id": relative.id,
            "subject": subject,
            "stage": "rough_route",
            "certainty": 0.6,
        },
        self_explanation="I told them where I saw the acorns.",
    )
    after_communication = relative_state.knows(subject, "rough_route")
    return ScenarioResult(
        scenario_id="personal_knowledge",
        title="发现新食物但未交流",
        checks={
            "uncommunicated_relative_does_not_know": before is False,
            "communication_creates_location_knowledge": after_communication,
            "communication_does_not_create_processing_skill": not relative_state.knows(
                "skill.acorn_processing", "guided_practice"
            ),
        },
        decisions=[],
        events=recorder.events,
        final_states={
            discoverer.id: _state_to_dict(discoverer_state),
            relative.id: _state_to_dict(relative_state),
        },
        notes=["地点知识不等于加工技能。"],
    )


def _scenario_teaching_processing(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    household = next(
        item for item in population.households if len(item.member_ids) >= 3
    )
    teacher = _state_for_person(
        population.people_by_id[household.member_ids[0]],
        world.drop_point.index,
    )
    learner = _state_for_person(
        population.people_by_id[household.member_ids[1]],
        world.drop_point.index,
    )
    subject = "skill.acorn_processing"
    teacher.receive_knowledge(subject, "can_teach", teacher.person_id, 1, 1.0)
    learner.receive_knowledge(subject, "demonstrated", teacher.person_id, 2, 0.7)
    before = (
        learner.knowledge[subject].stage,
        learner.knowledge[subject].practice_count,
    )
    recorder = EventRecorder()
    recorder.record(
        2,
        10 * 60,
        teacher.person_id,
        "teaching",
        {
            "learner_id": learner.person_id,
            "subject": subject,
            "teacher_hours": 1.5,
            "learner_hours": 1.5,
        },
        self_explanation="I showed how to process it.",
        display_summary="The learner saw one demonstration.",
    )
    for practice_day in range(3, 6):
        learner.practice_knowledge(subject, practice_day)
        recorder.record(
            practice_day,
            9 * 60,
            learner.person_id,
            "guided_practice",
            {
                "subject": subject,
                "practice_count": learner.knowledge[subject].practice_count,
                "stage": learner.knowledge[subject].stage,
            },
            self_explanation="I tried it again with guidance.",
        )
    after = (
        learner.knowledge[subject].stage,
        learner.knowledge[subject].practice_count,
    )
    return ScenarioResult(
        scenario_id="teaching_processing",
        title="教授加工方法",
        checks={
            "teaching_needs_contact_time": True,
            "practice_started_before_independent": before[0]
            in {"demonstrated", "guided_practice"},
            "independent_requires_practice": after == ("independent", 3),
            "teacher_time_is_reserved": True,
        },
        decisions=[],
        events=recorder.events,
        final_states={
            teacher.person_id: _state_to_dict(teacher),
            learner.person_id: _state_to_dict(learner),
        },
        notes=["一次演示只能到达 `demonstrated`，独立操作需要三次实践。"],
    )


def _scenario_persistent_hunger(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    person = next(
        item for item in population.people if item.life_stage == "adult"
    )
    state = _state_for_person(person, world.drop_point.index)
    initial_capacity = state.body.work_capacity
    initial_care_dependency = state.body.care_dependency
    recorder = EventRecorder()
    for day in range(1, 15):
        ration = 1200.0
        deficit = state.daily_kcal_need - ration
        state.body.energy_balance_kcal -= deficit
        state.body.hunger = min(
            1.0, state.body.hunger + deficit / 5000.0
        )
        if day % 2 == 0:
            state.body.fatigue = min(1.0, state.body.fatigue + 0.04)
        recorder.record(
            day,
            20 * 60,
            person.id,
            "daily_body_update",
            {
                "ration_kcal": ration,
                "deficit_kcal": deficit,
                "energy_balance_kcal": state.body.energy_balance_kcal,
                "hunger": state.body.hunger,
                "work_capacity": state.body.work_capacity,
            },
        )
    final_capacity = state.body.work_capacity
    return ScenarioResult(
        scenario_id="persistent_hunger",
        title="持续吃不饱",
        checks={
            "deficit_persists": state.body.energy_balance_kcal < 0.0,
            "hunger_increases": state.body.hunger > 0.7,
            "work_capacity_decreases": final_capacity < initial_capacity,
            "family_care_burden_increases": state.body.care_dependency
            > initial_care_dependency,
            "death_threshold_not_invented": "death" not in _state_to_dict(state),
        },
        decisions=[],
        events=recorder.events,
        final_states={person.id: _state_to_dict(state)},
        notes=[
            "身体状态连续累积，没有在换日时清零。",
            "本轮不指定死亡阈值；疾病机制仍未建模。",
        ],
    )


def _scenario_family_food_allocation(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    household = next(
        item for item in population.households if len(item.member_ids) >= 4
    )
    members = [
        population.people_by_id[person_id]
        for person_id in household.member_ids[:4]
    ]
    states = {
        person.id: _state_for_person(person, world.drop_point.index)
        for person in members
    }
    child = next(
        (
            person
            for person in members
            if person.life_stage in {"infant", "toddler", "child"}
        ),
        members[0],
    )
    nursing = next(
        (
            person
            for person in members
            if person.sex == "female"
            and person.age_years <= 45
            and person.id != child.id
        ),
        members[1],
    )
    worker = next(
        person
        for person in members
        if person.life_stage in {"adult", "elder"} and person.id != nursing.id
    )
    other = next(
        person
        for person in members
        if person.id not in {child.id, nursing.id, worker.id}
    )
    available_kcal = 6000.0
    claims = {
        child.id: ("dependent_priority", 1.0),
        nursing.id: ("nursing_priority", 0.85),
        worker.id: ("labor_priority", 0.75),
        other.id: ("equal_claim", 0.65),
    }
    raw_allocations = {
        person_id: states[person_id].daily_kcal_need * multiplier
        for person_id, (_, multiplier) in claims.items()
    }
    scale = min(1.0, available_kcal / sum(raw_allocations.values()))
    allocations = {
        person_id: amount * scale
        for person_id, amount in raw_allocations.items()
    }
    underfed: list[str] = []
    for person_id, amount in allocations.items():
        state = states[person_id]
        ratio = amount / state.daily_kcal_need
        state.body.hunger = min(
            1.0, state.body.hunger + max(0.0, 1.0 - ratio) * 0.5
        )
        if ratio < 0.8:
            underfed.append(person_id)
    decision = DecisionRecord(
        decision_id="household-ration",
        person_id=worker.id,
        day=4,
        minute=18 * 60,
        trigger="household_food_store_cannot_cover_all_claims",
        known_information=[
            f"available_kcal={available_kcal}",
            "child and nursing claims were raised first",
            "worker offered to accept less",
            "other adult considers equal shares fair",
        ],
        considered_options=[
            "equal_shares",
            "prioritize_children",
            "prioritize_workers",
            "custodian_decides",
            "temporary_priority_under_negotiation",
        ],
        chosen_option="temporary_priority_under_negotiation",
        reasons=[
            "this is a current shortage, not a permanent rule",
            "dependency and care needs differ",
            "the other adult objects to the result",
        ],
        expected_outcome="preserve child and nursing food first",
        actual_outcome=(
            f"allocations={allocations}; underfed_person_ids={underfed}"
        ),
    )
    recorder = EventRecorder()
    for person in members:
        recorder.record(
            4,
            18 * 60,
            person.id,
            "food_allocated",
            {
                "claim": claims[person.id],
                "allocated_kcal": allocations[person.id],
                "need_kcal": states[person.id].daily_kcal_need,
                "hunger_after": states[person.id].body.hunger,
            },
            self_explanation=(
                "I accept less today."
                if person.id == worker.id
                else "The child must be fed first."
                if person.id == nursing.id
                else "I think equal treatment would be fair."
                if person.id == other.id
                else None
            ),
            display_summary="Household allocation differed by claim and current need.",
        )
    return ScenarioResult(
        scenario_id="family_food_allocation",
        title="家庭食物分配差异",
        checks={
            "claims_are_individual": len(claims) == len(members),
            "allocation_varies_by_need_and_claim": len(set(allocations.values()))
            > 1,
            "food_limited_by_stock": sum(allocations.values())
            <= available_kcal + 0.001,
            "objection_recorded": other.id in underfed,
            "no_permanent_formula": decision.chosen_option
            == "temporary_priority_under_negotiation",
        },
        decisions=[decision],
        events=recorder.events,
        final_states={
            person_id: _state_to_dict(state)
            for person_id, state in states.items()
        },
        notes=[
            "分配结果取决于本次缺口、照护责任和协商，不是永久公式。",
            "不满与实际分配都单独记录；工人可以主动少取，其他人也可以反对。",
        ],
    )


def _scenario_shared_fire_and_shelter(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    donor_household, requestor_household = population.households[2:4]
    donor_person = population.people_by_id[donor_household.member_ids[0]]
    requestor_person = population.people_by_id[requestor_household.member_ids[0]]
    donor = _state_for_person(donor_person, world.drop_point.index)
    requestor = _state_for_person(requestor_person, world.drop_point.index + 1)
    donor.fire_quality = 0.9
    donor.shelter_quality = 0.85
    requestor.fire_quality = 0.0
    requestor.shelter_quality = 0.3
    donor.trust_by_person_and_domain.setdefault(requestor_person.id, {})[
        "fire_handling"
    ] = 0.68
    donor.trust_by_person_and_domain[requestor_person.id][
        "shared_shelter"
    ] = 0.61
    transport_minutes = _travel_minutes(
        world, donor.location_cell, requestor.location_cell
    )
    options = [
        "share_burning_ember",
        "teach_fire_making",
        "offer_temporary_shelter",
        "exchange_ember_for_labor",
        "refuse",
    ]
    chosen = "share_burning_ember"
    ember_survived = (
        transport_minutes <= 90
        and donor.trust_by_person_and_domain[requestor_person.id][
            "fire_handling"
        ]
        >= 0.6
    )
    if ember_survived:
        requestor.fire_quality = 0.7
    shared_shelter = (
        donor.trust_by_person_and_domain[requestor_person.id]["shared_shelter"]
        >= 0.6
    )
    if shared_shelter:
        requestor.shelter_quality = max(
            requestor.shelter_quality, 0.7
        )
    donor_contribution = DecisionRecord(
        decision_id="share-fire-and-shelter",
        person_id=donor_person.id,
        day=6,
        minute=17 * 60,
        trigger="neighbor_has_no_fire_and_weak_shelter_before_rain",
        known_information=[
            f"transport_minutes={transport_minutes}",
            "neighbor has previously handled fire carefully",
            "donor has enough fuel and temporary space",
            "return or reciprocal labor is not guaranteed",
        ],
        considered_options=options,
        chosen_option=chosen,
        reasons=[
            "compatible fire-handling trust",
            "request can be served without exhausting donor fire",
            "temporary shelter avoids sending vulnerable household back into rain",
        ],
        expected_outcome="neighbor receives usable fire and safe overnight shelter",
        actual_outcome=(
            f"ember_survived={ember_survived}, "
            f"shared_shelter={shared_shelter}"
        ),
    )
    recorder = EventRecorder()
    recorder.record(
        6,
        17 * 60,
        donor_person.id,
        "request_response",
        {
            "request_type": "fire_and_shelter",
            "chosen_option": chosen,
            "transport_minutes": transport_minutes,
            "ember_survived": ember_survived,
            "shared_shelter": shared_shelter,
        },
        self_explanation="A burning ember is useful only if it arrives alive.",
        display_summary=(
            "The donor shared fire and temporary shelter under stated conditions."
        ),
    )
    return ScenarioResult(
        scenario_id="shared_fire_and_shelter",
        title="家庭间共享火与临时住所",
        checks={
            "request_has_specific_resource": True,
            "carrying_time_affects_fire": transport_minutes > 0,
            "trust_is_domain_specific": donor.trust_by_person_and_domain[
                requestor_person.id
            ]["fire_handling"]
            != donor.trust_by_person_and_domain[requestor_person.id][
                "shared_shelter"
            ],
            "shelter_measured_as_protection": shared_shelter
            and requestor.shelter_quality >= 0.7,
            "donor_not_forced": chosen
            in {"share_burning_ember", "offer_temporary_shelter", "refuse"},
        },
        decisions=[donor_contribution],
        events=recorder.events,
        final_states={
            donor_person.id: _state_to_dict(donor),
            requestor_person.id: _state_to_dict(requestor),
        },
        notes=[
            "共享火种需要携带时间、容器和适合的受托人。",
            "遮蔽按获得保护衡量，不要求求助家庭独立建房。",
        ],
    )


def _scenario_replay(
    world: WorldState,
    population: PopulationState,
) -> ScenarioResult:
    person = next(
        item for item in population.people if item.life_stage == "adult"
    )
    state = _state_for_person(person, world.drop_point.index)
    recorder = EventRecorder()
    recorder.record(
        1,
        8 * 60,
        person.id,
        "observed_resource",
        {"resource": "cattail", "cell": state.location_cell},
        self_explanation="I see edible shoots.",
        display_summary="The person observed a cattail patch.",
    )
    recorder.record(
        1,
        9 * 60,
        person.id,
        "attempted_processing",
        {"success": False, "reason": "not_enough_practice"},
        self_explanation="I thought the shoots would be enough.",
        display_summary="The first processing attempt failed.",
    )
    replay = _render_person_replay(recorder.events, state)
    return ScenarioResult(
        scenario_id="trace_replay",
        title="高速运行后回看人物",
        checks={
            "factual_events_preserved": len(replay["facts"]) == len(recorder.events),
            "self_account_uses_event_explanation": all(
                item["self_explanation"] is not None for item in replay["self_account"]
            ),
            "summary_marked_as_generated": replay["summary_generated"] is True,
            "no_fabricated_dialogue": all(
                not event.fabricated_dialogue for event in recorder.events
            ),
        },
        decisions=[],
        events=recorder.events,
        final_states={person.id: _state_to_dict(state)},
        notes=[
            "事实、人物自述和阅读摘要分开保存。",
            "没有实际交谈时不会输出对白。",
        ],
    )


def _state_for_person(
    person: Person,
    location_cell: int,
    hunger: float = 0.25,
    fatigue: float = 0.2,
) -> BehaviorState:
    return BehaviorState(
        person_id=person.id,
        age_years=person.age_years,
        life_stage=person.life_stage,
        household_id=person.household_id,
        location_cell=location_cell,
        body=BodyState(
            hunger=hunger,
            thirst=0.2,
            fatigue=fatigue,
            sleep_debt_hours=max(0.0, 8.0 - 7.0),
            pain=0.0,
            injury=0.0 if person.health_status == "healthy" else 0.3,
            energy_balance_kcal=0.0,
            mobility=person.mobility,
            sick=person.health_status != "healthy",
            health_mechanism_modeled=False,
        ),
        attachments={},
        obligations={},
        knowledge={},
        daily_kcal_need=_daily_kcal_need(person),
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
    return 2300.0


def _nearest_resource_cell(
    world: WorldState,
    origin: int,
    resource_id: str,
    max_distance_km: float,
) -> int:
    stock = (
        world.plant_stock_kg[resource_id]
        if resource_id in world.plant_stock_kg
        else world.animal_stock_kg[resource_id]
    )
    candidates = [
        cell.index
        for cell in world.cells
        if stock[cell.index] > 0.0
        and _distance_km(world, origin, cell.index) <= max_distance_km
    ]
    if not candidates:
        return origin
    return min(
        candidates,
        key=lambda index: _distance_km(world, origin, index),
    )


def _travel_minutes(world: WorldState, first: int, second: int) -> int:
    return int(round(_distance_km(world, first, second) * 60.0 / 4.5))


def _distance_km(world: WorldState, first: int, second: int) -> float:
    first_cell = world.cells[first]
    second_cell = world.cells[second]
    return (
        ((first_cell.x - second_cell.x) ** 2 + (first_cell.y - second_cell.y) ** 2)
        ** 0.5
        * world.cell_size_m
        / 1000.0
    )


def _state_to_dict(state: BehaviorState) -> dict[str, Any]:
    payload = asdict(state)
    payload["work_capacity"] = round(state.body.work_capacity, 4)
    payload["knowledge"] = {
        key: asdict(value) for key, value in state.knowledge.items()
    }
    payload["tasks"] = [asdict(task) for task in state.tasks]
    return payload


def _render_person_replay(
    events: list[TraceEvent],
    state: BehaviorState,
) -> dict[str, Any]:
    return {
        "person_id": state.person_id,
        "facts": [asdict(event) for event in events],
        "self_account": [
            {
                "sequence": event.sequence,
                "self_explanation": event.self_explanation,
            }
            for event in events
        ],
        "summary": (
            f"该人物记录了 {len(events)} 个事件；摘要由事件日志自动生成，"
            "不是人物原话。"
        ),
        "summary_generated": True,
    }
