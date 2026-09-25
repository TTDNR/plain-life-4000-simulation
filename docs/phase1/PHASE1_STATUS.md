# Phase 1 状态

## 门禁状态

```text
BLOCKED
```

长期模拟不得启动。当前专项核验确认：最初数日存在可行生存路径，但最初数周以后食物
获取失败。

## 当前审计汇总

```text
Blockers: 6
Warnings: 0
Environment: known=9, assumption=32, unresolved=0
Survival: known=7, assumption=1, unresolved=0
Population constraints: known=16
Population snapshot: ready, 4000/4000
```

阻断来自：

- 最初数周、第一个季节转换和第一个完整年度食物核验失败。
- 食物、遮蔽和稳定供给三条路径未通过。

当前没有结构警告。环境参数全部以已接受的模型假设运行；实证校准仍待后续需求。

## 三项交接结果

1. [环境资源清单](ENVIRONMENT_RESOURCE_INVENTORY.md)：区分已确定、假设和待补事实。
2. [开局生存核验](OPENING_SURVIVAL_REVIEW.md)：列出四时间窗、依赖链和当前瓶颈。
3. [初始化一致性检查](INITIALIZATION_CONSISTENCY_REVIEW.md)：列出 4000 人和家庭引用约束。

## 复现

```powershell
py -3.12 -m compileall -q tools tests
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_phase1.py --days 365 --allow-failed
```

用于长期模拟门禁的命令不得加 `--allow-failed`：

```powershell
py -3.12 tools\run_phase1.py --days 365
```

在门禁非 `PASS` 时，该命令返回非零退出码。
