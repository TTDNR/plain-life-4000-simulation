# v2 Phase 1 审计

## 门禁

`BLOCKED`

## 阻断项与证据

| 编号 | 阻断项 | 证据位置 | 当前证据 |
| ---: | --- | --- | --- |
| 1 | `window_failed` | `survival.windows.initial_days.status` | 平均食物满足率 0.5628，最低家庭日 0.0 |
| 2 | `window_failed` | `survival.windows.initial_weeks.status` | 平均食物满足率 0.0282，39 天存在最低家庭值低于 0.8 |
| 3 | `window_failed` | `survival.windows.first_season_transition.status` | 平均食物满足率 0.0631，138 天存在最低家庭值低于 0.8 |
| 4 | `window_failed` | `survival.windows.first_year_plus.status` | 平均食物满足率 0.0066，185 天存在最低家庭值低于 0.8 |
| 5 | `path_failed` | `survival.paths.food.status` | 总地图库存和可食转换后仍无法覆盖固定需求 |
| 6 | `path_failed` | `survival.paths.shelter.status` | 859/1000 家庭达到完成阈值，未达到要求覆盖 |
| 7 | `path_failed` | `survival.paths.fire.status` | 中位首次成功日为第 276 日，无法满足早期用火 |
| 8 | `path_failed` | `survival.paths.stable_supply.status` | 四个时间窗均失败 |
| 9 | `natural_loss_model_missing` | `resource_ledger.*.natural_loss_kg` | 自然死亡、腐坏和采集前损失未实现，零值是缺口 |
| 10 | `dynamic_body_consequences_missing` | `survival.test_kind` | 固定人口需求压力测试，没有体重、失能、死亡反馈 |
| 11 | `household_food_allocation_rules_missing` | `population.behavior_gaps.household_food_allocation` | 家庭仍使用共享食物池，缺少差异、拒绝和冲突 |
| 12 | `interhousehold_exchange_rules_missing` | `population.behavior_gaps.interhousehold_exchange` | 家庭间食物、火种、照护和知识交换未定义 |

完整机器结果位于 `artifacts/phase1/versions/v2/phase1_audit.json`。
