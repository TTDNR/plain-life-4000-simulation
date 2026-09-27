# S01-1 核心整改 A01—A04

## 范围

本记录对应《S01接入裁决与核心整改 D01》的 A01—A04。

状态：开发中，等待总控复核。S01-1 不因本地回归通过而自动验收。

整改代码提交：`7246ff617097f907c2ad22e13959fe519569df2e`

## A01 启动失败残留行动

修复：

- `start_action` 先检查人物存在、存活、当前占用和动作条件。
- 忙碌人物得到 `blocked` 行动，不进入 `active`。
- `handler.begin` 失败时恢复启动前行动、人物、物品、预约、事件和待处理事件。

回归：

- `test_busy_actor_start_is_blocked_before_state_commit`
- `test_handler_begin_failure_rolls_back_start_and_reservation`

原始复现现在得到：

```json
{
  "active_actions_after_rejection": ["first"],
  "second_status": "blocked"
}
```

## A02 查询结果改写世界

修复：

- `snapshot`、`query_events`、`perceived_state`、`module_state` 返回深拷贝。
- 输入人物、物品、承诺、行动目标、事件事实和模块状态时保存副本。
- `from_snapshot` 在导入时复制输入快照。

回归：

- `test_read_views_are_isolated_from_authoritative_state`

原始复现现在得到：

```json
{
  "core_hunger_after_snapshot_edit": 0.2,
  "event_facts_after_query_edit": "core_unit_fixture",
  "memory_x_after_view_edit": 12.0
}
```

## A03 当前时刻事件延迟

修复：

- 每个时间边界先处理当前时刻到期事件，再处理到期行动。
- `advance_to(now)` 也会执行当前时刻事件。
- 同刻事件和行动循环有 10000 次安全检查，无进展时明确报错。

回归：

- `test_due_now_event_is_processed_at_current_time_and_segments_match`

原始复现现在得到：

```json
{
  "due_now_at_zero": [0],
  "due_now_after_ten": [0]
}
```

## A04 恢复后环境停止

修复：

- 快照保存必需模块、恢复工厂标识和模块状态。
- `load` 检查所有必需模块是否重新绑定。
- 缺少绑定时抛出 `ModuleBindingError`，禁止静默继续。
- `WorldClockAdapter.restore` 从恢复副本重建世界并重新绑定推进。

回归：

- `test_existing_world_follows_core_clock_and_round_trips`

原始复现现在得到：

```json
{
  "missing_module_result": "ModuleBindingError",
  "core_days": 2,
  "environment_days": 2
}
```

## 接口变化

没有改变 R1 字段语义。新增：

- `ModuleBindingError`
- `register_advance_callback(..., required_for_advance, restore_factory)`
- `SimulationCore.load(..., module_factories=...)`
- `WorldClockAdapter.restore`

## 接入裁决

- B/C 新动作接入 core。
- 旧 `survival.py` 诊断独立保留。
- 不将旧整日循环包装为推进回调。

## 尚未完成

- B/C 生产动作和真实生活链尚未接入。
- D 只读观察入口尚未实现。
- 64 人和 4000 人诊断尚未运行。
- T08/T11 状态需要区分核心回归通过与完整领域验收。
