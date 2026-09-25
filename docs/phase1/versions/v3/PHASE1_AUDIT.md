# v3 Phase 1 审计

## 门禁

`BLOCKED`

## 阻断项与证据

| 编号 | 阻断项 | 证据位置 | 当前证据 |
| ---: | --- | --- | --- |
| 1 | `window_failed` | `survival.windows.initial_days.status` | 平均食物满足率约 0.56 |
| 2 | `window_failed` | `survival.windows.initial_weeks.status` | 平均食物满足率约 0.03 |
| 3 | `window_failed` | `survival.windows.first_season_transition.status` | 平均食物满足率约 0.06 |
| 4 | `window_failed` | `survival.windows.first_year_plus.status` | 平均食物满足率约 0.01 |
| 5 | `path_failed` | `survival.paths.water.status` | 最低饮水满足率约 0.60，水具成功 182/1000 |
| 6 | `path_failed` | `survival.paths.food.status` | 固定需求不能被实际劳动和加工路径覆盖 |
| 7 | `path_failed` | `survival.paths.shelter.status` | 遮蔽覆盖约 3373/4000 人 |
| 8 | `path_failed` | `survival.paths.fire.status` | 中位成功在投放后第 280 日，太晚 |
| 9 | `path_failed` | `survival.paths.stable_supply.status` | 四个时间窗均失败 |
| 10 | `dynamic_body_consequences_missing` | `survival.test_kind` | 年度仍是固定需求压力测试，没有死亡和劳动衰减反馈 |
| 11 | `household_food_allocation_rules_missing` | `population.behavior_gaps.household_food_allocation` | 短场景已实现，年度人口尚未接入差异分配 |
| 12 | `interhousehold_exchange_rules_missing` | `population.behavior_gaps.interhousehold_exchange` | 短场景已实现请求与回应，年度人口尚未接入 |

## 不是阻断项

- 14 类资源账全部闭合且非负。
- 植物过季损失已记录；动物净增长语义已明确。
- 个人时间账闭合误差低于 `0.001` 小时。
- 8 个第一批和第二批基础短场景通过。

