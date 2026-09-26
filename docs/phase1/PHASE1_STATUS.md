# Phase 1 状态

## 当前版本

`v5` 季节拒绝与捕鱼退出诊断版，暂不验收，不启动正式长期模拟。

当前状态：

- 鹿、兔、鱼、水禽、香蒲和春季嫩叶没有季节拒绝记录；真实季节拒绝来自
  箭叶、浆果、榛子和橡子。
- 第 2 日 651 户捕鱼；第 4 与第 5 日均未再取得鱼的 238 户中，
  235 户两日都因已知鱼类候选格耗尽退出。
- 全图鱼类并未耗尽；期末仍有约 99,785 kg。问题集中在少量共享资源格。
- 七天食物摄入仍由约 49% 降至约 5%；固定初始能力对照同样降至约 5%。
- 初步相容性评估指出，必须先隔离 20 个集中营地与共享候选格造成的局部压力。
- 第 6 天触发内部诊断警戒线。
- 正式长期模拟继续暂停。

完整机器结果位于版本目录：

- [版本索引](versions/README.md)
- [v5 七天整合诊断](versions/v5/SEVEN_DAY_INTEGRATION.md)
- [v5 开局相容性评估](versions/v5/COMPATIBILITY_ASSESSMENT.md)
- [v5 变更记录](versions/v5/CHANGES.md)
- [v5 审计](versions/v5/PHASE1_AUDIT.md)
- [v3 年度固定压力测试](versions/v3/OPENING_SURVIVAL_REVIEW.md)

## v1 保留

v1 的秋季温带基线和失败结果未被覆盖，存放于
[v1 版本目录](versions/v1/PHASE1_STATUS.md)。其未经证明的长期供给判断已在
[v1 勘误](versions/v1/ERRATA.md) 中撤销。

## 复现

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py v4
py -3.12 tools\run_integration_diagnostic.py v5
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
```

正式门禁命令不得添加 `--allow-failed`：

```powershell
py -3.12 tools\run_phase1.py --version v3 --days 365
```
