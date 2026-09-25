"""Seven-day integrated diagnostic using the full 4000-person world."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .behavior import BehaviorState, BodyState, _state_for_person
from .environment import generate_environment, load_environment_baseline
from .population import generate_population
from .survival import run_survival_validation


def run_seven_day_integration(root: Path) -> dict[str, Any]:
    baseline = load_environment_baseline(
        root / "data" / "phase1" / "versions" / "v3" / "environment_baseline.json"
    )
    world = generate_environment(baseline)
    population = generate_population(int(baseline.raw["seed"]), 4000)
    behavior_states = {
        person.id: _state_for_person(person, world.drop_point.index)
        for person in population.people
    }
    _seed_social_state(population, behavior_states)
    run = run_survival_validation(
        world,
        population,
        days=7,
        behavior_states=behavior_states,
        record_household_trace=True,
    )
    fixed_control = run_survival_validation(
        world,
        population,
        days=7,
    )
    integration = run.integration_diagnostics
    if integration.get("daily"):
        population_count = len(population.people)
        integration["first_day_outside_reviewed_range"] = next(
            (
                item["day"]
                for item in integration["daily"]
                if item["mean_work_capacity"] < 0.2
                or item["minimum_work_capacity"] < 0.1
                or item["people_with_hunger_at_cap"] / population_count > 0.1
                or item["people_with_thirst_at_cap"] / population_count > 0.1
            ),
            None,
        )
    return {
        "version": "v3",
        "diagnostic_type": "seven_day_integrated_opening_diagnostic",
        "formal_history": False,
        "long_term_conclusion_allowed": False,
        "days": 7,
        "population": population.summary(),
        "integration": integration,
        "window_results": run.window_results,
        "path_results": run.path_results,
        "time_account_hours": run.acquisition_paths["time_account_hours"],
        "water": {
            key: value
            for key, value in run.acquisition_paths["water"].items()
            if key != "vessel_spec"
        },
        "fire": run.acquisition_paths["fire_attempts"],
        "shelter": run.acquisition_paths["shelter"],
        "care_and_shelter": {
            "dependent_people": sum(
                person.life_stage in {"infant", "toddler", "child"}
                for person in population.people
            ),
            "dependent_people_with_declared_caregiver": sum(
                person.life_stage in {"infant", "toddler", "child"}
                and bool(person.caregiver_ids)
                for person in population.people
            ),
            "care_hours": run.acquisition_paths["time_account_hours"][
                "care"
            ],
            "shelter_completed_households": run.acquisition_paths[
                "shelter"
            ]["households_completed"],
            "shelter_protected_people": run.acquisition_paths["shelter"][
                "people_in_completed_households"
            ],
            "shelter_attempt_hours": run.acquisition_paths[
                "shelter_evidence"
            ]["attempt_hours"],
            "shelter_material_failure_days": run.acquisition_paths[
                "shelter_evidence"
            ]["material_failure_days"],
            "shelter_partial_households": run.acquisition_paths[
                "shelter_evidence"
            ]["households_with_partial_cover"],
            "shelter_partial_people": run.acquisition_paths[
                "shelter_evidence"
            ]["people_with_partial_cover"],
        },
        "food_by_window": run.acquisition_paths["food_by_window"],
        "food_annual": run.acquisition_paths["food"],
        "resource_ledger": run.resource_ledger,
        "daily_metrics": [asdict(metric) for metric in run.metrics],
        "household_daily_records": run.household_daily_records,
        "person_daily_records": run.person_daily_records,
        "personal_time_audit": _personal_time_audit(
            run.person_daily_records, population
        ),
        "water_diagnosis": _water_diagnosis(run.household_daily_records),
        "body_fixed_control": {
            "mode": "fixed_initial_work_capacity_control",
            "daily_metrics": [asdict(metric) for metric in fixed_control.metrics],
            "note": (
                "Diagnostic counterfactual only; it does not represent a "
                "proposed behavior."
            ),
        },
        "social_actions": {
            "interhousehold_food_requests": 0,
            "completed_food_transfers": 0,
            "teaching_events": 0,
            "temporary_cohabitation_events": 0,
            "note": (
                "No cross-household exchange, teaching, or cohabitation was "
                "forced. Zero means the integrated rule set did not trigger them."
            ),
        },
        "social_action_funnel": _social_action_funnel(
            run.household_daily_records
        ),
        "failure_reasons": _failure_reason_summary(
            run.acquisition_paths, run.metrics
        ),
    }


def render_seven_day_integration_report(result: dict[str, Any]) -> str:
    integration = result["integration"]
    failed_days = sum(
        metric["food_ratio"] < 0.8 for metric in result["daily_metrics"]
    )
    water_failed_days = sum(
        metric["water_ratio"] < 0.8 for metric in result["daily_metrics"]
    )
    lines = [
        "# v3 七天开局整合诊断",
        "",
        "这是 4000 人世界副本上的连续 7 天诊断，不是正式历史，也不能证明长期生存能力。",
        "",
        "## 整合口径",
        "",
        "- 行动在每个模拟日由当前身体、照护、资源和已探索信息产生，没有按日期脚本触发事件。",
        "- 身体劳动能力限制当日可用时间；实际摄入和缺水在当天结束后更新身体。",
        "- 食物、水、材料和劳动都从同一个世界副本扣除。",
        "- 没有发生跨家庭交换、教学或同居时记录为零，不为演示功能强制触发。",
        "",
        "## 七天结果",
        "",
        f"- 低于 80% 食物需要的天数：`{failed_days}/7`。",
        f"- 低于 80% 饮水需要的天数：`{water_failed_days}/7`。",
        f"- 但低于 80% 饮水需求的家庭日："
        f"`{result['water_diagnosis']['deficient_household_days']}`；"
        "全体加总不能代替家庭和个体检查。",
        f"- 最低劳动能力：`{integration['minimum_work_capacity']}`。",
        f"- 末日平均劳动能力：`{integration['mean_work_capacity']}`。",
        f"- 人为最低能力下限："
        f"`{integration['minimum_allowed_work_capacity']}`。",
        f"- 饥饿达到模型上限人数：`{integration['people_with_hunger_at_cap']}`。",
        f"- 口渴达到模型上限人数：`{integration['people_with_thirst_at_cap']}`。",
        f"- 最终劳动能力低于 0.5 的人数："
        f"`{integration['people_capacity_limited_on_final_day']}`。",
        f"- 累计能量余额：`{integration['total_energy_balance_kcal']}` kcal。",
        f"- 首次超出本模型可解释范围的日期："
        f"`{integration['first_day_outside_reviewed_range']}`；"
        "此后结果只能用于故障定位。判断条件为最低劳动能力低于 0.1、"
        "平均能力低于 0.2，或超过 10% 人口达到饥饿或口渴上限。",
        "",
        "模型没有死亡阈值；死亡人数显示为零，状态为 `death_modeled=false`。"
        "疾病也未被建模，因此不能解释为没有疾病风险。",
        "- `0.05` 是人为工作能力下限，不是生理死亡阈值。",
        "- 饥饿感与累计能量缺口取较大影响，不与同一代谢因素重复相加。",
        "- 当前能力只减少可用劳动小时，不额外降低每小时产出。",
        "- 末日平均和最低值都是模型指标，不是现实人体测量。",
        "",
        "| 日期 | 平均劳动能力 | 最低劳动能力 | 饥饿上限人数 | 口渴上限人数 |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in integration["daily"]:
        lines.append(
            f"| {item['day']} | {item['mean_work_capacity']} | "
            f"{item['minimum_work_capacity']} | "
            f"{item['people_with_hunger_at_cap']} | "
            f"{item['people_with_thirst_at_cap']} |"
        )
    lines.extend(
        [
            "",
            "## 个人时间使用",
            "",
            "| 类别 | 家庭小时 |",
            "| --- | ---: |",
        ]
    )
    for key, value in result["time_account_hours"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "同一小时只进入一个类别；时间账闭合误差为 "
            f"`{result['time_account_hours']['closure_error_hours']}` 小时。",
            "",
            "## 实际食物摄入",
            "",
            "| 投放后日 | 固定需求 kcal | 实际摄入 kcal | 摄入/需求 | "
            "最低家庭日比例 | 饮水比例 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric in result["daily_metrics"]:
        lines.append(
            f"| {metric['day']} | {metric['food_demand_kcal']} | "
            f"{round(metric['food_demand_kcal'] * metric['food_ratio'], 3)} | "
            f"{metric['food_ratio']} | {metric['food_ratio_household_min']} | "
            f"{metric['water_ratio']} |"
        )
    lines.extend(
        [
            "",
            "摄入量由家庭实际吃下触发，不是分配量或仓库存量。",
            "",
            "## 资源收支",
            "",
            "| 资源 | 期初 kg | 新增 kg | 采集/捕获 kg | 自然损失 kg | "
            "期末 kg | 闭合误差 kg | 非负 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for resource_id, ledger in result["resource_ledger"].items():
        lines.append(
            f"| `{resource_id}` | {ledger['opening_stock_kg']} | "
            f"{ledger['additions_kg']} | {ledger['harvested_kg']} | "
            f"{ledger['natural_loss_kg']} | "
            f"{ledger['closing_stock_kg']} | "
            f"{ledger['closure_error_kg']} | {ledger['non_negative']} |"
        )
    care = result["care_and_shelter"]
    lines.extend(
        [
            "",
            "## 照护与遮蔽覆盖",
            "",
            f"- 依赖人口：`{care['dependent_people']}`。",
            f"- 有明确照护者引用的依赖人口："
            f"`{care['dependent_people_with_declared_caregiver']}`。",
            f"- 七天照护占用：`{care['care_hours']}` 家庭小时。",
            f"- 达到遮蔽保护阈值的家庭："
            f"`{care['shelter_completed_households']}`；覆盖人数："
            f"`{care['shelter_protected_people']}`。",
            f"- 达到部分保护阈值的家庭："
            f"`{care['shelter_partial_households']}`；部分保护人数："
            f"`{care['shelter_partial_people']}`。",
            f"- 遮蔽尝试：`{care['shelter_attempt_hours']}` 家庭小时；"
            f"材料不足：`{care['shelter_material_failure_days']}` 家庭日。",
            "- 未完成遮蔽进度跨日保留，部分结构计入部分保护，不再只显示二元覆盖。",
            "- 同一照护者时间按任务区间扣除，不会同时用于远处采集。",
            "- 遮蔽按实际保护人数和容量报告，不要求每户独立建房。",
            "",
            "## 主要失败原因",
            "",
        ]
    )
    for reason, count in result["failure_reasons"].items():
        lines.append(f"- `{reason}`：`{count}`")
    lines.extend(
        [
            "",
            "## 缺水追踪",
            "",
            f"- 低于 80% 饮水需求的家庭日："
            f"`{result['water_diagnosis']['deficient_household_days']}`；"
            "全体加总日比例可能仍高于 80%，不能用全体平均掩盖部分家庭缺水。",
            f"- 失败原因计数："
            f"`{result['water_diagnosis']['by_failure_cause']}`。",
            "",
            "| 日期 | 家庭 | 水源距离 km | 可行动人数 | 依赖人数 | "
            "取水方式 | 直接容量 L | 交付 L | 水小时 | 迁移小时 | "
            "潜在工时 | 照护工时 | 紧急取水 | 照护可重叠 | 已重叠 | "
            "取水前可用小时 | 满足率 | 失败原因 | 水具受阻原因 |",
            "| ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | --- |",
        ]
    )
    for item in result["water_diagnosis"]["worst_examples"]:
        lines.append(
            f"| {item['day']} | `{item['household_id']}` | "
            f"{item['water_distance_km']} | {item['mobile_people']} | "
            f"{item['dependent_people']} | `{item['water_method']}` | "
            f"{item['direct_capacity_l']} | {item['water_delivered_l']} | "
            f"{item['water_hours']} | {item['migration_hours']} | "
            f"{item['potential_hours']} | {item['care_hours']} | "
            f"{item['water_emergency']} | "
            f"{item['care_overlap_allowance']} | "
            f"{item['care_overlap_used']} | "
            f"{item['hours_before_water']} | "
            f"{item['water_ratio']} | `{item['failure_cause']}` | "
            f"`{item['vessel_blocked_reason']}` |"
        )
    lines.extend(
        [
            "",
            "- 容器不是直接饮水的强制前置条件；无容器时仍走前往水源饮水路径。",
            "- 表中家庭是满足率最低的实际样本，不是脚本指定家庭。",
            "- `no_labour_time_before_fetch` 表示照护和身体能力修正后，取水前可用工时为 0；"
            "不是人物不知道水源。",
            "- `no_mobile_person` 表示家庭中没有能够自行到达水源的人，"
            "但跨家庭请求照护或送水尚未接入统一调度。",
            "- 直接饮水本身不受容器门槛限制；容器只影响返回携带、储水或运输。",
            "",
            "## 个人时间与照护交接",
            "",
            f"- 个人日活动记录：`{result['personal_time_audit']['records']}`。",
            f"- 重叠任务：`{result['personal_time_audit']['overlaps']}`。",
            f"- 超出个人能力上限：`{result['personal_time_audit']['over_capacity']}`。",
            f"- 未记录活动的可劳动人次：`{result['personal_time_audit']['missing_active_person_days']}`。",
            f"- 资格校验失败：`{result['personal_time_audit']['eligibility_violations']}`。",
            f"- 照护记录：`{result['personal_time_audit']['care_records']}`。",
            "- 照护记录使用实际照护者 ID 和时间段；接受未来安排不等于已经完成接手。",
            "- `potential` 指身体修正后的可劳动小时，不是全部清醒时间；"
            "剩余部分进入休息或未使用能力。",
            "- 活动记录目前只到家庭营地位置，尚未保存每个资源格的实际执行位置，"
            "位置精度仍待提高。",
            "",
            "## 动态身体对照",
            "",
            "| 日期 | 动态食物比例 | 固定能力对照食物比例 | 动态饮水比例 | "
            "固定能力对照饮水比例 |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    control_metrics = result["body_fixed_control"]["daily_metrics"]
    food_differences = [
        dynamic["food_ratio"] - fixed["food_ratio"]
        for dynamic, fixed in zip(result["daily_metrics"], control_metrics)
    ]
    for dynamic, fixed in zip(result["daily_metrics"], control_metrics):
        lines.append(
            f"| {dynamic['day']} | {dynamic['food_ratio']} | "
            f"{fixed['food_ratio']} | {dynamic['water_ratio']} | "
            f"{fixed['water_ratio']} |"
        )
    lines.extend(
        [
            "",
            "- 固定能力对照仅用于拆分身体反馈放大效应，不代表现实方案。",
            f"- 动态结果高于固定对照的天数："
            f"`{sum(value > 0.001 for value in food_differences)}/7`；"
            f"低于固定对照的天数："
            f"`{sum(value < -0.001 for value in food_differences)}/7`。",
            "- 差异不是单向的，说明身体反馈改变了行动路径，"
            "不能简单表述为“身体反馈只会放大短缺”。",
            "",
            "## 社会行为接入状态",
            "",
            "| 阶段 | 跨家庭互助 | 教学 | 临时同住 |",
            "| --- | --- | --- | --- |",
            f"| 需求发生 | `{result['social_action_funnel']['need_events']}` | "
            "`not_measured` | `not_measured` |",
            "| 察觉可接触对象 | `not_connected` | `not_connected` | `not_connected` |",
            "| 考虑求助 | `not_connected` | `not_connected` | `not_connected` |",
            "| 发出请求 | `0: not_connected` | `0: not_connected` | `0: not_connected` |",
            "| 得到回应 | `0: not_connected` | `0: not_connected` | `0: not_connected` |",
            "| 实际执行 | `0: not_connected` | `0: not_connected` | `0: not_connected` |",
            "",
            "- 这组事件没有接入七天整合循环；零事件不能解释为人物选择不合作。",
            "- 只有短场景验证了请求、回应、拒绝和部分执行，尚未进入 4000 人统一调度。",
            "",
            "## 模型适用边界",
            "",
            (
                "- 有较多人物达到饥饿或口渴上限，后续变化不能作为长期生存结论。"
                if integration["people_with_hunger_at_cap"] > 0
                or integration["people_with_thirst_at_cap"] > 0
                else "- 七天结束时没有人物达到饥饿或口渴上限。"
            ),
            "- 恢复曲线、疾病、伤害和死亡阈值仍未校准。",
            "- 本诊断只用于检查时间、资源、信息和身体约束能否同时成立。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _seed_social_state(
    population: Any,
    states: dict[str, BehaviorState],
) -> None:
    for household in population.households:
        for person_id in household.member_ids:
            state = states[person_id]
            for other_id in household.member_ids:
                if person_id == other_id:
                    continue
                state.attachments[other_id] = 0.6
            for skill in population.people_by_id[person_id].skills:
                state.receive_knowledge(
                    f"skill.{skill['id']}",
                    "independent",
                    person_id,
                    0,
                    float(skill.get("proficiency", 0.5)),
                )


def _failure_reason_summary(
    acquisition_paths: dict[str, Any],
    metrics: list[Any],
) -> dict[str, int]:
    return {
        "days_without_enough_food": sum(
            metric.food_ratio < 0.8 for metric in metrics
        ),
        "days_without_enough_water": sum(
            metric.water_ratio < 0.8 for metric in metrics
        ),
        "water_vessel_failures": acquisition_paths["water"][
            "vessel_failures"
        ],
        "water_vessel_blocked_households": sum(
            acquisition_paths["water"]["blocked_reasons"].values()
        ),
        "fire_material_search_failures": acquisition_paths["fire_attempts"][
            "material_search_failures"
        ],
        "fire_attempt_failures": acquisition_paths["fire_attempts"][
            "total_failures"
        ],
        "shelter_households_not_completed": (
            acquisition_paths["shelter"]["households_total"]
            - acquisition_paths["shelter"]["households_completed"]
        ),
    }


def _personal_time_audit(
    records: list[dict[str, Any]],
    population: Any,
) -> dict[str, int]:
    by_person_day: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["person_id"], record["day"])
        by_person_day.setdefault(key, []).append(record)
    overlaps = 0
    over_capacity = 0
    care_records = 0
    for person_records in by_person_day.values():
        ordered = sorted(person_records, key=lambda item: item["start_minute"])
        for first, second in zip(ordered, ordered[1:]):
            if second["start_minute"] < first["end_minute"]:
                overlaps += 1
        if sum(item["hours"] for item in ordered) > 24.0:
            over_capacity += 1
        care_records += sum(
            item["category"] == "care" for item in ordered
        )
    expected_active_person_days = sum(
        person.life_stage in {"adolescent", "adult", "elder"}
        or (person.life_stage == "child" and person.age_years >= 6)
        for person in population.people
    ) * 7
    return {
        "records": len(records),
        "person_days": len(by_person_day),
        "overlaps": overlaps,
        "over_capacity": over_capacity,
        "care_records": care_records,
        "expected_active_person_days": expected_active_person_days,
        "missing_active_person_days": max(
            0, expected_active_person_days - len(by_person_day)
        ),
        "eligibility_violations": sum(
            not item["eligibility_checked"] for item in records
        ),
        "location_precision": "household_camp_only",
    }


def _water_diagnosis(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    deficient = [
        item for item in records if item["water_ratio"] < 0.8
    ]
    worst = sorted(
        deficient,
        key=lambda item: (item["water_ratio"], item["day"]),
    )[:10]
    by_method: dict[str, int] = {}
    by_blocked_reason: dict[str, int] = {}
    by_failure_cause: dict[str, int] = {}
    for item in deficient:
        if item["hours_before_water"] <= 0.01:
            cause = "no_labour_time_before_fetch"
        elif item["mobile_people"] == 0:
            cause = "no_mobile_person"
        elif (
            item["water_method"] == "travel_to_source_without_vessel"
            and item["direct_capacity_l"] < item["water_demand_l"]
        ):
            cause = "direct_access_capacity_short"
        else:
            cause = "available_water_time_or_delivery_short"
        item["failure_cause"] = cause
        by_failure_cause[cause] = by_failure_cause.get(cause, 0) + 1
        by_method[item["water_method"]] = (
            by_method.get(item["water_method"], 0) + 1
        )
        reason = item["vessel_blocked_reason"] or "not_blocked"
        by_blocked_reason[reason] = by_blocked_reason.get(reason, 0) + 1
    return {
        "deficient_household_days": len(deficient),
        "by_water_method": dict(sorted(by_method.items())),
        "by_vessel_blocked_reason": dict(sorted(by_blocked_reason.items())),
        "by_failure_cause": dict(sorted(by_failure_cause.items())),
        "worst_examples": worst,
    }


def _social_action_funnel(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    need_events = sum(
        item["food_ratio"] < 0.8 or item["water_ratio"] < 0.8
        for item in records
    )
    return {
        "need_events": need_events,
        "interhousehold": {
            "contact_opportunity": "not_connected",
            "consider_request": "not_connected",
            "request_sent": 0,
            "response_received": 0,
            "executed": 0,
            "classification": "not_connected_to_integrated_loop",
        },
        "teaching": {
            "need_measurement": "not_measured",
            "contact_opportunity": "not_connected",
            "request_sent": 0,
            "response_received": 0,
            "executed": 0,
            "classification": "not_connected_to_integrated_loop",
        },
        "cohabitation": {
            "need_measurement": "not_measured",
            "contact_opportunity": "not_connected",
            "request_sent": 0,
            "response_received": 0,
            "executed": 0,
            "classification": "not_connected_to_integrated_loop",
        },
    }
