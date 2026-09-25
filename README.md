# Plain Life 4000 Simulation

用于模拟 4000 个人类单位在平原环境中生活的独立项目。

当前状态：Phase 1 世界与人口门禁已建立。尚未批准启动长期模拟。

## 项目目标

- 建立包含 4000 个人类单位的平原生活模拟。
- 模拟范围和技术路线由后续需求决定。
- 环境必须先固定并形成快照，人物才能进入世界。
- 长期模拟只能在环境、生存路径和人口一致性三项核验通过后启动。

## 当前内容

- 独立 Git 仓库和提交规则。
- 项目目标简报。
- Phase 1 结构化场景数据和审计工具。
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
py -3.12 tools\phase1_audit.py --data data\phase1
```

第二条命令会在门禁未通过时返回非零退出码。`data/phase1` 中的未决事实必须由需求输入补齐，
审计器不会生成默认生态或人口数据。
