# Phase 1 状态

## 当前版本

`v6` 空间发现与完整信息诊断版，暂不验收，不启动正式长期模拟。

当前状态：

- 当前有限规则每资源只保留当前营地 4 km 内评分最高的 40 个资源格，
  并且采集不检查个人 `known_cells`。
- 第 2 日以后平均新发现格为零；候选迁移格固定为 27.748 个。
- 951 次迁移全部在第 1 日，平均仅 0.182 km；第 5 日 940 户受冷却限制。
- 完整位置信息组第 7 日仍有 50 个不同鱼类资源格被使用，食物比例
  由有限组的 0.0475 提高到 0.4222。
- 完整信息组仍低于 80%，因此候选规则是主要假性受困来源，但不是唯一缺口。
- 第 6 天触发内部诊断警戒线。
- 正式长期模拟继续暂停。

完整机器结果位于版本目录：

- [版本索引](versions/README.md)
- [v6 空间发现与信息对照诊断](versions/v6/SPATIAL_ACCESS_DIAGNOSTIC.md)
- [v6 七天整合诊断](versions/v6/SEVEN_DAY_INTEGRATION.md)
- [v6 变更记录](versions/v6/CHANGES.md)
- [v6 审计](versions/v6/PHASE1_AUDIT.md)
- [v3 年度固定压力测试](versions/v3/OPENING_SURVIVAL_REVIEW.md)

## v1 保留

v1 的秋季温带基线和失败结果未被覆盖，存放于
[v1 版本目录](versions/v1/PHASE1_STATUS.md)。其未经证明的长期供给判断已在
[v1 勘误](versions/v1/ERRATA.md) 中撤销。

## 复现

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py v4
py -3.12 tools\run_integration_diagnostic.py v6
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
```

正式门禁命令不得添加 `--allow-failed`：

```powershell
py -3.12 tools\run_phase1.py --version v3 --days 365
```
