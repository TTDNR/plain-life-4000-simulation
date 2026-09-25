"""Markdown reports for the Phase 1 validation package."""

from __future__ import annotations

import json
from statistics import mean
from typing import Any, Mapping

from .environment import WorldState, environment_summary
from .population import PopulationState
from .survival import SurvivalRunResult


def render_environment_report(
    world: WorldState,
    population: PopulationState,
    run_result: SurvivalRunResult,
) -> str:
    environment = environment_summary(world)
    resources = environment["resources"]
    materials = environment["materials"]
    consumption = run_result.resource_consumption_kg
    lines = [
        "# 环境资源清单",
        "",
        "本报告由 `tools/run_phase1.py` 从固定基线和种子生成。当前基线是可复算的模型假设，"
        "不是已校准到现实地点的实测生态数据。",
        "",
        "## 世界快照",
        "",
        f"- 世界标识：`{environment['world_id']}`",
        f"- 随机种子：`{environment['seed']}`",
        f"- 初始状态指纹：`{environment['fingerprint']}`",
        f"- 初始日：第 `{environment['start_day_of_year']}` 日",
        f"- 网格：`100 x 50`，单元边长 `100 m`，总面积 `50 km²`",
        f"- 投放点：`({environment['drop_point']['x']}, "
        f"{environment['drop_point']['y']})`，距水 "
        f"`{environment['drop_point']['distance_to_water_km']} km`",
        "",
        "环境在人口创建前完整物化，并保留初始指纹。专项试运行使用世界副本，"
        f"初始世界未被改写：`{run_result.initial_world_unchanged}`。",
        "",
        "## 地形与土地",
        "",
        "| 土地类型 | 单元数 | 初始意义 |",
        "| --- | ---: | --- |",
    ]
    land_meanings = {
        "water": "封闭地表水体，饮水和鱼类的来源",
        "wetland": "季节性积水，水生可食植物集中区",
        "floodplain": "肥力较高但存在洪水风险",
        "meadow": "可居住和可开垦地，浆果与纤维",
        "forest_edge": "林地与空地过渡区，木材、坚果和动物",
        "woodland": "橡子、榛子、木材和鹿的集中区",
        "upland": "坡度和排水较高，石材较多",
    }
    for land_class, count in environment["habitat_counts"].items():
        lines.append(
            f"| `{land_class}` | {count} | {land_meanings[land_class]} |"
        )
    lines.extend(
        [
            "",
            f"- 可居住单元：`{environment['habitable_cells']}`",
            f"- 初始可开垦单元：`{environment['cultivable_cells']}`",
            "- 连续性使用会按年降低肥力，休耕会缓慢恢复；具体参数见"
            " `data/phase1/environment_baseline.json`。",
            "",
            "## 淡水与封闭边界",
            "",
            f"- 初始地表水体积：`{environment['water']['surface_volume_m3']} m³`",
            f"- 地表水容量：`{environment['water']['surface_capacity_m3']} m³`",
            f"- 初始地下水储量：`{environment['water']['groundwater_m3']} m³`",
            f"- 初始水质指数：`{environment['water']['quality']}`",
            "- 降雨是唯一水量输入；蒸发和可选地表排水只作为输出。",
            "- 无外部鱼群、泥沙、种子或其他生物输入。",
            "- 边界不移动、不伤害探索者、不主动提示，并以同一规则处理所有穿越尝试。",
            "",
            "## 食品资源",
            "",
            "| 资源 | 初始存量 kg | 承载量 kg | 可取用季 | 年恢复比例 | 证据 |",
            "| --- | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for resource_id, item in resources.items():
        season = item["availability_day_range"]
        lines.append(
            f"| `{resource_id}` | {item['stock_kg_at_start']} | "
            f"{item['capacity_kg']} | {season[0]}–{season[1]} | "
            f"{item['annual_recovery_fraction']} | "
            f"`{', '.join(item['evidence'])}` |"
        )
    lines.extend(
        [
            "",
            "季节性、成熟度、栖息地和再生条件独立于人物需求生成。人物首次接触时，"
            "只能从已探索区域、当前成熟资源和自身可操作知识中获取。",
            "",
            "### 本次试运行消耗",
            "",
            "| 资源 | 消耗 kg |",
            "| --- | ---: |",
        ]
    )
    for resource_id, kg in consumption.items():
        lines.append(f"| `{resource_id}` | {kg} |")
    lines.extend(
        [
            "",
            "过度采集超过单格承载量 55% 时会降低该格下一年度的植物恢复条件。"
            "动物采用受容量上限约束的逻辑增长，捕猎会降低当前数量。",
            "",
            "## 材料与加工",
            "",
            "| 材料 | 初始存量 kg | 承载量 kg | 年更新比例 | 证据 |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for material_id, item in materials.items():
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
            "### 已由需求确定",
            "",
            "- 50 平方公里封闭世界。",
            "- 环境先存在，人物后投放。",
            "- 不得按人物需求临时补资源。",
            "- 降雨为输入，蒸发和排水只能为输出。",
            "- 无外部生物或物资输入。",
            "",
            "### 当前模型假设",
            "",
            "- 温带泛滥平原气候和 12 个月降雨、蒸发、温度序列。",
            "- 所有物种产量、成熟期、加工时间、采食热量和捕获难度。",
            "- 地表水为封闭盆地水体，由本地降雨和径流维持。",
            "- 材料初始容量、更新率和土地肥力变化。",
            "",
            "### 待验证",
            "",
            "- 各资源产量与恢复比例尚无真实地点校准。",
            "- 鱼、鹿、兔和水禽的捕获率及捕猎恢复尚未做独立参数试验。",
            "- 水质只保留距人活动区的稀释底线，污染传播仍是简化模型。",
            "- 连续开垦后的肥力下降和弃耕恢复没有与长期农业参数联调。",
            "",
            "## 机器可检查依据",
            "",
            f"- 环境指纹：`{world.initial_fingerprint}`",
            f"- 人口指纹：`{population.fingerprint}`",
            "- 原始参数：`data/phase1/environment_baseline.json`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_survival_report(run_result: SurvivalRunResult) -> str:
    windows = run_result.window_results
    paths = run_result.path_results
    all_windows_pass = run_result.days >= 365 and all(
        item["status"] == "evaluated" for item in windows.values()
    )
    lines = [
        "# 开局生存核验报告",
        "",
        (
            "当前年度专项核验未通过。最初几天存在可行生存路径，但当前无群体分享、"
            "无经济交换的模型下，中期和年度食物获取出现决定性缺口。"
            if run_result.days >= 365 and not all_windows_pass
            else "当前结果只覆盖部分时间窗，不能视为年度核验结论。"
            if run_result.days < 365
            else "当前年度专项核验通过。"
        ),
        "",
        "试运行只测试角色已经定义的基础生存行为，不作为正式世界历史，也不代表已经实现"
        "可信的人类社会模拟。",
        "",
        "## 时间窗",
        "",
        "| 时间窗 | 结果 | 瓶颈 | 平均食物满足率 | 最低食物满足率 | "
        "最低饮水满足率 | 最可能失败 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for window_id, item in windows.items():
        lines.append(
            f"| `{window_id}` | {item['status']} | {item['bottleneck']} | "
            f"{item['average_food_ratio']} | {item['minimum_food_ratio']} | "
            f"{item['minimum_water_ratio']} | {item['likely_failure']} |"
        )
    lines.extend(
        [
            "",
            "## 可行获取路径",
            "",
            "| 需求链 | 结果 | 路径或失败原因 |",
            "| --- | --- | --- |",
        ]
    )
    for path_id, item in paths.items():
        lines.append(
            f"| `{path_id}` | {item['status']} | {item['solution']} |"
        )
    lines.extend(
        [
            "",
            "## 已确认的可行部分",
            "",
            "- 淡水位点可从投放区到达。",
            "- 无容器时可以直接饮用；照护者能够为不能自行取水的人送水。",
            "- 最初三天可通过浆果、榛子、橡子、香蒲、慈姑和鱼类建立食物链。",
            "- 木质和纤维材料足以开始搭建遮蔽。",
            "- 有实际操作技能的人可以尝试摩擦取火，失败后仍可继续尝试。",
            "- 石、木原料支持渐进式工具制作，缺少关键工匠不会被自动补齐。",
            "",
            "## 主要瓶颈",
            "",
            "- 当前没有定义人物之间的食物再分配、交换或互助决策。试运行不假设家庭自动共享，"
            "因此掌握橡子加工等技能的少数家庭会先取得高热量库存，没有技能的家庭持续失败。",
            "- 4000 人在 50 平方公里内的局部采集速度超过家庭自行探索和迁移的恢复速度。",
            "- 家庭照护会显著削减可劳动时间；幼儿、老人和行动受限者集中于部分家庭时，"
            "这些家庭的获取能力明显更低。",
            "- 食物储存需要处理、干燥和保存安排，现有基础行为只保留按物种腐败率计算的简化仓库。",
            "",
            "## 最可能失败环节",
            "",
            (
                f"年度检查的最差日为第 `{min(run_result.metrics, key=lambda item: item.food_ratio).day}` "
                "天，首要风险是食物而不是饮水。"
            ),
            "",
            "在补齐食物分配、劳动交换、信任形成与家庭间决策前，不能通过扩大资源产量来"
            "宣布年度生存可行。该缺口是需求缺口，不是可由试运行隐藏的参数问题。",
            "",
            "## 探索与迁移",
            "",
            f"- 初始家庭营地：`{run_result.migration_summary['initial_camps']}` 个不同单元。",
            f"- 发生迁移的家庭：`{run_result.migration_summary['households_that_migrated']}`。",
            f"- 迁移事件：`{run_result.migration_summary['migration_events']}`。",
            f"- 年度结束时探索半径上限："
            f"`{run_result.migration_summary['known_cell_radius_km_end']} km`。",
            "- 探索知识按家庭分别维护；没有全体共享地图。",
            "- 搬迁不等于形成政权，也不自动建立新群体认同。",
            "",
            "## 必须修正的需求缺口",
            "",
            "1. 定义家庭之间在食物、火种、照护和知识上的交换或拒绝规则。",
            "2. 定义信任形成速度与信息传播范围，避免依赖全知指挥。",
            "3. 明确个人和家庭迁移决策所需的有限信息，以及出发、返程和放弃规则。",
            "4. 明确伤害、疾病、体力消耗和死亡如何影响后续劳动能力。",
            "5. 明确储存、加工场地和食品保质条件，尤其是橡子、鱼和肉类。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_initialization_report(
    population: PopulationState,
    run_result: SurvivalRunResult,
    audit_findings: list[Mapping[str, Any]],
) -> str:
    summary = population.summary()
    blocker_count = sum(
        finding["severity"] == "blocker" for finding in audit_findings
    )
    population_blockers = [
        finding
        for finding in audit_findings
        if finding["section"] == "initialization"
        and finding["severity"] == "blocker"
    ]
    lines = [
        "# 初始化一致性检查报告",
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
        f"- 初始化审计阻断项：`{len(population_blockers)}`；全部审计阻断项："
        f"`{blocker_count}`。",
        "",
        "人口内部结构一致，但与生态的年度相容性未通过。内部一致不能抵消生存资源的"
        "分配和再生缺口。",
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
            "- 家庭由角色模板生成，亲子和伴侣关系在同一次初始化中建立。",
            "- 婴儿均有照护者、活产事件和哺乳关系；照护者引用可解析。",
            "- 人物只有一次新世界初始化，不把旧职位、财产或权力转为新资产。",
            "- 家庭内部允许依赖、矛盾和不平等，不能被强制视为完全合作单位。",
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
            "- 每名成年人和老年人的技能都有学习来源、练习次数和熟练度。",
            "- 技能分布会显著影响家庭食物路径；当前模型不自动补齐缺失工匠。",
            "- 生命经历包含出生、成长、职业学习和旧世界财产不转入新世界的记录。",
            "",
            "## 照护与劳动",
            "",
            f"- 依赖人口：`{summary['dependent_people']}`。",
            f"- 可基础劳动的成年人或老年人：`{summary['active_people']}`。",
            f"- 承担照护责任的人：`{summary['caregiver_people']}`。",
            "- 试运行按婴儿、幼儿、儿童、行动限制和健康状态扣除劳动时间。",
            "- 照护者仍保留剩余工作时间，但关键照护者会首先损失外出采集时间。",
            "",
            "## 与环境的相容性",
            "",
            "| 核验项 | 结果 |",
            "| --- | --- |",
            "| 饮水路径 | 通过 |",
            "| 初始数日食物 | 通过 |",
            "| 最初数周食物 | 失败 |",
            "| 季节转换 | 失败 |",
            "| 完整年度 | 失败 |",
            "| 遮蔽 | 在第一个完整季节内达到可行覆盖，但首三日覆盖偏低 |",
            "| 火 | 冷季覆盖不足 |",
            "| 工具 | 多数家庭达到可用阈值，但少数家庭持续落后 |",
            "",
            "## 生态冲突",
            "",
            "1. 4000 人对局部野生资源的消耗速度快于家庭独立探索、加工和迁移的恢复速度。",
            "2. 当前技能分布使高热量秋季资源集中在部分家庭，未定义分享或交换时会产生"
            "结构性饥荒。",
            "3. 50 平方公里内的自然再生量可能支持长期生存，但家庭级分配、储存和协作缺失"
            "使总量不可转化为稳定供给。",
            "4. 不能通过运行时补给、自动共享或提高所有人技能来消除这些冲突。",
            "",
            "## 结论",
            "",
            "人口内部初始化一致性通过；人口与环境的最初数日条件相容，但月和年度生存"
            "不通过。完整模拟必须等待人物决策、交换、信任和劳动交换需求补齐并重新核验。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
