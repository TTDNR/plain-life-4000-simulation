# S01-0 现状清点与映射

日期：2026-09-27

## 仓库与运行基座

| 项目 | 事实 |
| --- | --- |
| 仓库 | `plain-life-4000-simulation` 独立 Git 仓库 |
| 工作目录 | `C:\Users\Administrator\.codex\worktrees\cb2b\plain-life-4000-simulation` |
| 初始分支状态 | 从提交 `16397f5` 建立 `codex/s01-contract-core` |
| 语言 | Python 3.12.13 |
| 第三方依赖 | 当前 S01 核心没有新增第三方依赖 |
| Mesa | 未选择；现有可运行核心继续使用 Python 标准库 |
| 存档 | 新 S01 核心使用 Python 标准库 `sqlite3` |
| 当前世界基线 | v6，冻结在 `data/phase1/versions/v6/` |

## 现有启动入口

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py v4
py -3.12 tools\run_integration_diagnostic.py v6
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
```

S01-1 新增的契约夹具入口：

```powershell
py -3.12 tools\run_core_contract.py
```

## 模块映射

| R1 模块 | 现有文件 | 当前状态 | S01 处理 |
| --- | --- | --- | --- |
| core | `plain_life/core.py` | 新增 | 唯一时钟、行动生命周期、预约、事件、SQLite 存档 |
| contracts | `plain_life/contracts.py` | 新增 | R1 数据定义和通用单位 |
| environment | `plain_life/environment.py` | 已实现诊断模型 | `core_adapters.py` 负责把日推进绑定到核心时钟 |
| body_population | `plain_life/population.py`、`plain_life/behavior.py` | 人口初始化已实现；身体只在短场景或诊断内 | 新核心先保存通用 `PersonState`，B/C 后续接真实身体 |
| perception_memory | `plain_life/behavior.py`、`survival.py` | 短场景/诊断内有个人知识 | 新核心提供 `PerceivedState` 和显式知识来源 |
| decisions | `plain_life/behavior.py`、`survival.py` | 规则分散，只在场景或日循环内 | 新核心只保存 `DecisionTrace`，不内置社会选择规则 |
| production | `plain_life/survival.py` | 旧诊断内有采集、加工和库存 | S01-1 提供 `ItemBatch`、预约和提交接口；B 组后续接入动作定义 |
| social | `plain_life/behavior.py`、`survival.py` | 短场景和诊断内有请求/回应 | 新核心提供承诺和回应记录，不决定合作规则 |
| observer_audit | `plain_life/reporting.py`、`integration.py` | Markdown/JSON 报告 | D 组后续接读接口，S01-1 已提供快照、个人视图和事件查询 |

## 已接入能力

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 50 km² 世界生成 | 已验证 | `environment.py`，现有测试检查 5000 格 |
| 天气/季节/资源再生 | 已验证诊断 | 日推进函数存在，参数仍为假设 |
| 4000 人初始化 | 已验证 | `population.py` |
| 饮水、食物、遮蔽、火、工具路径 | 诊断已接入 | 由 `survival.py` 的固定日循环执行 |
| 个人知识不默认家庭同步 | 短场景已验证 | 尚未全部改接 S01 核心 |
| 求助、回应、分配和照护 | 短场景/诊断 | 不是正式长期行为规则 |
| 唯一事件日志 | S01-1 已新增 | `SimulationCore` 运行清单和事件序列 |
| 资源预约/防重复交付 | S01-1 已验证 | `ItemReservation` 与核心提交 |
| 暂停/推进/快照/恢复 | S01-1 已验证 | SQLite 存档恢复后可继续进行中行动 |
| 二维观察界面 | 未实现 | 只保留报告输出 |

## 旧模型内的时钟和状态重叠

下列重叠只存在于已冻结的诊断路径，S01-1 没有把它们静默合并：

| 重叠 | 位置 | 处理 |
| --- | --- | --- |
| `WorldState.elapsed_days` | `environment.py` | 旧日循环仍直接推进；新核心通过 `WorldClockAdapter` 驱动 |
| `run_survival_validation` 的 `day` 循环 | `survival.py` | 保持旧诊断；新流程不得再开一份时钟 |
| `Task.start_minute/end_minute` | `behavior.py` | 短场景分钟制；新接口统一用 `world_seconds` |
| `HouseholdRuntime.food_store_kg/kcal` | `survival.py` | 旧家庭库存；新资源路径改为 `ItemBatch` |
| `BehaviorState.food_items` | `behavior.py` | 短场景物品；新资源路径改为 `ItemBatch` |
| 世界资源数组 | `environment.py` | 仍是野外存量来源；物品批次记录从地图到持有者的流转 |

## 当前失败基线

v6 的空间发现诊断仍是当前失败基线：

- 有限候选规则固定为每资源 40 格、4 km、排序取前，且采集不检查个人 `known_cells`。
- 第 2 日以后平均新发现为 0；951 次迁移全部发生在第 1 日。
- 完整信息对照组仍低于 80% 食物满足率。
- 当前结论是候选规则造成假性受困，同时存在真实获取、交通和加工不足。

引用：

- [v6 诊断](../../phase1/versions/v6/SPATIAL_ACCESS_DIAGNOSTIC.md)
- [v6 审计](../../phase1/versions/v6/PHASE1_AUDIT.md)

## 未核查项

- Mesa 版本及其事件调度未使用，因此没有版本锁定。
- 旧诊断与新核心尚未合并成同一条 64 人连续运行链路。
- 二维观察界面没有实现。
- 身体、疾病、死亡、跨代和长期性能仍未校准。

