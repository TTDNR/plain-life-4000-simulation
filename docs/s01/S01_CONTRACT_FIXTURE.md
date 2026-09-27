# S01-1 契约与执行核心夹具

这是 `contract_fixture`，不是正式世界历史，也不代表生存路径通过。

- 运行标识：`d4322a787ab440e4`
- 代码提交：`e6869c3b5eb9af599fbc708e627f3c7af3bdd915`
- 模式：`contract_fixture`
- 世界时间：`7200` 秒

## 验收检查

| 检查 | 结果 |
| --- | --- |
| `interrupted_action_has_no_output` | `True` |
| `competing_action_blocked` | `True` |
| `restored_action_was_active` | `True` |
| `restored_action_completed_after_load` | `True` |
| `item_quantity_conserved` | `True` |
| `only_one_transfer_output` | `True` |
| `random_state_restored` | `True` |
| `future_commitment_restored` | `True` |
| `knowledge_restored` | `True` |
| `location_and_body_restored` | `True` |
| `pending_event_restored` | `True` |
| `pending_event_processed_after_restore` | `True` |
| `all_events_have_run_id` | `True` |

## 关键事件

| 序号 | 世界秒 | 事件 | 行动 | 事实 |
| ---: | ---: | --- | --- | --- |
| 3 | 0 | `action_intent_submitted` | `action-interrupted-transfer` | `{'action_type': 'transfer_item', 'expected_outcome': 'p2 receives 0.6 kg', 'known_conditions': ['food-1 held by p1']}` |
| 7 | 1800 | `action_interrupted` | `action-interrupted-transfer` | `{'progress_seconds': 1800, 'reason': 'fixture_interruption', 'result': {'reason': 'fixture_interruption', 'released_reservations': ['d4322a787ab440e4:r00000001']}}` |
| 8 | 1800 | `action_intent_submitted` | `action-restored-transfer` | `{'action_type': 'transfer_item', 'expected_outcome': 'p3 receives 0.6 kg', 'known_conditions': ['food-1 is held by p1 after interruption']}` |
| 11 | 1800 | `action_intent_submitted` | `action-competing-transfer` | `{'action_type': 'transfer_item', 'expected_outcome': 'p3 receives 0.6 kg', 'known_conditions': ['food-1 may still be held by p1']}` |
| 12 | 1800 | `action_blocked` | `action-competing-transfer` | `{'facts': {'available': 0.4, 'requested': 0.6}, 'reason': 'insufficient_unreserved_item'}` |
| 13 | 3000 | `item_transferred` | `action-restored-transfer` | `{'reservation_id': 'd4322a787ab440e4:r00000002', 'source_batch_id': 'food-1', 'output_batch_id': 'food-1:transfer:000001', 'quantity': 0.6, 'unit': 'kg', 'to_owner_kind': 'person', 'to_owner_id': 'p3'}` |
| 14 | 3000 | `action_completed` | `action-restored-transfer` | `{'output_batch_id': 'food-1:transfer:000001', 'quantity': 0.6, 'unit': 'kg', 'to_owner_kind': 'person', 'to_owner_id': 'p3'}` |

## 状态结果

- 物品批次：`[{'batch_id': 'food-1', 'category': 'mixed_berries', 'quantity': 0.4, 'unit': 'kg', 'state': 'edible', 'owner_kind': 'person', 'owner_id': 'p1', 'location': {'x_m': 100.0, 'y_m': 200.0, 'cell_index': 102}, 'source_event_id': None, 'kcal_per_kg': 500.0, 'attributes': {'source': 'fixture'}}, {'batch_id': 'food-1:transfer:000001', 'category': 'mixed_berries', 'quantity': 0.6, 'unit': 'kg', 'state': 'edible', 'owner_kind': 'person', 'owner_id': 'p3', 'location': {'x_m': 120.0, 'y_m': 200.0, 'cell_index': 102}, 'source_event_id': 'd4322a787ab440e4:e00000013', 'kcal_per_kg': 500.0, 'attributes': {'source': 'fixture'}}]`
- 活跃行动：`[]`
- 恢复前待处理事件：`[{'scheduled_id': 'd4322a787ab440e4:q00000001', 'due_world_seconds': 7200, 'event_type': 'fixture_pending_event', 'actor_ids': ['p1'], 'facts': {'purpose': 'restore_pending_event_check'}, 'action_id': None, 'cause_event_ids': [], 'observed_by': ['p1', 'p2'], 'location': None}]`
- 恢复后随机状态一致：`True`
- 未来照护承诺恢复：`True`

## 入口

```powershell
py -3.12 tools\run_core_contract.py
```

机器结果和 SQLite 存档位于 `artifacts/s01/contract_fixture/`。
