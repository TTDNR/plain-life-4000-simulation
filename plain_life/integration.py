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
    )
    return {
        "version": "v3",
        "diagnostic_type": "seven_day_integrated_opening_diagnostic",
        "formal_history": False,
        "long_term_conclusion_allowed": False,
        "days": 7,
        "population": population.summary(),
        "integration": run.integration_diagnostics,
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
        },
        "food_by_window": run.acquisition_paths["food_by_window"],
        "food_annual": run.acquisition_paths["food"],
        "resource_ledger": run.resource_ledger,
        "daily_metrics": [asdict(metric) for metric in run.metrics],
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
        f"- 最低劳动能力：`{integration['minimum_work_capacity']}`。",
        f"- 平均劳动能力：`{integration['mean_work_capacity']}`。",
        f"- 饥饿达到模型上限人数：`{integration['people_with_hunger_at_cap']}`。",
        f"- 口渴达到模型上限人数：`{integration['people_with_thirst_at_cap']}`。",
        f"- 最终劳动能力低于 0.5 的人数："
        f"`{integration['people_capacity_limited_on_final_day']}`。",
        f"- 累计能量余额：`{integration['total_energy_balance_kcal']}` kcal。",
        "",
        "模型没有死亡阈值；死亡人数显示为零，状态为 `death_modeled=false`。"
        "疾病也未被建模，因此不能解释为没有疾病风险。",
        "",
        "## 个人时间使用",
        "",
        "| 类别 | 家庭小时 |",
        "| --- | ---: |",
    ]
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
            "## 未自然发生的行动",
            "",
            f"- 跨家庭食物请求：`{result['social_actions']['interhousehold_food_requests']}`。",
            f"- 完成食品转移：`{result['social_actions']['completed_food_transfers']}`。",
            f"- 教学事件：`{result['social_actions']['teaching_events']}`。",
            f"- 临时同住：`{result['social_actions']['temporary_cohabitation_events']}`。",
            "",
            result["social_actions"]["note"],
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
