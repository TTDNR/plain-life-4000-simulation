# 初始化一致性检查报告（v3）

人口指纹：`5c27aa772c4d3151db0fcf6eb2890335a2ef084ba898491a46867b134548763e`。

## 总体结果

- 人口数量：`4000 / 4000`。
- 家庭数量：`1000`。
- 亲属关系边：`2093`。
- 妊娠记录：`100`，其中持续妊娠 `30`。
- 哺乳关系：`70`。
- 婴儿：`70`，有照护者：`70`。
- 人口内部一致性阻断项：`0`；行为能力阻断项：`3`；全部审计阻断项：`12`。

人口内部结构和亲属引用通过，不等于身体与行为能力已经完成。当前整体门禁状态为
`BLOCKED`：见下方阻断证据。

## 年龄与家庭

| 年龄阶段 | 人数 |
| --- | ---: |
| `under_1` | 70 |
| `age_1_4` | 230 |
| `age_5_12` | 375 |
| `age_13_17` | 250 |
| `age_18_44` | 1942 |
| `age_45_64` | 725 |
| `age_65_plus` | 408 |

| 家庭人数 | 家庭数 |
| ---: | ---: |
| 1 | 80 |
| 2 | 120 |
| 3 | 180 |
| 4 | 220 |
| 5 | 230 |
| 6 | 100 |
| 7 | 50 |
| 8 | 20 |

- 家庭角色、年龄、亲子和伴侣关系在同一初始化过程中生成。
- 婴儿都有照护者、活产事件和哺乳关系。
- v3 不再把家庭技能集合自动视为个人知识；采集资格按实际成员技能判断。
- 家庭内部当前仍有共同食物仓库假设。有差异、可拒绝、会冲突的家庭分配行为尚未定义，因此不能把这份人口快照当作完整家庭行为验收结果。

## 技能与经历

| 技能 | 持有人数 |
| --- | ---: |
| `basic_plant_identification` | 2888 |
| `water_finding` | 2570 |
| `water_safety` | 1479 |
| `fire_keeping` | 559 |
| `fire_friction` | 284 |
| `shelter_building` | 1163 |
| `stone_tool_making` | 590 |
| `wood_working` | 911 |
| `fiber_cordage` | 999 |
| `wetland_plant_knowledge` | 1737 |
| `tree_food_knowledge` | 1740 |
| `acorn_processing` | 1325 |
| `fishing` | 989 |
| `hunting_or_trapping` | 684 |
| `cooking` | 2392 |
| `childcare` | 2254 |

- 技能有学习来源、练习次数和熟练度。
- 个人技能不会被自动复制给家庭成员。
- 探索信息按人物保存；家庭层面只在明确计入沟通时间后形成共享视图。

## 照护与劳动

- 依赖人口：`675`。
- 可基础劳动的成年人或老年人：`2941`。
- 承担照护责任的人：`905`。
- 照护、探索沟通和迁移往返都会扣除家庭可用劳动时间。

## 全部审计阻断项与证据

| 阻断项 | 证据位置 | 说明 |
| --- | --- | --- |
| `window_failed` | `survival.windows.initial_days.status` | The evaluated time window did not pass its survival checks. |
| `window_failed` | `survival.windows.initial_weeks.status` | The evaluated time window did not pass its survival checks. |
| `window_failed` | `survival.windows.first_season_transition.status` | The evaluated time window did not pass its survival checks. |
| `window_failed` | `survival.windows.first_year_plus.status` | The evaluated time window did not pass its survival checks. |
| `path_failed` | `survival.paths.water.status` | The evaluated survival path did not pass against the environment. |
| `path_failed` | `survival.paths.food.status` | The evaluated survival path did not pass against the environment. |
| `path_failed` | `survival.paths.shelter.status` | The evaluated survival path did not pass against the environment. |
| `path_failed` | `survival.paths.fire.status` | The evaluated survival path did not pass against the environment. |
| `path_failed` | `survival.paths.stable_supply.status` | The evaluated survival path did not pass against the environment. |
| `dynamic_body_consequences_missing` | `survival.test_kind` | The annual result is a fixed-demand pressure test and does not update body condition, labor, or mortality. |
| `household_food_allocation_rules_missing` | `population.behavior_gaps.household_food_allocation` | Family members currently share a household food pool; differential, refusable, and conflicting allocation is not implemented. |
| `interhousehold_exchange_rules_missing` | `population.behavior_gaps.interhousehold_exchange` | Food, fire, care, and knowledge exchange between households is not a formal behavior; only diagnostic comparisons exist. |

## 与环境的相容性

- 饮水、食物、遮蔽、火和工具的专项路径结果见 `OPENING_SURVIVAL_REVIEW.md`。
- 资源账目和非负检查见 `ENVIRONMENT_RESOURCE_INVENTORY.md`。
- 在动态身体后果和家庭分配需求补齐前，不通过初始化与生态相容性验收。

## 结论

内部引用一致，但整体仍被生存、资源账或行为缺口阻断。当前结果只能作为固定人口压力测试和需求诊断，不能启动正式长期模拟。
