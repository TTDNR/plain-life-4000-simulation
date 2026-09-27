# S01 第一条真实生活链：移动到水源并饮水

这是 `integration_fixture`，不是正式历史，也不代表长期生存能力。

- 运行标识：`ba88571e867ec2f2`
- 代码提交：`ce550c61e9d60f1c291ab58f4c20d95c2393adfa`
- 人物位置：`{'x_m': 5000.0, 'y_m': 3300.0, 'cell_index': 3350}` → `{'x_m': 5000.0, 'y_m': 2800.0, 'cell_index': 2850}`
- 移动耗时：`400` 秒
- 饮水：`1.5` L
- 口渴：`0.72` → `0.19500000000000006`
- 世界水量：`12863309.725936027` → `12863309.724436028` m³

## 关键事件

| 世界秒 | 事件 | 行动 | 事实 |
| ---: | --- | --- | --- |
| 0 | `action_started` | `move-to-water` | `{'action_type': 'move_to_location', 'expected_end_world_seconds': 400, 'validation': {'distance_m': 500.0, 'expected_duration_seconds': 400}}` |
| 400 | `person_moved` | `move-to-water` | `{'from': {'x_m': 5000.0, 'y_m': 3300.0, 'cell_index': 3350}, 'to': {'x_m': 5000.0, 'y_m': 2800.0, 'cell_index': 2850}, 'reason': 'move_completed'}` |
| 400 | `action_completed` | `move-to-water` | `{'event_id': 'ba88571e867ec2f2:e00000004', 'from': {'x_m': 5000.0, 'y_m': 3300.0, 'cell_index': 3350}, 'to': {'x_m': 5000.0, 'y_m': 2800.0, 'cell_index': 2850}, 'distance_m': 500.0}` |
| 400 | `action_started` | `drink-at-water` | `{'action_type': 'drink_at_water', 'expected_end_world_seconds': 520, 'validation': {'distance_m': 0.0, 'litres': 1.5}}` |
| 520 | `body_state_changed` | `drink-at-water` | `{'before': {'hunger': 0.3, 'thirst': 0.72}, 'after': {'hunger': 0.3, 'thirst': 0.19500000000000006, 'water_intake_litres': 1.5}, 'delta': {'thirst': -0.5249999999999999, 'water_intake_litres': 1.5}, 'reason': 'drink_at_water'}` |
| 520 | `action_completed` | `drink-at-water` | `{'litres': 1.5, 'water_volume_before_m3': 12863309.725936027, 'water_volume_after_m3': 12863309.724436028, 'body_event_id': 'ba88571e867ec2f2:e00000008', 'thirst_before': 0.72, 'thirst_after': 0.19500000000000006}` |

## 检查

| 检查 | 结果 |
| --- | --- |
| `move_completed` | `True` |
| `arrived_at_water` | `True` |
| `drink_completed` | `True` |
| `thirst_reduced` | `True` |
| `world_water_reduced` | `True` |
| `body_event_recorded` | `True` |
| `event_query_has_move_and_drink` | `True` |

## 入口

```powershell
py -3.12 tools\run_water_chain.py --code-commit ce550c61e9d60f1c291ab58f4c20d95c2393adfa
```
