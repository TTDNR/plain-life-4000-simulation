# Plain Life 4000 Simulation

用于模拟 4000 个人类单位在平原环境中生活的独立项目。

当前状态：Phase 1 固定世界、4000 人初始人口和专项生存核验已经可复算。
最初数日存在生存路径，但年度核验失败，尚未批准启动长期模拟。

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
- [技术决策记录](docs/TECHNOLOGY_DECISIONS.md)
- [Git 工作流](docs/GIT_WORKFLOW.md)
- [项目规则](AGENTS.md)

## Phase 1 验证

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_phase1.py --days 365
```

第二条命令运行完整年度专项核验并生成三项报告。门禁未通过时返回非零退出码。
`--allow-failed` 只用于保留失败报告，不能作为正式世界历史或长期模拟许可。
