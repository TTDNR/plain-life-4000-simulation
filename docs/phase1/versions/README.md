# Phase 1 版本索引

## v1

状态：已冻结，不验收，不用于正式长期模拟。

基线：

- 温带泛滥平原。
- 年均温约 13.25°C，年降雨约 795 mm。
- 初始日第 260 日。
- 初始化时直接分布到多个营地。
- 家庭技能集合直接参与可用知识。

原始结果：

- 环境资源清单：[v1](v1/ENVIRONMENT_RESOURCE_INVENTORY.md)
- 开局生存核验：[v1](v1/OPENING_SURVIVAL_REVIEW.md)
- 初始化一致性检查：[v1](v1/INITIALIZATION_CONSISTENCY_REVIEW.md)
- 状态：[v1](v1/PHASE1_STATUS.md)

v1 的“自然再生量可能支持长期生存”判断已被撤销。该判断没有资源账和参数
实证支持。保留原报告是为了追踪改动，不作为当前结论。

## v2

状态：修正版压力测试，门禁 `BLOCKED`，等待验收，不启动正式长期模拟。

主要修正：

- 气候改为暖湿参数。
- 投放时间恢复为暖季早期第 90 日，并单独记录为需求修正。
- 分开投放瞬间和首日自行扎营。
- 个人技能和信息不再自动同步。
- 增加逐资源账目、资源口径、加工失败、分配口径和诊断对照。

当前结果：

- 环境资源清单：[v2](v2/ENVIRONMENT_RESOURCE_INVENTORY.md)
- 开局生存核验：[v2](v2/OPENING_SURVIVAL_REVIEW.md)
- 初始化一致性检查：[v2](v2/INITIALIZATION_CONSISTENCY_REVIEW.md)
- 变更记录：[v2](v2/CHANGES.md)
- 审计阻断项：[v2](v2/PHASE1_AUDIT.md)
