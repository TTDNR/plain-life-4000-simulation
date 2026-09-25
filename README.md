# Plain Life 4000 Simulation

用于模拟 4000 个人类单位在平原环境中生活的独立项目。

当前状态：v1、v2、v3 结果已冻结；v4 已把家庭分配、局部求助和基础教学接入
七天动态循环，并建立逐日食物链定位。v4 仅为诊断，尚未批准正式长期模拟。

## 项目目标

- 建立包含 4000 个人类单位的平原生活模拟。
- 模拟范围和技术路线由后续需求决定。
- 环境必须先固定并形成快照，人物才能进入世界。
- 长期模拟只能在环境、生存路径和人口一致性三项核验通过后启动。

## 当前内容

- 独立 Git 仓库和提交规则。
- 项目目标简报。
- Phase 1 结构化场景数据和审计工具。
- 可复算的 50 平方公里环境生成器。
- 4000 人家庭、照护、经历和技能初始化器。
- 饮水、食物、遮蔽、火、工具、探索和迁移的专项核验内核。
- 环境资源、开局生存和初始化一致性报告。
- 技术决策记录。
- 通用忽略规则。

## 文档

- [项目简报](docs/PROJECT_BRIEF.md)
- [Phase 1 设计](docs/phase1/PHASE1_DESIGN.md)
- [Phase 1 状态](docs/phase1/PHASE1_STATUS.md)
- [环境资源清单](docs/phase1/ENVIRONMENT_RESOURCE_INVENTORY.md)
- [开局生存核验](docs/phase1/OPENING_SURVIVAL_REVIEW.md)
- [初始化一致性检查](docs/phase1/INITIALIZATION_CONSISTENCY_REVIEW.md)
- [版本索引](docs/phase1/versions/README.md)
- [技术决策记录](docs/TECHNOLOGY_DECISIONS.md)
- [Git 工作流](docs/GIT_WORKFLOW.md)
- [项目规则](AGENTS.md)

## Phase 1 验证

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py v4
py -3.12 tools\run_integration_diagnostic.py v4
py -3.12 tools\run_phase1.py --version v3 --days 365
```

最后一条命令只用于复现 v3 年度固定人口压力测试，不能替代 v4 动态诊断。
`--allow-failed` 只用于保留失败报告，不能作为正式世界历史或长期模拟许可。
