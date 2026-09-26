"""Seven-day integrated diagnostic using the full 4000-person world."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .behavior import BehaviorState, BodyState, _state_for_person
from .environment import generate_environment, load_environment_baseline
from .population import generate_population
from .survival import run_survival_validation


def run_seven_day_integration(
    root: Path,
    version: str = "v5",
) -> dict[str, Any]:
    baseline = load_environment_baseline(
        root
        / "data"
        / "phase1"
        / "versions"
        / version
        / "environment_baseline.json"
    )
    world = generate_environment(baseline)
    population = generate_population(int(baseline.raw["seed"]), 4000)
    behavior_states = {
        person.id: _state_for_person(person, world.drop_point.index)
        for person in population.people
    }
    _seed_social_state(population, behavior_states)
    initial_dynamic_capacity = sum(
        state.body.work_capacity for state in behavior_states.values()
    ) / len(behavior_states)
    fixed_behavior_states = copy.deepcopy(behavior_states)
    run = run_survival_validation(
        world,
        population,
        days=7,
        behavior_states=behavior_states,
        record_household_trace=True,
        enable_social_exchange=True,
    )
    fixed_control = run_survival_validation(
        world,
        population,
        days=7,
        behavior_states=fixed_behavior_states,
        enable_social_exchange=True,
        apply_body_feedback=False,
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
        "version": version,
        "run_id": hashlib.sha256(
            (
                f"{version}:{world.initial_fingerprint}:"
                f"{population.fingerprint}:seven-day-dynamic"
            ).encode("ascii")
        ).hexdigest()[:16],
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
        "migration_summary": run.migration_summary,
        "care_and_shelter": {
            "dependent_people": sum(
                person.life_stage in {"infant", "toddler", "child"}
                for person in population.people
            ),
            "water_nonmobile_people": sum(
                person.life_stage in {"infant", "toddler"}
                or person.mobility < 0.5
                for person in population.people
            ),
            "water_dependency_definition": (
                "cannot safely reach water alone because of age or mobility"
            ),
            "care_dependency_definition": (
                "infant, toddler, or child requiring household care"
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
        "person_food_records": run.person_food_records,
        "food_path_records": run.food_path_records,
        "food_chain_trace": _food_chain_trace(
            run.food_path_records,
            run.daily_harvest_details,
            run.metrics,
            limit_days=5,
        ),
        "season_rejection_audit": _season_rejection_audit(
            run.food_path_records, baseline.raw["resources"]
        ),
        "fishing_exit_diagnosis": _fishing_exit_diagnosis(
            run.food_path_records,
            run.person_daily_records,
            run.household_daily_records,
            population,
        ),
        "food_intake_summary": _food_intake_summary(
            run.person_food_records
        ),
        "household_daily_records": run.household_daily_records,
        "person_daily_records": run.person_daily_records,
        "personal_time_audit": _personal_time_audit(
            run.person_daily_records, population
        ),
        "water_diagnosis": _water_diagnosis(run.household_daily_records),
        "body_fixed_control": {
            "mode": "frozen_individual_initial_capacity_control",
            "initial_dynamic_mean_capacity": round(
                initial_dynamic_capacity, 4
            ),
            "initial_fixed_mean_capacity": round(
                initial_dynamic_capacity, 4
            ),
            "same_initial_world": True,
            "same_initial_population": True,
            "same_social_rules": True,
            "daily_metrics": [asdict(metric) for metric in fixed_control.metrics],
            "note": (
                "Diagnostic counterfactual only; it does not represent a "
                "proposed behavior."
            ),
        },
        "social_actions": run.social_action_stats,
        "social_action_records": run.social_action_records,
        "social_action_funnel": _social_action_funnel(
            run.household_daily_records,
            run.social_action_stats,
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
        f"# {result['version']} 七天开局整合诊断",
        "",
        "这是 4000 人世界副本上的连续 7 天诊断，不是正式历史，也不能证明长期生存能力。",
        "",
        f"运行标识：`{result['run_id']}`；模式：`dynamic_body_short_integration`。",
        "",
        "## 整合口径",
        "",
        "- 行动在每个模拟日由当前身体、照护、资源和已探索信息产生，没有按日期脚本触发事件。",
        "- 身体劳动能力限制当日可用时间；实际摄入和缺水在当天结束后更新身体。",
        "- 食物、水、材料和劳动都从同一个世界副本扣除。",
        "- 跨家庭请求只面向 1 公里内、最多 6 个实际可接触家庭；不会全地图寻找救援者。",
        "- 求助、回应、拒绝和交付分别记录，零事件必须由阶段原因解释。",
        "- 家庭食物按个人需求与当前主张权重分配，再由明确进食事件更新身体；"
        "拒绝和协商仍只在短场景验证，未作为统一年度人格规则。",
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
            f"- 尚待执行的社交往返："
            f"`{result['time_account_hours']['pending_social_travel_hours']}` 小时；"
            "它作为未来承诺单独保留，没有冒充已经完成的活动。",
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
            "| 日期 | 摄入低于 80% 需求人数 | 平均摄入/需求 | 最低个人摄入/需求 |",
            "| ---: | ---: | ---: | ---: |",
        ]
    )
    for item in result["food_intake_summary"]["daily"]:
        lines.append(
            f"| {item['day']} | {item['below_80_percent_people']} | "
            f"{item['mean_intake_ratio']} | {item['minimum_intake_ratio']} |"
        )
    lines.extend(
        [
            "",
            "最低摄入个人样本：",
            "",
            "| 日 | 人物 | 家庭 | 摄入 kcal | 需求 kcal | 比例 |",
            "| ---: | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for item in result["food_intake_summary"]["lowest_examples"]:
        lines.append(
            f"| {item['day']} | `{item['person_id']}` | "
            f"`{item['household_id']}` | {item['intake_kcal']} | "
            f"{item['effective_need_kcal']} | {item['intake_ratio']} |"
        )
    lines.extend(
        [
            "",
            "## 每日食物获取链",
            "",
            "| 日期 | 去重已知热点 kcal | 家庭重复累计 kcal | 获取原料 kg | "
            "可食食物 kg | 日末库存 kcal | 资源切换 | 未成熟/过季检查 | "
            "无人会做检查 | 局部耗尽检查 | 无时间检查 | 加工失败检查 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric in result["daily_metrics"]:
        obstacles = metric["food_obstacles"]
        lines.append(
            f"| {metric['day']} | {metric['known_available_food_kcal']} | "
            f"{metric['household_known_food_kcal_sum']} | "
            f"{metric['stock_kg_acquired']} | "
            f"{metric['edible_food_kg_acquired']} | "
            f"{metric['food_store_end_kcal']} | "
            f"{metric['food_resource_switches']} | "
            f"{obstacles.get('not_mature_or_out_of_season', 0)} | "
            f"{obstacles.get('no_household_member_with_knowledge', 0)} | "
            f"{obstacles.get('local_stock_depleted', 0)} | "
            f"{obstacles.get('no_time_after_travel', 0)} | "
            f"{obstacles.get('processing_failed', 0)} |"
        )
    lines.extend(
        [
            "",
            "- 获取原料和可食食物分开记录；加工失败只减少可食产量，不能伪装成已吃下。",
            "- `去重已知热点` 按资源格去重，避免同一鱼塘被每个家庭重复计算；"
            "`家庭重复累计` 仅表示各家庭已知范围之和，不能当作全体供给。",
            "- 受阻列是备选检查次数，不是独立失败事件，也不能单独用于判断主因；"
            "实际完成链由个人活动和资源账给出。",
            f"- 资源切换事件："
            f"`{sum(item['food_resource_switches'] for item in result['daily_metrics'])}`；"
            f"迁移家庭："
            f"`{result['migration_summary']['households_that_migrated']}`；"
            f"跨家庭求助请求："
            f"`{sum(result['social_action_funnel'][key]['request_sent'] for key in ('water', 'food', 'fire', 'care', 'shelter', 'teaching'))}`。",
            "- 这些数量用于确认人物会切换资源、迁移或求助，较差的后续收益仍必须单独解释。",
        ]
    )
    trace = result["food_chain_trace"]
    lines.extend(
        [
            "",
            "### 主要来源逐日链",
            "",
            f"主要来源：`{trace['resource_id']}`。",
            "",
            "| 日 | 家庭数 | 采集小时 | 加工小时 | 原料 kg | 可食 kg | "
            "加工失败 | 切换次数 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in trace["daily"]:
        lines.append(
            f"| {item['day']} | {item['households']} | "
            f"{item['harvest_hours']} | {item['processing_hours']} | "
            f"{item['stock_kg_removed']} | {item['edible_food_kg']} | "
            f"{item['processing_failures']} | {item['resource_switches']} |"
        )
    lines.extend(
        [
            "",
            "代表性家庭资源选择：",
            "",
            "| 日 | 家庭 | 已知替代来源 | 实际选择 | 主要未选原因 | 地点 |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for item in trace["representative_households"]:
        lines.append(
            f"| {item['day']} | `{item['household_id']}` | "
            f"{item['known_alternatives']} | {item['selected']} | "
            f"`{item['main_not_selected_reason']}` | {item['selected_cells']} |"
        )
    season = result["season_rejection_audit"]
    world_days = season["observed_world_days"]
    lines.extend(
        [
            "",
            "### 替代资源季节拒绝核对",
            "",
            f"- 季节拒绝核对记录：`{season['records_examined']}` 个家庭日。",
            f"- 投放瞬间为世界年内第 `{season['drop_instant_day_of_year']}` 日；"
            f"本次记录的完整日为第 `{world_days[0]}`–`{world_days[-1]}` 日。",
            f"- 日期来源：`{season['season_model']}`；"
            f"局部成熟度是否建模：`{season['local_maturity_modeled']}`。",
            f"- 仅因季节窗口不符的拒绝："
            f"`{season['season_only_by_resource']}`。",
            f"- 季节窗口内却被标记为过季的错误："
            f"`{season['incorrect_outside_window_rejections']}`。",
            f"- 缺少世界年内日期的路径记录："
            f"`{season['records_without_day_of_year']}`。",
            "",
            "| 资源 | 季节窗口 | 季节拒绝检查 | 其他拒绝原因（候选格检查次数） | 结论 |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    rankings = [
        "cattail",
        "arrowhead",
        "mixed_berries",
        "hazelnut",
        "oak_acorn",
        "spring_greens",
        "fish",
        "waterfowl",
        "hare",
        "deer",
    ]
    for resource_id in rankings:
        assessment = season["resource_assessments"][resource_id]
        nonseason = ", ".join(
            f"{reason}={count}"
            for reason, count in assessment[
                "non_season_rejection_counts"
            ].items()
        )
        lines.append(
            f"| `{resource_id}` | "
            f"`{assessment['availability_day_range']}` | "
            f"{assessment['outside_window_rejections']} | "
            f"{nonseason or '无'} | "
            f"`{assessment['conclusion']}` |"
        )
    lines.extend(
        [
            "",
            "只抽取实际被标为季节不符的具体资源格；这些记录均核对世界年内日"
            "和当前 `availability_day_range`。",
            "",
            "| 投放后日 | 世界年内日 | 家庭 | 营地格 | 资源 | 资源格 | 季节窗口 | 窗口内 |",
            "| ---: | ---: | --- | ---: | --- | ---: | --- | --- |",
        ]
    )
    for item in season["samples"]:
        lines.append(
            f"| {item['day']} | {item['day_of_year']} | "
            f"`{item['household_id']}` | {item['camp_cell_index']} | "
            f"`{item['resource_id']}` | {item['cell_index']} | "
            f"`{item['availability_day_range']}` | "
            f"{item['inside_configured_window']} |"
        )
    fishing = result["fishing_exit_diagnosis"]
    lines.extend(
        [
            "",
            "### 捕鱼退出原因",
            "",
            f"- 第 2 日参与捕鱼的家庭：`{fishing['day_2_fishing_households']}`。",
            f"- 第 4 日全体参与捕鱼："
            f"`{fishing['day_4_fishing_households_all']}`；"
            f"其中来自第 2 日捕鱼队列："
            f"`{fishing['day_4_fishing_households_from_day_2']}`。",
            f"- 第 5 日全体参与捕鱼："
            f"`{fishing['day_5_fishing_households_all']}`；"
            f"其中来自第 2 日捕鱼队列："
            f"`{fishing['day_5_fishing_households_from_day_2']}`。",
            f"- 第 2 日参与、但第 4 与第 5 日均未再取得鱼的家庭队列："
            f"`{fishing['exited_both_days_households']}`。",
            f"- 后续两日按家庭日分类："
            f"`{fishing['exit_daily_classification']}`。",
            f"- 退出队列按家庭归并："
            f"`{fishing['exit_cohort_classification']}`。",
            f"- 退出队列第 4–5 日仍已知有正鱼群存量的家庭日："
            f"`{fishing['exit_cohort_household_days_with_positive_fish_stock']}`。",
            f"- 退出队列第 4–5 日有正替代资源存量的家庭日："
            f"`{fishing['exit_cohort_household_days_with_positive_alternative']}`；"
            "没有正替代资源的家庭日："
            f"`{fishing['exit_cohort_household_days_without_positive_alternative']}`。",
            f"- 退出队列实际选择的资源计数："
            f"`{fishing['exit_cohort_selected_resources']}`。",
            f"- 退出队列家庭食物满足率："
            f"`{fishing['exit_cohort_food_ratio']}`。",
            f"- 退出队列营地分布："
            f"`{fishing['exit_cohort_camp_distribution']}`。",
            "",
            "| 日 | 选中鱼类资源格次数 | 不同鱼类资源格 | 单格最多家庭 | 前五资源格 |",
            "| ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for day, item in fishing["fish_selected_cells_by_day"].items():
        top_cells = ", ".join(
            f"{entry['cell_index']}:{entry['households']}"
            for entry in item["top_cells"]
        )
        lines.append(
            f"| {day} | {item['selected_cell_occurrences']} | "
            f"{item['distinct_selected_cells']} | "
            f"{item['largest_cell_households']} | {top_cells} |"
        )
    lines.extend(
        [
            "",
            "#### 捕鱼减少后的时间去向",
            "",
            "| 时间类别 | 第 2 日均值 | 第 4–5 日均值 |",
            "| --- | ---: | ---: |",
        ]
    )
    categories = sorted(
        set(fishing["aggregate_time_shift_per_exiting_household"]["day_2"])
        | set(
            fishing["aggregate_time_shift_per_exiting_household"][
                "mean_day_4_5"
            ]
        )
    )
    for category in categories:
        lines.append(
            f"| `{category}` | "
            f"{fishing['aggregate_time_shift_per_exiting_household']['day_2'].get(category, 0.0)} | "
            f"{fishing['aggregate_time_shift_per_exiting_household']['mean_day_4_5'].get(category, 0.0)} |"
        )
    fish_activity_day_2 = fishing[
        "resource_activity_shift_per_exiting_household"
    ]["day_2_fish"]
    lines.extend(
        [
            "",
            "| 第 2 日鱼类资源活动 | 家庭均值 |",
            "| --- | ---: |",
        ]
    )
    for key, value in fish_activity_day_2.items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "| 第 4–5 日替代资源 | 资源格 | 原料 kg | 可食 kg | 采集小时 | 加工小时 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    alternative_activity = fishing[
        "resource_activity_shift_per_exiting_household"
    ]["day_4_5_alternatives"]
    for resource_id, activity in alternative_activity.items():
        lines.append(
            f"| `{resource_id}` | {activity.get('cells_selected', 0)} | "
            f"{activity.get('stock_kg_removed', 0.0)} | "
            f"{activity.get('edible_food_kg', 0.0)} | "
            f"{activity.get('harvest_hours', 0.0)} | "
            f"{activity.get('processing_hours', 0.0)} |"
        )
    lines.extend(
        [
            "",
            "#### 退出队列代表性证据",
            "",
            "| 家庭 | 日 | 分类 | 当日选择 | 已知鱼 kcal | 鱼候选拒绝 | 可用小时 | 照护小时 | 食物比例 |",
            "| --- | ---: | --- | --- | ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for item in fishing["representative_exits"]:
        for day_item in item["daily"]:
            lines.append(
                f"| `{item['household_id']}` | {day_item['day']} | "
                f"`{day_item['reason']}` | "
                f"{day_item['selected_resources']} | "
                f"{day_item['known_fish_kcal']} | "
                f"`{day_item['fish_rejection_counts']}` | "
                f"{day_item['hours_available']} | "
                f"{day_item['care_hours']} | "
                f"{day_item['food_ratio']} |"
            )
    lines.extend(
        [
            "",
            "| 家庭 | 日 | 人物 | 活动 | 小时 | 地点格 | 说明 |",
            "| --- | ---: | --- | --- | ---: | ---: | --- |",
        ]
    )
    for item in fishing["representative_exits"][:2]:
        for activity in item["person_activity_trace"][:10]:
            lines.append(
                f"| `{item['household_id']}` | {activity['day']} | "
                f"`{activity['person_id']}` | `{activity['category']}` | "
                f"{activity['hours']} | {activity['location_cell']} | "
                f"`{activity['detail']}` |"
            )
    lines.extend(
        [
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
            f"- 不能自行到水边的人数：`{care['water_nonmobile_people']}`。",
            f"- 取水依赖定义：{care['water_dependency_definition']}。",
            f"- 照护依赖定义：{care['care_dependency_definition']}。",
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
            "请求与陪同路径已经接入；本运行若仍未解决，原因应由接触、回应或执行记录说明。",
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
            f"- 照护对象人数："
            f"`{len(result['personal_time_audit']['care_recipient_ids'])}`；"
            f"缺少对象的照护记录："
            f"`{result['personal_time_audit']['care_records_without_target']}`。",
            "- “不能自行到水边人数”和“需要儿童/家庭照护人数”口径不同；"
            "后者可以为正而前者为零。",
            "- `potential` 指身体修正后的可劳动小时，不是全部清醒时间；"
            "剩余部分进入休息或未使用能力。",
            f"- 记录到实际资源格或水源格的活动："
            f"`{result['personal_time_audit']['records_with_activity_site']}`；"
            f"仅记录到家庭营地的活动："
            f"`{result['personal_time_audit']['records_with_camp_only']}`。",
            "",
            "### 代表性行动链",
            "",
            "| 日 | 人物 | 家庭 | 活动 | 开始 | 结束 | 地点单元 | 说明 |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for action in result["personal_time_audit"]["representative_actions"]:
        lines.append(
            f"| {action['day']} | `{action['person_id']}` | "
            f"`{action['household_id']}` | `{action['category']}` | "
            f"{action['start_minute']} | {action['end_minute']} | "
            f"{action['location_cell']} | `{action['detail']}` |"
        )
    lines.extend(
        [
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
            f"- 两组使用同一世界、人口、行动和求助规则；动态组初始平均能力 "
            f"`{result['body_fixed_control']['initial_dynamic_mean_capacity']}`，"
            f"固定组为 "
            f"`{result['body_fixed_control']['initial_fixed_mean_capacity']}`，"
            "因此第一天不再存在初始能力差异；后续差异只来自身体状态是否继续变化。",
            f"- 动态结果高于固定对照的天数："
            f"`{sum(value > 0.001 for value in food_differences)}/7`；"
            f"低于固定对照的天数："
            f"`{sum(value < -0.001 for value in food_differences)}/7`。",
            "- 差异不是单向的，说明身体反馈改变了行动路径，"
            "不能简单表述为“身体反馈只会放大短缺”。",
            "",
            "## 社会行为接入状态",
            "",
            f"涉及至少一种短缺的家庭日："
            f"`{result['social_action_funnel']['total_need_events']}`；"
            f"按求助类型累计的需求事件："
            f"`{result['social_action_funnel']['sum_aid_need_events']}`。"
            "同一家庭日可能同时缺水、缺食和缺火，因此两个数字口径不同，不要求相等。",
            "",
            "| 需求 | 发生需求 | 附近候选 | 知道位置 | 找到人 | 可交流 | 请求 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for aid_type in ("water", "food", "fire", "care", "shelter", "teaching"):
        item = result["social_action_funnel"][aid_type]
        lines.append(
            f"| `{aid_type}` | {item['need_events']} | "
            f"{item['candidate_households']} | {item['location_known']} | "
            f"{item['person_found']} | {item['communication_opportunity']} | "
            f"{item['request_sent']} |"
        )
    lines.extend(
        [
            "",
            "| 需求 | 回应 | 愿意但当前无资源 | 有条件未来承诺 | "
            "当前交付承诺 | 拒绝 | 执行 | 未来承诺兑现 | 未来承诺失败 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for aid_type in ("water", "food", "fire", "care", "shelter", "teaching"):
        item = result["social_action_funnel"][aid_type]
        lines.append(
            f"| `{aid_type}` | {item['response_received']} | "
            f"{item['willing_no_current_resource']} | "
            f"{item['conditional_promises']} | "
            f"{item['current_delivery_commitments']} | "
            f"{item['rejected']} | {item['executed']} | "
            f"{item['promises_executed']} | {item['promises_failed']} |"
        )
    lines.extend(
        [
            "",
            "- 回应闭合："
            + "；".join(
                f"`{aid_type}`={result['social_action_funnel'][aid_type]['response_closure_error']}"
                for aid_type in (
                    "water",
                    "food",
                    "fire",
                    "care",
                    "shelter",
                    "teaching",
                )
            ),
            "- 当前交付承诺闭合："
            + "；".join(
                f"`{aid_type}`={result['social_action_funnel'][aid_type]['commitment_closure_error']}"
                for aid_type in (
                    "water",
                    "food",
                    "fire",
                    "care",
                    "shelter",
                    "teaching",
                )
            ),
        ]
    )
    lines.extend(
        [
            "",
            "| 需求 | 未继续原因 |",
            "| --- | --- |",
        ]
    )
    for aid_type in ("water", "food", "fire", "care", "shelter", "teaching"):
        item = result["social_action_funnel"][aid_type]
        lines.append(
            f"| `{aid_type}` | `{item['not_continued_reasons']}` |"
        )
    lines.extend(
        [
            "",
            "- 接触对象只从 1 公里内、最多 6 个可达家庭中选择，不做全地图最优匹配。",
            "- 候选不等于认识或已经接触；知道位置、找到人、可以交流和请求分别计数。",
            "- 未继续的原因汇总保存在机器结果，区分无候选、无位置、找不到人、无交流机会、"
            "无资源、被拒绝和执行失败。",
            "- 照护请求的接受与次日实际使用分开；整合表不把未来承诺记作已经执行。",
            "- 住所请求为零表示没有家庭同时满足“雨天”和“遮蔽不足”两个触发条件，"
            "不是住所行为未接入。",
            "- 教学接受后没有执行，原因是教师或学习者状态不满足；该失败保留，"
            "不为展示功能强制成功。",
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
                    (
                        "can_teach"
                        if float(skill.get("proficiency", 0.5)) >= 0.7
                        else "independent"
                    ),
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
) -> dict[str, Any]:
    by_person_day: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["person_id"], record["day"])
        by_person_day.setdefault(key, []).append(record)
    overlaps = 0
    over_capacity = 0
    care_records = 0
    care_recipient_ids: set[str] = set()
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
        for item in ordered:
            if item["category"] == "care":
                care_recipient_ids.update(item.get("target_person_ids", []))
    expected_active_person_days = sum(
        person.life_stage in {"adolescent", "adult", "elder"}
        or (person.life_stage == "child" and person.age_years >= 6)
        for person in population.people
    ) * 7
    household_by_person = {
        person.id: person.household_id for person in population.people
    }
    representative_actions = [
        {
            "person_id": item["person_id"],
            "household_id": household_by_person[item["person_id"]],
            "day": item["day"],
            "category": item["category"],
            "start_minute": item["start_minute"],
            "end_minute": item["end_minute"],
            "location_cell": item["location_cell"],
            "location_precision": item["location_precision"],
            "detail": item["detail"],
        }
        for item in records
        if item["location_precision"] == "resource_or_water_cell"
    ][:12]
    return {
        "records": len(records),
        "person_days": len(by_person_day),
        "overlaps": overlaps,
        "over_capacity": over_capacity,
        "care_records": care_records,
        "care_recipient_ids": sorted(care_recipient_ids),
        "care_records_without_target": sum(
            item["category"] == "care"
            and not item.get("target_person_ids")
            for item in records
        ),
        "expected_active_person_days": expected_active_person_days,
        "missing_active_person_days": max(
            0, expected_active_person_days - len(by_person_day)
        ),
        "eligibility_violations": sum(
            not item["eligibility_checked"] for item in records
        ),
        "records_with_activity_site": sum(
            item["location_precision"] == "resource_or_water_cell"
            for item in records
        ),
        "records_with_camp_only": sum(
            item["location_precision"] == "household_camp_only"
            for item in records
        ),
        "representative_actions": representative_actions,
    }


def _food_intake_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    by_day: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        by_day.setdefault(record["day"], []).append(record)
    daily = []
    for day, items in sorted(by_day.items()):
        ratios = [item["intake_ratio"] for item in items]
        daily.append(
            {
                "day": day,
                "below_80_percent_people": sum(
                    item["below_80_percent_need"] for item in items
                ),
                "mean_intake_ratio": round(sum(ratios) / len(ratios), 4),
                "minimum_intake_ratio": round(min(ratios), 4),
            }
        )
    lowest = sorted(
        records,
        key=lambda item: (item["intake_ratio"], item["day"], item["person_id"]),
    )[:12]
    return {"daily": daily, "lowest_examples": lowest}


def _food_chain_trace(
    path_records: list[dict[str, Any]],
    harvest_records: list[dict[str, Any]],
    metrics: list[Any],
    limit_days: int,
) -> dict[str, Any]:
    recent_harvest = [
        item for item in harvest_records if int(item["day"]) <= limit_days
    ]
    totals: dict[str, float] = {}
    for item in recent_harvest:
        resource_id = str(item["resource_id"])
        totals[resource_id] = totals.get(resource_id, 0.0) + float(
            item["stock_kg_removed"]
        )
    resource_id = max(totals, key=totals.get) if totals else "none"
    by_day: dict[int, dict[str, float]] = {}
    households_by_day: dict[int, set[str]] = {}
    switches_by_day = {
        int(metric.day): metric.food_resource_switches for metric in metrics
    }
    for item in recent_harvest:
        if item["resource_id"] != resource_id:
            continue
        day = int(item["day"])
        aggregate = by_day.setdefault(
            day,
            {
                "households": 0.0,
                "harvest_hours": 0.0,
                "processing_hours": 0.0,
                "stock_kg_removed": 0.0,
                "edible_food_kg": 0.0,
                "processing_failures": 0.0,
                "resource_switches": 0.0,
            },
        )
        households_by_day.setdefault(day, set()).add(str(item["household_id"]))
        aggregate["harvest_hours"] += float(item["harvest_hours"])
        aggregate["processing_hours"] += float(item["processing_hours"])
        aggregate["stock_kg_removed"] += float(item["stock_kg_removed"])
        aggregate["edible_food_kg"] += float(item["edible_food_kg"])
        aggregate["processing_failures"] += float(item["processing_failure"])
        aggregate["resource_switches"] = switches_by_day.get(day, 0)
    representatives = []
    used_households: set[str] = set()
    for day in range(1, limit_days + 1):
        candidates = [
            item
            for item in path_records
            if int(item["day"]) == day
            and resource_id in item.get("selected_resources", [])
            and item.get("household_id") not in used_households
        ]
        if not candidates:
            continue
        item = max(
            candidates,
            key=lambda candidate: float(candidate["hours_used"]),
        )
        used_households.add(str(item["household_id"]))
        reasons = item.get("decision_reasons", {})
        main_reason = (
            max(reasons, key=reasons.get)
            if reasons
            else "no_unselected_reason_recorded"
        )
        representatives.append(
            {
                "day": day,
                "household_id": item["household_id"],
                "known_alternatives": sorted(
                    item.get("known_resources", {})
                )[:8],
                "selected": item.get("selected_resources", [])[:5],
                "main_not_selected_reason": main_reason,
                "selected_cells": item.get("selected_cells", [])[:5],
            }
        )
    return {
        "resource_id": resource_id,
        "reason": "selected by cumulative stock removed during the first five days",
        "daily": [
            {
                "day": day,
                "households": len(households_by_day.get(day, set())),
                **{
                    key: round(value, 6)
                    for key, value in item.items()
                    if key != "households"
                },
            }
            for day, item in sorted(by_day.items())
        ],
        "representative_households": representatives,
    }


def _season_rejection_audit(
    path_records: list[dict[str, Any]],
    resource_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    windows = {
        item["id"]: item["availability_day_range"]
        for item in resource_specs
    }
    by_resource: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    season_only_by_resource: dict[str, int] = {}
    nonseason_by_resource: dict[str, dict[str, int]] = {}
    samples: list[dict[str, Any]] = []
    observed_world_days: set[int] = set()
    day_to_world_day: dict[int, int] = {}
    records_without_day_of_year = 0
    incorrect = 0
    for path in path_records:
        world_day = path.get("day_of_year")
        if world_day is None:
            records_without_day_of_year += 1
        else:
            world_day = int(world_day)
            observed_world_days.add(world_day)
            day_to_world_day[int(path["day"])] = world_day
        for resource_id, reason_counts in path.get(
            "rejection_summary", {}
        ).items():
            for reason, count in reason_counts.items():
                by_resource[resource_id] = (
                    by_resource.get(resource_id, 0) + count
                )
                by_reason[reason] = by_reason.get(reason, 0) + count
                if reason == "outside_availability_window":
                    season_only_by_resource[resource_id] = (
                        season_only_by_resource.get(resource_id, 0) + count
                    )
                else:
                    resource_reasons = nonseason_by_resource.setdefault(
                        resource_id, {}
                    )
                    resource_reasons[reason] = (
                        resource_reasons.get(reason, 0) + count
                    )
        for rejection in path.get("rejected_resource_cells", []):
            resource_id = rejection["resource_id"]
            reason = rejection["reason"]
            rejection_day = int(rejection["day_of_year"])
            window = windows.get(resource_id)
            inside_window = (
                window is not None
                and int(window[0]) <= rejection_day <= int(window[1])
            )
            if reason == "outside_availability_window" and inside_window:
                incorrect += 1
            if (
                reason == "outside_availability_window"
                and len(samples) < 30
            ):
                samples.append(
                    {
                        "day": path["day"],
                        "day_of_year": rejection_day,
                        "household_id": path["household_id"],
                        "resource_id": resource_id,
                        "cell_index": rejection["cell_index"],
                        "camp_cell_index": path["camp_cell_index"],
                        "reason": reason,
                        "availability_day_range": window,
                        "inside_configured_window": inside_window,
                    }
                )
    resource_assessments: dict[str, dict[str, Any]] = {}
    for resource_id, window in windows.items():
        reasons = nonseason_by_resource.get(resource_id, {})
        season_count = season_only_by_resource.get(resource_id, 0)
        resource_assessments[resource_id] = {
            "availability_day_range": window,
            "outside_window_rejections": season_count,
            "non_season_rejection_counts": dict(sorted(reasons.items())),
            "conclusion": (
                "season_window_rejected"
                if season_count
                else "not_rejected_by_season_in_this_run"
            ),
        }
    sorted_world_days = sorted(observed_world_days)
    first_simulated_day = day_to_world_day.get(1)
    drop_instant_day = (
        first_simulated_day - 1 if first_simulated_day is not None else None
    )
    return {
        "records_examined": len(path_records),
        "records_without_day_of_year": records_without_day_of_year,
        "drop_instant_day_of_year": drop_instant_day,
        "observed_world_days": sorted_world_days,
        "day_to_world_day": {
            str(day): world_day
            for day, world_day in sorted(day_to_world_day.items())
        },
        "season_model": "whole_resource_cell_uses_day_of_year_window",
        "local_maturity_modeled": False,
        "by_resource": dict(sorted(by_resource.items())),
        "season_only_by_resource": dict(
            sorted(season_only_by_resource.items())
        ),
        "by_reason": dict(sorted(by_reason.items())),
        "resource_assessments": resource_assessments,
        "incorrect_outside_window_rejections": incorrect,
        "samples": samples,
    }


def _fishing_exit_diagnosis(
    path_records: list[dict[str, Any]],
    activity_records: list[dict[str, Any]],
    household_daily_records: list[dict[str, Any]],
    population: Any,
) -> dict[str, Any]:
    day_two = {
        item["household_id"]
        for item in path_records
        if int(item["day"]) == 2
        and "fish" in item.get("selected_resources", [])
    }
    records_by_household_day = {
        (item["household_id"], int(item["day"])): item
        for item in path_records
    }
    day_four = {
        household_id
        for household_id in day_two
        if "fish"
        in records_by_household_day.get((household_id, 4), {}).get(
            "selected_resources", []
        )
    }
    day_five = {
        household_id
        for household_id in day_two
        if "fish"
        in records_by_household_day.get((household_id, 5), {}).get(
            "selected_resources", []
        )
    }
    exit_households = day_two - day_four - day_five
    fish_selected_cells_by_day: dict[str, dict[str, Any]] = {}
    for day in range(1, 8):
        cell_counts: dict[int, int] = {}
        for record in path_records:
            if int(record["day"]) != day:
                continue
            for resource_id, cell_index in zip(
                record.get("selected_resources", []),
                record.get("selected_cells", []),
            ):
                if resource_id == "fish":
                    cell_counts[int(cell_index)] = (
                        cell_counts.get(int(cell_index), 0) + 1
                    )
        fish_selected_cells_by_day[str(day)] = {
            "selected_cell_occurrences": sum(cell_counts.values()),
            "distinct_selected_cells": len(cell_counts),
            "largest_cell_households": (
                max(cell_counts.values()) if cell_counts else 0
            ),
            "top_cells": [
                {"cell_index": cell_index, "households": count}
                for cell_index, count in sorted(
                    cell_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:5]
            ],
        }
    exit_camp_counts: dict[int, int] = {}
    for household_id in exit_households:
        record = records_by_household_day.get((household_id, 5))
        if record is None:
            continue
        camp_index = int(record["camp_cell_index"])
        exit_camp_counts[camp_index] = exit_camp_counts.get(camp_index, 0) + 1

    def classify_exit(record: dict[str, Any] | None) -> str:
        if record is None:
            return "no_food_path_record"
        if "fish" in record.get("selected_resources", []):
            return "still_fishing"
        if record.get("hours_available", 0.0) <= 0.01:
            return "no_labour_time_after_care_or_body_limit"
        fish_rejections = record.get("rejection_summary", {}).get(
            "fish", {}
        )
        known_fish_kcal = float(
            record.get("known_resources", {}).get("fish", 0.0)
        )
        if (
            fish_rejections.get("local_stock_depleted", 0) > 0
            and known_fish_kcal <= 0.001
        ):
            return "known_fish_cells_depleted"
        if fish_rejections.get("no_time_after_travel", 0) > 0:
            return "travel_time_insufficient"
        if (
            fish_rejections.get(
                "no_household_member_with_knowledge", 0
            )
            > 0
            and known_fish_kcal <= 0.001
        ):
            return "no_current_fishing_knowledge"
        if record.get("selected_resources"):
            return "switched_to_other_resource"
        if known_fish_kcal > 0.001:
            return "fish_known_but_not_selected"
        fish_candidates = record.get("candidate_summary", {}).get(
            "fish", {}
        )
        if (
            fish_candidates.get("examined_candidates", 0) > 0
            and fish_candidates.get("available_stock_cells", 0) == 0
        ):
            return "fish_candidates_unavailable"
        return "fish_not_known_or_not_accessible"

    daily_classification: dict[str, int] = {}
    for household_id in sorted(day_two):
        for day in (4, 5):
            reason = classify_exit(
                records_by_household_day.get((household_id, day))
            )
            daily_classification[reason] = (
                daily_classification.get(reason, 0) + 1
            )
    cohort_classification: dict[str, int] = {}
    for household_id in sorted(exit_households):
        reasons = {
            classify_exit(records_by_household_day.get((household_id, day)))
            for day in (4, 5)
        }
        if reasons == {"known_fish_cells_depleted"}:
            reason = "known_fish_cells_depleted_both_days"
        elif "no_labour_time_after_care_or_body_limit" in reasons:
            reason = "labour_limit_on_at_least_one_day"
        elif "travel_time_insufficient" in reasons:
            reason = "travel_time_limit_on_at_least_one_day"
        elif reasons == {"switched_to_other_resource"}:
            reason = "switched_to_other_resource_both_days"
        else:
            reason = "mixed_or_other_reason"
        cohort_classification[reason] = (
            cohort_classification.get(reason, 0) + 1
        )

    household_by_person = {
        person.id: person.household_id for person in population.people
    }
    activity_by_household = {
        household_id: {
            "day_2": {},
            "day_4_5": {},
        }
        for household_id in day_two
    }
    time_destinations: dict[str, dict[str, float]] = {}
    for activity in activity_records:
        household_id = household_by_person.get(activity["person_id"])
        if household_id not in activity_by_household:
            continue
        day = int(activity["day"])
        bucket = "day_2" if day == 2 else "day_4_5" if day in {4, 5} else None
        if bucket is None:
            continue
        category = activity["category"]
        activity_by_household[household_id][bucket][category] = (
            activity_by_household[household_id][bucket].get(category, 0.0)
            + float(activity["hours"])
        )
    for household_id, buckets in activity_by_household.items():
        divisor = 2.0
        baseline = buckets["day_2"]
        later = {
            category: round(value / divisor, 6)
            for category, value in sorted(buckets["day_4_5"].items())
        }
        time_destinations[household_id] = {
            "day_2": {
                key: round(value, 6)
                for key, value in sorted(baseline.items())
            },
            "mean_day_4_5": later,
        }
    food_ratio_by_household_day = {
        (item["household_id"], int(item["day"])): float(item["food_ratio"])
        for item in household_daily_records
    }
    cohort_food_ratios: dict[str, dict[str, float | int | None]] = {}
    for day in (2, 4, 5):
        values = [
            food_ratio_by_household_day[(household_id, day)]
            for household_id in exit_households
            if (household_id, day) in food_ratio_by_household_day
        ]
        cohort_food_ratios[str(day)] = {
            "sample_households": len(values),
            "mean": round(sum(values) / len(values), 6) if values else None,
            "minimum": round(min(values), 6) if values else None,
        }
    selected_resource_counts: dict[str, int] = {}
    no_positive_alternative_household_days = 0
    positive_alternative_household_days = 0
    positive_fish_household_days = 0
    for household_id in exit_households:
        for day in (4, 5):
            record = records_by_household_day.get((household_id, day))
            if record is None:
                continue
            known_resources = record.get("known_resources", {})
            if float(known_resources.get("fish", 0.0)) > 0.001:
                positive_fish_household_days += 1
            if any(
                resource_id != "fish" and float(kcal) > 0.001
                for resource_id, kcal in known_resources.items()
            ):
                positive_alternative_household_days += 1
            else:
                no_positive_alternative_household_days += 1
            for resource_id in record.get("selected_resources", []):
                selected_resource_counts[resource_id] = (
                    selected_resource_counts.get(resource_id, 0) + 1
                )
    resource_activity_shift: dict[str, dict[str, Any]] = {
        "day_2_fish": {},
        "day_4_5_alternatives": {},
    }
    for household_id in exit_households:
        fish_activity = (
            records_by_household_day.get((household_id, 2), {})
            .get("resource_activity", {})
            .get("fish", {})
        )
        for key, value in fish_activity.items():
            resource_activity_shift["day_2_fish"][key] = round(
                float(resource_activity_shift["day_2_fish"].get(key, 0.0))
                + float(value),
                6,
            )
        for day in (4, 5):
            record = records_by_household_day.get((household_id, day))
            if record is None:
                continue
            for resource_id, activity in record.get(
                "resource_activity", {}
            ).items():
                bucket = resource_activity_shift[
                    "day_4_5_alternatives"
                ].setdefault(resource_id, {})
                for key, value in activity.items():
                    bucket[key] = round(
                        float(bucket.get(key, 0.0)) + float(value), 6
                    )
    aggregate_day_2: dict[str, float] = {}
    aggregate_day_4_5: dict[str, float] = {}
    for household_id in exit_households:
        buckets = activity_by_household[household_id]
        for category, value in buckets["day_2"].items():
            aggregate_day_2[category] = (
                aggregate_day_2.get(category, 0.0) + value
            )
        for category, value in buckets["day_4_5"].items():
            aggregate_day_4_5[category] = (
                aggregate_day_4_5.get(category, 0.0) + value
            )
    exit_count = max(1, len(exit_households))
    for key, value in list(
        resource_activity_shift["day_2_fish"].items()
    ):
        resource_activity_shift["day_2_fish"][key] = round(
            float(value) / exit_count, 6
        )
    for resource_id, activity in resource_activity_shift[
        "day_4_5_alternatives"
    ].items():
        for key, value in list(activity.items()):
            activity[key] = round(float(value) / exit_count / 2.0, 6)

    activity_trace_by_household: dict[str, list[dict[str, Any]]] = {}
    for activity in activity_records:
        household_id = household_by_person.get(activity["person_id"])
        if (
            household_id in exit_households
            and int(activity["day"]) in {2, 4, 5}
        ):
            activity_trace_by_household.setdefault(
                household_id, []
            ).append(
                {
                    "day": activity["day"],
                    "person_id": activity["person_id"],
                    "category": activity["category"],
                    "hours": activity["hours"],
                    "detail": activity.get("detail"),
                    "location_cell": activity.get("location_cell"),
                    "location_precision": activity.get(
                        "location_precision"
                    ),
                }
            )

    representative_households: list[str] = []
    seen_reasons: set[str] = set()
    for household_id in sorted(exit_households):
        reasons = [
            classify_exit(records_by_household_day.get((household_id, day)))
            for day in (4, 5)
        ]
        reason = reasons[0] if len(reasons) == 1 else "mixed"
        if reason in seen_reasons and len(representative_households) >= 6:
            continue
        seen_reasons.add(reason)
        representative_households.append(household_id)
        if len(representative_households) >= 10:
            break
    representative_exits = []
    for household_id in representative_households:
        representative_exits.append(
            {
                "household_id": household_id,
                "daily": [
                    {
                        "day": day,
                        "reason": classify_exit(
                            records_by_household_day.get(
                                (household_id, day)
                            )
                        ),
                        "selected_resources": (
                            records_by_household_day.get(
                                (household_id, day), {}
                            ).get("selected_resources", [])
                        ),
                        "known_fish_kcal": records_by_household_day.get(
                            (household_id, day), {}
                        )
                        .get("known_resources", {})
                        .get("fish", 0.0),
                        "fish_rejection_counts": records_by_household_day.get(
                            (household_id, day), {}
                        )
                        .get("rejection_summary", {})
                        .get("fish", {}),
                        "candidate_summary": records_by_household_day.get(
                            (household_id, day), {}
                        )
                        .get("candidate_summary", {})
                        .get("fish", {}),
                        "food_ratio": food_ratio_by_household_day.get(
                            (household_id, day)
                        ),
                        "hours_available": records_by_household_day.get(
                            (household_id, day), {}
                        ).get("hours_available"),
                        "care_hours": records_by_household_day.get(
                            (household_id, day), {}
                        ).get("care_hours"),
                    }
                    for day in (2, 4, 5)
                ],
                "time_destination": time_destinations[household_id],
                "person_activity_trace": activity_trace_by_household.get(
                    household_id, []
                )[:18],
            }
        )
    return {
        "day_2_fishing_households": len(day_two),
        "day_4_fishing_households_all": len(
            {
                item["household_id"]
                for item in path_records
                if int(item["day"]) == 4
                and "fish" in item.get("selected_resources", [])
            }
        ),
        "day_5_fishing_households_all": len(
            {
                item["household_id"]
                for item in path_records
                if int(item["day"]) == 5
                and "fish" in item.get("selected_resources", [])
            }
        ),
        "day_4_fishing_households_from_day_2": len(day_four),
        "day_5_fishing_households_from_day_2": len(day_five),
        "exited_both_days_households": len(exit_households),
        "fish_selected_cells_by_day": fish_selected_cells_by_day,
        "exit_cohort_camp_distribution": {
            "distinct_camps": len(exit_camp_counts),
            "largest_camp_households": (
                max(exit_camp_counts.values()) if exit_camp_counts else 0
            ),
            "camps": [
                {"camp_cell_index": cell_index, "households": count}
                for cell_index, count in sorted(
                    exit_camp_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:10]
            ],
        },
        "exit_daily_classification": dict(
            sorted(daily_classification.items())
        ),
        "exit_cohort_classification": dict(
            sorted(cohort_classification.items())
        ),
        "aggregate_time_shift_per_exiting_household": {
            "day_2": {
                key: round(value / exit_count, 6)
                for key, value in sorted(aggregate_day_2.items())
            },
            "mean_day_4_5": {
                key: round(value / exit_count / 2.0, 6)
                for key, value in sorted(aggregate_day_4_5.items())
            },
        },
        "resource_activity_shift_per_exiting_household": (
            resource_activity_shift
        ),
        "exit_cohort_selected_resources": dict(
            sorted(selected_resource_counts.items())
        ),
        "exit_cohort_household_days_with_positive_alternative": (
            positive_alternative_household_days
        ),
        "exit_cohort_household_days_without_positive_alternative": (
            no_positive_alternative_household_days
        ),
        "exit_cohort_household_days_with_positive_fish_stock": (
            positive_fish_household_days
        ),
        "exit_cohort_food_ratio": cohort_food_ratios,
        "representative_exits": representative_exits,
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
    stats: dict[str, Any],
) -> dict[str, Any]:
    total_need_events = sum(
        item["food_ratio"] < 0.8 or item["water_ratio"] < 0.8
        for item in records
    )
    def aid_stats(name: str) -> dict[str, Any]:
        item = stats.get(name, {})
        accepted_not_executed = max(
            0, item.get("accepted", 0) - item.get("executed", 0)
        )
        response_parts = (
            item.get("rejected", 0)
            + item.get("willing_no_current_resource", 0)
            + item.get("conditional_promises", 0)
            + item.get("current_delivery_commitments", 0)
        )
        return {
            "need_events": item.get("need_events", 0),
            "candidate_households": item.get("candidate_households", 0),
            "location_known": item.get("location_known", 0),
            "person_found": item.get("person_found", 0),
            "communication_opportunity": item.get(
                "communication_opportunity", 0
            ),
            "contact_opportunity": item.get("contacts_considered", 0),
            "consider_request": item.get("need_events", 0),
            "request_sent": item.get("requests_sent", 0),
            "response_received": item.get("responses_received", 0),
            "accepted": item.get("accepted", 0),
            "current_delivery_commitments": item.get(
                "current_delivery_commitments", 0
            ),
            "willing_no_current_resource": item.get(
                "willing_no_current_resource", 0
            ),
            "conditional_promises": item.get("conditional_promises", 0),
            "promises_executed": item.get("promises_executed", 0),
            "promises_failed": item.get("promises_failed", 0),
            "current_commitment_failures": item.get(
                "current_commitment_failures", 0
            ),
            "rejected": item.get("rejected", 0),
            "executed": item.get("executed", 0),
            "accepted_not_executed": accepted_not_executed,
            "response_closure_error": (
                item.get("responses_received", 0) - response_parts
            ),
            "commitment_closure_error": (
                item.get("current_delivery_commitments", 0)
                - item.get("executed", 0)
                - accepted_not_executed
                - item.get("current_commitment_failures", 0)
            ),
            "not_continued_reasons": item.get(
                "not_continued_reasons", {}
            ),
        }
    return {
        "total_need_events": total_need_events,
        "sum_aid_need_events": sum(
            stats.get(name, {}).get("need_events", 0)
            for name in (
                "water",
                "food",
                "fire",
                "care",
                "shelter",
                "teaching",
            )
        ),
        "water": aid_stats("water"),
        "food": aid_stats("food"),
        "fire": aid_stats("fire"),
        "care": aid_stats("care"),
        "shelter": aid_stats("shelter"),
        "teaching": aid_stats("teaching"),
        "classification": "connected_to_integrated_loop",
    }
