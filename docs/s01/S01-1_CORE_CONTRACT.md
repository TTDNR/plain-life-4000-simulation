# S01-1 契约与执行核心

## 范围

本任务只建立共享契约、唯一时钟、行动生命周期、资源提交、事件记录、
运行清单和 SQLite 存档。它不实现 64 人或 4000 人生活流程，也不启动正式长期模拟。

## 数据定义

实现文件：`plain_life/contracts.py`

| R1 记录 | 实现 |
| --- | --- |
| RunManifest | 运行 ID、代码提交、契约版本、场景/参数/环境/人口指纹、种子、模式、未支持能力、依赖版本 |
| PersonState | 人物、家庭、真实位置、身体、当前行动 |
| ItemBatch | 批次、类别、数量、单位、状态、持有者/位置、来源事件、热量属性 |
| PerceivedState | 个人当前身体、当前行动、知识、已知地点、可见物品、承诺和说法 |
| ActionIntent | 意图、人物、动作类型、形成时间、时长、目标和已知条件 |
| ActionRecord | 计划、开始、进度、结束、参与者、预约、结果和原因事件 |
| SocialResponse / Commitment | 回应类型和未来承诺的独立状态 |
| Event | 运行、事件、时间、行动、原因、参与者和状态事实 |
| DecisionTrace | 当时的信息引用、选项、选择和预期结果 |

## 执行核心

实现文件：`plain_life/core.py`

### 唯一时钟

- `SimulationClock` 使用整数世界秒。
- `advance_to` 和 `advance_by` 是唯一推进入口。
- 世界时间只能递增；暂停状态禁止推进。
- 日序和年内日期由时钟转换，不要求领域模块自行加 1。

### 行动生命周期

1. `submit_action` 创建 `ActionRecord` 并记录意图事件。
2. `start_action` 在任何状态提交前检查人物存活、当前占用和动作条件。
   拒绝时行动进入 `blocked`，不留下开始时间、预约或人物占用。
3. 动作开始时可预约物品；预约不会改变持有者数量。
4. `advance_to` 推进进度，并在结束时间调用 `complete`。
5. `interrupt_action` 记录已经发生的时间和进度，释放未完成预约，不产生未完成产物。
6. 完成和失败都产生新事件，不覆盖旧行动。

已提供：

- `TransferItemHandler`：转移预留物品，防止重复交付。
- `ConsumeItemHandler`：消费预留物品，未完成时不扣减。

`handler.begin` 失败时，核心恢复行动、人物、物品、预约、事件和待处理事件到
启动前状态，然后产生明确的 `action_blocked`。

### 时间边界

每个世界时间边界按以下顺序处理：

1. 当前时刻已到期的待处理事件。
2. 当前时刻到期的行动完成。
3. 跨过该时间边界的模块推进回调。
4. 模块回调产生的同刻事件。

`advance_to(now)` 也会处理当前时刻事件。一次推进与分段推进必须得到相同的
事件类型、顺序和时间；同刻处理若没有进展会显式报错。

## 资源提交规则

- `ItemBatch` 是 S01 资源持有状态的唯一入口。
- `available_item_quantity` 扣除所有未完成预约。
- 同一批次不能把预约量再次转移或消费。
- 转移在完成时拆分批次并产生 `item_transferred`。
- 中断释放预约；已经发生的行动时间仍保留在行动记录和事件中。

## 只读接口

`snapshot`、`query_events`、`perceived_state` 和 `module_state` 返回深拷贝。
调用者修改返回的嵌套人物、事件事实、记忆、物品或模块数据，不会改变核心状态。
外部对象通过 `register_person`、`add_item`、`add_commitment` 等入口导入时，
核心也保存副本，不保留调用者后续可修改的共享引用。

## 保存与恢复

实现使用标准库 `sqlite3`：

- `run_state` 保存 `RunManifest` 和完整快照。
- `events` 保存按序列排列的事件记录，便于外部查询。
- 快照包含人物、物品、预约、知识、关系、进行中行动、未来承诺、
  待处理事件、模块状态、模块恢复要求和随机状态。
- 恢复进行中行动时必须提供对应动作处理器。
- 必需模块必须通过保存的恢复工厂重新绑定；缺少绑定时恢复失败，
  不允许核心时间继续而模块静默停在旧状态。

接口：

```python
core = create_run(manifest, handlers)
core.advance_to(world_seconds)
snapshot = core.snapshot()
perceived = core.perceived_state(person_id)
events = core.query_events(person_id=person_id)
core.save(Path("run.sqlite3"))
loaded = SimulationCore.load(
    Path("run.sqlite3"),
    handlers=handlers,
    module_factories={
        "environment_world": WorldClockAdapter.restore,
    },
)
```

## 与旧模型的适配

实现文件：`plain_life/core_adapters.py`

- `world_to_state` / `world_from_state`：序列化现有 `WorldState`。
- `WorldClockAdapter`：注册为推进回调，由核心时钟驱动 `advance_day`。
- `population_to_state` / `population_from_state`：序列化现有 `PopulationState`。

旧 `survival.py` 日循环保持冻结；新流程只能使用核心时钟。不得把旧整日循环
包装成一个大动作或推进回调。B/C 使用 core 动作接口和已验证的领域计算，
旧诊断继续使用独立运行 ID 与状态。

## 完成标准对应关系

| S01-1 完成标准 | 证据 |
| --- | --- |
| 同一食物不能重复交付 | `tests/test_core_contract.py::test_reservation_blocks_double_delivery` |
| 中断不产生未完成产物 | `test_interrupted_action_has_no_output` |
| 恢复后继续行动 | `test_sqlite_restore_continues_active_action_and_preserves_state` |
| 环境状态可随核心推进并恢复 | `test_existing_world_follows_core_clock_and_round_trips` |
| 运行清单和事件可查询 | `tools/run_core_contract.py` 的 `run_manifest.json`、`events.jsonl` |

## 未完成边界

- 本任务没有把生产和人物行为接入核心；那是 S01-2 和 S01-3。
- 没有二维界面；那是 S01-4。
- 没有 64 人和 4000 人连续运行；那是 S01-5。
- Mesa 未引入，因为当前 `WorldState` 和 `PopulationState` 已有可用 Python
  实现，新增适配层足以满足 S01-1。
- 完整天气、生态和身体快照的模块化提交仍需在后续接入时逐项验证。

## D01 接入裁决

| 内容 | 处理 |
| --- | --- |
| B/C 行为 | 接入新 core 的动作、物品、时间和事件 |
| 旧 `survival.py` | 保留为独立诊断，不进入新世界推进链 |
| 旧参数与初始化 | 可作为新世界的初始输入，记录版本与指纹 |
| 旧整日循环 | 不得包装为模块回调或一个大动作 |
| 环境日更新 | 只通过 `WorldClockAdapter` 等明确模块在时间边界推进 |
