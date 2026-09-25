# Phase 1 状态

## 门禁状态

```text
BLOCKED
```

长期模拟不得启动。此状态来自结构化场景，而不是运行结果。

## 当前审计汇总

```text
Blockers: 51
Warnings: 3
Environment: known=7, assumption=3, unresolved=31
Survival: known=0, assumption=0, unresolved=18
Population constraints: known=16
Population snapshot: unresolved, 0/4000
```

阻断主要来自：

- 31 个世界初始化或生态事实尚未确定。
- 四个时间窗和六条生存依赖均未评估。
- 八个食物可用性维度尚未确定。
- 人口与生态关联、4000 人家庭快照尚未生成。

警告来自三个尚未正式接受的边界假设：固定地点气候输入、可选地表水单向输出、可选地下水
单向输出。

## 三项交接结果

1. [环境资源清单](ENVIRONMENT_RESOURCE_INVENTORY.md)：区分已确定、假设和待补事实。
2. [开局生存核验](OPENING_SURVIVAL_REVIEW.md)：列出四时间窗、依赖链和当前瓶颈。
3. [初始化一致性检查](INITIALIZATION_CONSISTENCY_REVIEW.md)：列出 4000 人和家庭引用约束。

## 复现

```powershell
py -3.12 -m compileall -q tools tests
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\phase1_audit.py --data data\phase1 --format markdown --allow-blocked
```

用于长期模拟门禁的命令不得加 `--allow-blocked`：

```powershell
py -3.12 tools\phase1_audit.py --data data\phase1
```

在门禁非 `PASS` 时，该命令返回非零退出码。
