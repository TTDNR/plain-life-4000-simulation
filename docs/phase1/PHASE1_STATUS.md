# Phase 1 状态

## 当前版本

`v3` 修正版，门禁 `BLOCKED`，暂不验收，不启动正式长期模拟。

当前审计包含 12 个阻断项：

- 四个时间窗全部失败。
- 饮水、食物、遮蔽、火和稳定供给路径失败。
- 年度结果仍是固定人口需求压力测试，没有动态身体后果。
- 家庭分配和跨家庭请求回应只在短场景通过，尚未接入年度人口。

完整机器结果位于版本目录：

- [版本索引](versions/README.md)
- [v3 环境资源清单](versions/v3/ENVIRONMENT_RESOURCE_INVENTORY.md)
- [v3 开局生存核验](versions/v3/OPENING_SURVIVAL_REVIEW.md)
- [v3 初始化一致性检查](versions/v3/INITIALIZATION_CONSISTENCY_REVIEW.md)
- [v3 人物与家庭短场景](versions/v3/BEHAVIOR_SCENARIOS.md)
- [v3 变更记录](versions/v3/CHANGES.md)

## v1 保留

v1 的秋季温带基线和失败结果未被覆盖，存放于
[v1 版本目录](versions/v1/PHASE1_STATUS.md)。其未经证明的长期供给判断已在
[v1 勘误](versions/v1/ERRATA.md) 中撤销。

## 复现

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
```

正式门禁命令不得添加 `--allow-failed`：

```powershell
py -3.12 tools\run_phase1.py --version v3 --days 365
```
