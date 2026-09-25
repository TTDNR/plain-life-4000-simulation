"""Markdown reports for a versioned Phase 1 validation package."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .environment import WorldState, environment_summary
from .population import PopulationState
from .survival import SurvivalRunResult


def render_environment_report(
    world: WorldState,
    population: PopulationState,
    run_result: SurvivalRunResult,
    version: str,
) -> str:
    environment = environment_summary(world)
    climate = world.baseline.raw["climate"]
    resources = environment["resources"]
    ledgers = run_result.resource_ledger
    lines = [
        f"# 环境资源清单（{version}）",
        "",
        "本报告是版本化专项核验结果。`v1` 的秋季温带基线和失败报告保持独立，不被本版本覆盖。",
        "",
        "## 先纠正设定",
        "",
        "| 项目 | v1 | v2 | 处理说明 |",
        "| --- | --- | --- | --- |",
        "| 气候 | 温带泛滥平原，年均温约 13.25°C，年降雨约 795 mm | "
        "暖湿气候，年均温约 20.25°C，年降雨约 1460 mm | "
        "按已确认的暖湿环境修正，不只是改名 |",
        "| 投放季节 | 第 260 日，偏秋季坚果成熟期 | 第 90 日，暖季早期 | "
        "恢复到需求原有的暖季早期草案；变化列为修正，不作为提高通过率的调参 |",
        "| 集中投放 | 初始化阶段直接分布到 231 个营地 | 投放瞬间全部位于同一单元，"
        "首日探索后才自行选址 | 分开“投放瞬间”和“投放后行动”，迁移消耗白天时间 |",
        "| 知识 | 家庭技能集合直接共享 | 采集资格按实际人物技能判定，"
        "探索信息共享计入沟通时间 | 家庭成员不会自动同步见闻 |",
        "",
        "v2 没有以季节调整掩盖 v1 的失败；v1 的失败结论仍为：最初数日可行，"
        "最初数周以后失败，年度稳定供给失败。",
        "",
        "## 世界快照",
        "",
        f"- 世界标识：`{environment['world_id']}`",
        f"- 随机种子：`{environment['seed']}`",
        f"- 初始状态指纹：`{environment['fingerprint']}`",
        f"- 初始日：第 `{environment['start_day_of_year']}` 日",
        "- 网格：`100 x 50`，单元边长 `100 m`，总面积 `50 km²`",
        f"- 投放点：`({environment['drop_point']['x']}, "
        f"{environment['drop_point']['y']})`，距水 "
        f"`{environment['drop_point']['distance_to_water_km']} km`",
        f"- 投放瞬间营地数：`{run_result.migration_summary['drop_instant_camps']}`",
        f"- 首日探索和自行选址后的营地数："
        f"`{run_result.migration_summary['camps_after_day_one_selection']}`",
        f"- 试运行后的不同营地数：`{run_result.migration_summary['final_camps']}`",
        "",
        "专项试运行使用世界副本；初始世界指纹未被改写："
        f"`{run_result.initial_world_unchanged}`。",
        "",
        "## 暖湿气候核对",
        "",
        "| 月份 | 温度 °C | 降雨 mm | 蒸发 mm | 降雨日比例 |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for index in range(12):
        lines.append(
            f"| {index + 1} | {climate['temperature_c'][index]} | "
            f"{climate['rainfall_mm'][index]} | "
            f"{climate['evaporation_mm'][index]} | "
            f"{climate['rainy_day_fraction'][index]} |"
        )
    lines.extend(
        [
            "",
            f"- 年降雨：`{sum(climate['rainfall_mm'])} mm`。",
            f"- 年均温：`{sum(climate['temperature_c']) / 12:.2f}°C`。",
            "- 湿润生长季较长，仍有明显季节变化；冬季不是冻结气候，"
            "但降雨、蒸发、食物成熟和动物繁殖季节都参与逐日变化。",
            "- 气候参数仍是模型假设，MODEL 编号只表示内部可复算参数，"
            "不能作为现实地点依据。",
            "",
            "## 地形与土地",
            "",
            "| 土地类型 | 单元数 | 初始意义 |",
            "| --- | ---: | --- |",
        ]
    )
    land_meanings = {
        "water": "封闭地表水体，饮水和鱼类的来源",
        "wetland": "季节性积水，水生可食植物和纤维集中区",
        "floodplain": "肥力较高但存在洪水风险",
        "meadow": "可居住和可开垦地，浆果与纤维",
        "forest_edge": "林地与空地过渡区",
        "woodland": "木材和动物栖息地；坚果只在随后季节成熟",
        "upland": "坡度和排水较高，石材较多",
    }
    for land_class, count in environment["habitat_counts"].items():
        lines.append(
            f"| `{land_class}` | {count} | {land_meanings[land_class]} |"
        )
    lines.extend(
        [
            "",
            f"- 可居住单元：`{environment['habitable_cells']}`。",
            f"- 初始可开垦单元：`{environment['cultivable_cells']}`。",
            "- 土地肥力、排水、开垦成本和连续利用变化仍为模型假设，"
            "具体参数见 `environment_baseline.json`。",
            "",
            "## 淡水与封闭边界",
            "",
            f"- 初始地表水体积：`{environment['water']['surface_volume_m3']} m³`。",
            f"- 地表水容量：`{environment['water']['surface_capacity_m3']} m³`。",
            f"- 初始地下水储量：`{environment['water']['groundwater_m3']} m³`。",
            f"- 初始水质指数：`{environment['water']['quality']}`。",
            "- 降雨是唯一水量输入；蒸发和可选排水只作为输出。",
            "- 无外部鱼群、泥沙、种子或其他生物输入。",
            "- 同一单元格的边界尝试结果固定：不移动、不伤害、不提示。",
            "",
            "## 资源账目",
            "",
        "账目口径：期末存量 = 期初存量 + 新增量 - 采集或捕获量 "
        "- 自然损失 ± 地图内部转移。",
        f"本次账目来自一条连续世界副本，持续 `{run_result.days}` 天，"
        "没有把一个或多个副本的消耗混在一起。",
            "",
            "| 资源 | 期初 kg | 新增 kg | 采集/捕获 kg | 自然损失 kg | "
            "内部转移 kg | 期末 kg | 闭合误差 kg | 非负 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for resource_id, ledger in ledgers.items():
        lines.append(
            f"| `{resource_id}` | {ledger['opening_stock_kg']} | "
            f"{ledger['additions_kg']} | {ledger['harvested_kg']} | "
            f"{ledger['natural_loss_kg']} | "
            f"{ledger['internal_transfer_kg']} | "
            f"{ledger['closing_stock_kg']} | "
            f"{ledger['closure_error_kg']} | {ledger['non_negative']} |"
        )
    lines.extend(
        [
            "",
            "### 单位与再生语义",
            "",
            "| 资源 | 存量口径 | 可食比例 | 季节窗口 | 再生模型 |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for resource_id, resource in resources.items():
        season = resource["availability_day_range"]
        lines.append(
            f"| `{resource_id}` | `{resource['stock_basis']}` | "
            f"{resource['edible_yield_fraction']} | "
            f"{season[0]}–{season[1]} | "
            f"`{resource.get('regeneration_model', resource.get('growth_model', 'unspecified'))}` |"
        )
    lines.extend(
        [
            "",
            "- 植物存量是地图上的可食生物量；动物存量是活体重量。",
            "- 鱼类、鹿、兔和水禽的捕获量先按活体扣除，再乘 `edible_yield_fraction` "
            "进入家庭食物。",
            "- 本次试运行是一条连续世界副本；没有合并多个副本的消耗。",
            "- 地图内部迁移不复制资源；家庭之间的诊断性重分配不写入资源账，"
            "因此正式内部转移记录为零。",
            "- 植物年恢复比例在可取用季开始时只应用一次，不是每个时间步重复添加。",
            "- 成熟变化在初始化时决定期初状态，不记为再生新增；"
            "季节外的实际生物量增长才计入新增。",
            "- 鱼类不再从零库存自动恢复 1% 承载量；枯竭后只能通过实际存活生物量增长恢复。",
            "- 自然死亡、腐坏和采集前损失尚未实现，因此账表里的自然损失为零是"
            "声明中的模型缺口，不是完整生态结论。",
            "",
            "## 材料与加工",
            "",
            "| 材料 | 初始存量 kg | 承载量 kg | 年更新比例 | 证据 |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for material_id, item in environment["materials"].items():
        lines.append(
            f"| `{material_id}` | {item['stock_kg_at_start']} | "
            f"{item['capacity_kg']} | {item['renewal_fraction_per_year']} | "
            f"`{', '.join(item['evidence'])}` |"
        )
    lines.extend(
        [
            "",
            "## 依据、假设与待验证项",
            "",
            "### 需求依据",
            "",
            "- 50 平方公里封闭世界，环境先于人物。",
            "- 暖湿环境，暖季早期为默认投放草案。",
            "- 降雨为输入，蒸发和排水只能为输出。",
            "- 人物需要承担饮水、食物、遮蔽、火、工具、储存和协作的实际成本。",
            "",
            "### 模型假设",
            "",
            "- 气候和气候的长期值属于 v2 参数化草案。",
            "- 物种产量、热值、可食比例、加工失败率和捕获率属于内部假设。",
            "- 地下水和地表水的容量、径流、污染稀释属于内部假设。",
            "- 所有 MODEL-* 编号都表示模型参数，不是现实证据。",
            "",
            "### 待验证",
            "",
            "- 暖湿气候参数需要由明确地点或气候类别确认。",
            "- 每个资源产量、恢复、加工和捕获参数需要独立参数试验。",
            "- 水质污染传播仍是简化模型。",
            "- 连续使用土地的变化没有接入正式农业和定居过程。",
            "",
            "## 机器可检查依据",
            "",
            f"- 环境指纹：`{world.initial_fingerprint}`",
            f"- 人口指纹：`{population.fingerprint}`",
            f"- 试运行类型：`{run_result.test_kind}`",
            "- 原始参数：`data/phase1/versions/v2/environment_baseline.json`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_survival_report(
    run_result: SurvivalRunResult,
    version: str,
) -> str:
    windows = run_result.window_results
    paths = run_result.path_results
    all_windows_pass = run_result.days >= 365 and all(
        item["status"] == "evaluated" for item in windows.values()
    )
    lines = [
        f"# 开局生存核验报告（{version}）",
        "",
        f"试运行类型：`{run_result.test_kind}`。这是一项固定人口需求压力测试，"
        "不代表这些人真实存活了一年。",
        "",
        "当前模型没有把饥饿、感染、伤害和死亡反馈到体重、劳动能力或人口需求。"
        "因此本报告不能被称为动态生存测试，也不能宣称已有完整年度生存结论。",
        "",
        (
            "年度检查未通过。"
            if run_result.days >= 365 and not all_windows_pass
            else "当前只覆盖部分时间窗，不能视为年度结论。"
            if run_result.days < 365
            else "当前年度检查通过。"
        ),
        "",
        "## 时间窗与满足率口径",
        "",
        "`平均食物满足率` 是每日实际消费热量除以固定人口需求后，再按日平均。"
        "`最低食物满足率` 是最困难的单个家庭日，不是全体人口平均值。"
        "`P10 家庭满足率` 展示最困难十分之一家庭的水平。",
        "",
        "| 时间窗 | 结果 | 平均食物满足率 | 最低家庭日满足率 | "
        "P10 家庭满足率 | 最低饮水满足率 | 低于 80% 的家庭日 | "
        "最长连续不足 80% |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for window_id, item in windows.items():
        lines.append(
            f"| `{window_id}` | {item['status']} | "
            f"{item['average_food_ratio']} | "
            f"{item['minimum_household_food_ratio']} | "
            f"{item['p10_household_food_ratio']} | "
            f"{item['minimum_water_ratio']} | "
            f"{item['days_with_household_min_below_080']} | "
            f"{item['longest_consecutive_household_min_below_080']} |"
        )
    lines.extend(
        [
            "",
            "## 需求链结果",
            "",
            "| 需求链 | 结果 | 路径或失败原因 |",
            "| --- | --- | --- |",
        ]
    )
    for path_id, item in paths.items():
        lines.append(
            f"| `{path_id}` | {item['status']} | {item['solution']} |"
        )
    household_total = run_result.acquisition_paths["time_models"][
        "household_count"
    ]
    lines.extend(
        [
            "",
            "## 无容器饮水路径",
            "",
            f"- 第 1 日：`{run_result.acquisition_paths['water']['day_one_method']}`。",
            f"- 第 2 日起：`{run_result.acquisition_paths['water']['later_method']}`。",
            f"- 已建造携带容器的家庭："
            f"`{run_result.acquisition_paths['water']['container_built_households']} / "
            f"{household_total}`。",
            f"- 最小容器容量："
            f"`{run_result.acquisition_paths['water']['minimum_container_capacity_l']} L`。",
            "- 送水不是自动入仓：每次取水都计算到水源的往返时间，"
            "并使用纤维和木材制作的实际携带容器。",
            "- 行动受限者和婴幼儿由照护者带到水边或用水具带回；"
            "缺少容器时没有隐藏的家庭水库存。",
            "",
            "## 初期食物加工路径",
            "",
            "| 资源 | 活体/存量扣除 kg | 可食食物 kg | 可食热量 kcal | "
            "采集小时 | 加工小时 | 行程小时 | 加工失败次数 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for resource_id, item in run_result.harvest_details.items():
        if item["stock_kg_removed"] <= 0.0 and item["processing_attempts"] == 0:
            continue
        lines.append(
            f"| `{resource_id}` | {item['stock_kg_removed']} | "
            f"{item['edible_food_kg']} | {item['edible_kcal']} | "
            f"{item['harvest_hours']} | {item['processing_hours']} | "
            f"{item['travel_hours']} | {item['processing_failures']} |"
        )
    lines.extend(
        [
            "",
            "- 橡子和水生地下部分不是原料公斤直接等于热量；"
            "表中已经扣除获取时间、加工时间和加工失败。",
            "- 加工失败会消耗实际采集到的原料，但不会产生可食热量。",
            "",
            "## 遮蔽、火和工具",
            "",
            f"- 遮蔽完成家庭："
            f"`{run_result.acquisition_paths['shelter']['households_completed']}`，"
            f"中位完成日："
            f"`{run_result.acquisition_paths['shelter']['median_completion_day']}`。",
            f"- 火首次成功家庭："
            f"`{run_result.acquisition_paths['fire']['households_completed']}`，"
            f"中位成功日："
            f"`{run_result.acquisition_paths['fire']['median_completion_day']}`。",
            f"- 工具达到可用阈值家庭："
            f"`{run_result.acquisition_paths['tools']['households_completed']}`，"
            f"中位完成日："
            f"`{run_result.acquisition_paths['tools']['median_completion_day']}`。",
            "- 每次遮蔽、取火和工具尝试都消耗实际材料和劳动时间。",
            "",
            "## 分配对照",
            "",
            "以下对照仅用于诊断，不能写入正式人物行为。",
            "",
            "| 对照 | 失败天数 | 说明 |",
            "| --- | ---: | --- |",
            f"| 当前基础行为 | "
            f"{run_result.distribution_diagnostics['costless_redistribution']['basic_failure_days']} | "
            "家庭独立仓库和当前基础行为 |",
            f"| 食物无成本重新分配上限 | "
            f"{run_result.distribution_diagnostics['costless_redistribution']['ideal_upper_bound_failure_days']} | "
            "只用于拆分分配问题，不代表可实现方案 |",
            f"| 受 1 km 距离和 20% 损失约束的协作 | "
            f"{run_result.distribution_diagnostics['constrained_cooperation']['failure_days']} | "
            "诊断性最小协作，不是正式经济或信任系统 |",
            "",
            "- 仅由理想分配可消除的不足天数："
            f"`{run_result.distribution_diagnostics['costless_redistribution']['distribution_only_failure_days']}`。",
            "- 即使无成本重新分配后仍不足的天数："
            f"`{run_result.distribution_diagnostics['costless_redistribution']['residual_supply_or_labor_failure_days']}`。",
            "- 因此不能预设“缺少合作是主要原因”；必须同时报告总供给、劳动时间、"
            "加工能力、可达范围和分配不均的各自贡献。",
            "",
            "## 必须保留的测试限制",
            "",
            "- 家庭内部食物共享是当前基线假设，尚未实现有差异、可拒绝和会冲突的"
            "家庭成员分配行为。",
            "- 家庭之间没有自动交换或信任形成规则。",
            "- 没有体重变化、失能、疾病、死亡和劳动能力衰减。",
            "- 迁移决策是有限信息下的规则诊断，不代表完整人物心理模型。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_initialization_report(
    population: PopulationState,
    run_result: SurvivalRunResult,
    audit_findings: list[Mapping[str, Any]],
    version: str,
    gate_status: str,
) -> str:
    summary = population.summary()
    all_blockers = [
        finding
        for finding in audit_findings
        if finding["severity"] == "blocker"
    ]
    population_blockers = [
        finding
        for finding in all_blockers
        if finding["section"] == "initialization"
    ]
    lines = [
        f"# 初始化一致性检查报告（{version}）",
        "",
        f"人口指纹：`{population.fingerprint}`。",
        "",
        "## 总体结果",
        "",
        f"- 人口数量：`{summary['actual_total']} / {summary['target_total']}`。",
        f"- 家庭数量：`{summary['households']}`。",
        f"- 亲属关系边：`{summary['kinship_edges']}`。",
        f"- 妊娠记录：`{summary['pregnancy_events']}`，其中持续妊娠 "
        f"`{summary['ongoing_pregnancies']}`。",
        f"- 哺乳关系：`{summary['lactation_links']}`。",
        f"- 婴儿：`{summary['infants']}`，有照护者："
        f"`{summary['infants_with_caregiver']}`。",
        f"- 人口内部阻断项：`{len(population_blockers)}`；"
        f"全部审计阻断项：`{len(all_blockers)}`。",
        "",
        "人口内部结构通过不等于 Phase 1 整体通过。当前整体门禁状态为 "
        f"`{gate_status}`：见下方阻断证据。",
        "",
        "## 年龄与家庭",
        "",
        "| 年龄阶段 | 人数 |",
        "| --- | ---: |",
    ]
    for age_band, count in summary["age_bands"].items():
        lines.append(f"| `{age_band}` | {count} |")
    lines.extend(
        [
            "",
            "| 家庭人数 | 家庭数 |",
            "| ---: | ---: |",
        ]
    )
    for size, count in sorted(
        summary["household_sizes"].items(), key=lambda item: int(item[0])
    ):
        lines.append(f"| {size} | {count} |")
    lines.extend(
        [
            "",
            "- 家庭角色、年龄、亲子和伴侣关系在同一初始化过程中生成。",
            "- 婴儿都有照护者、活产事件和哺乳关系。",
            "- v2 不再把家庭技能集合自动视为个人知识；采集资格按实际成员技能判断。",
            "- 家庭内部当前仍有共同食物仓库假设。有差异、可拒绝、会冲突的"
            "家庭分配行为尚未定义，因此不能把这份人口快照当作完整家庭行为验收结果。",
            "",
            "## 技能与经历",
            "",
            "| 技能 | 持有人数 |",
            "| --- | ---: |",
        ]
    )
    for skill_id, count in summary["skill_counts"].items():
        lines.append(f"| `{skill_id}` | {count} |")
    lines.extend(
        [
            "",
            "- 技能有学习来源、练习次数和熟练度。",
            "- 个人技能不会被自动复制给家庭成员。",
            "- 探索信息按人物保存；家庭层面只在明确计入沟通时间后形成共享视图。",
            "",
            "## 照护与劳动",
            "",
            f"- 依赖人口：`{summary['dependent_people']}`。",
            f"- 可基础劳动的成年人或老年人：`{summary['active_people']}`。",
            f"- 承担照护责任的人：`{summary['caregiver_people']}`。",
            "- 照护、探索沟通和迁移往返都会扣除家庭可用劳动时间。",
            "",
            "## 全部审计阻断项与证据",
            "",
            "| 阻断项 | 证据位置 | 说明 |",
            "| --- | --- | --- |",
        ]
    )
    for finding in all_blockers:
        lines.append(
            f"| `{finding['code']}` | `{finding['path']}` | "
            f"{finding['message']} |"
        )
    lines.extend(
        [
            "",
            "## 与环境的相容性",
            "",
            "- 饮水、食物、遮蔽、火和工具的专项路径结果见"
            " `OPENING_SURVIVAL_REVIEW.md`。",
            "- 资源账目和非负检查见 `ENVIRONMENT_RESOURCE_INVENTORY.md`。",
            "- 在动态身体后果和家庭分配需求补齐前，不通过初始化与生态相容性验收。",
            "",
            "## 结论",
            "",
            "内部引用一致，但整体仍被生存、资源账或行为缺口阻断。"
            "当前结果只能作为固定人口压力测试和需求诊断，不能启动正式长期模拟。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
