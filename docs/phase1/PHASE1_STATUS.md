# Phase 1 状态

## 当前版本

`v4` 基础行为接入诊断版，暂不验收，不启动正式长期模拟。

当前状态：

- 家庭分配、局部求助、火种、照护、住所和基础教学已接入七天循环。
- 七天食物摄入仍由约 49% 降至约 5%；前三天去重热点热量仍高于需求，
  因此断点首先在知识、加工和实际获取，而不是全局库存。
- 社会求助已产生真实请求、拒绝和接受；当前食物接受后无可交付余粮，
  未发生实际交付。住所请求因未满足触发条件为零。
- 食物链已按日记录已知资源、获取、加工、库存、资源切换和受阻原因。
- 有 131 个家庭日低于 80% 饮水需求，完整遮蔽为零，部分遮蔽覆盖 862 户、3599 人。
- 第 6 天触发内部诊断警戒线。
- 正式长期模拟继续暂停。

完整机器结果位于版本目录：

- [版本索引](versions/README.md)
- [v4 人物与家庭短场景](versions/v4/BEHAVIOR_SCENARIOS.md)
- [v4 七天整合诊断](versions/v4/SEVEN_DAY_INTEGRATION.md)
- [v4 变更记录](versions/v4/CHANGES.md)
- [v4 审计](versions/v4/PHASE1_AUDIT.md)
- [v3 年度固定压力测试](versions/v3/OPENING_SURVIVAL_REVIEW.md)

## v1 保留

v1 的秋季温带基线和失败结果未被覆盖，存放于
[v1 版本目录](versions/v1/PHASE1_STATUS.md)。其未经证明的长期供给判断已在
[v1 勘误](versions/v1/ERRATA.md) 中撤销。

## 复现

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py v4
py -3.12 tools\run_integration_diagnostic.py v4
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
```

正式门禁命令不得添加 `--allow-failed`：

```powershell
py -3.12 tools\run_phase1.py --version v3 --days 365
```
