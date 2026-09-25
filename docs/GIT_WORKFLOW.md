# Git 工作流

本项目是独立 Git 仓库，主分支为 `main`。

## 开始工作

```powershell
git status --short --branch
```

## 提交前检查

Phase 1 审计工具：

```powershell
py -3.12 -m compileall -q tools tests
py -3.12 -m unittest discover -s tests -v
py -3.12 tools\run_behavior_scenarios.py
py -3.12 tools\run_integration_diagnostic.py
py -3.12 tools\run_phase1.py --version v3 --days 365 --allow-failed
git diff --check
git status
```

`run_phase1.py` 是 Phase 1 的端到端命令。它会生成固定世界和人口、运行专项核验并重新生成
指定版本的报告。门禁未通过时返回非零退出码；`--allow-failed` 只用于保存失败报告。

`phase1_audit.py` 是底层结构审计器，直接读取尚未注入生成快照的源文件，因此不能代替
`run_phase1.py` 的端到端结果。

确定长期模拟技术栈后，必须在这里补充该技术的实际构建、测试、格式化和运行命令。

## 提交

```powershell
git diff
git add .
git status
git commit -m "type(scope): description"
git status --short --branch
```

最后一次 `git status` 应显示工作区干净。

## 提交类型

- `feat`: 新功能
- `fix`: 修复问题
- `docs`: 文档和决策记录
- `refactor`: 行为不变的重构
- `test`: 测试变更
- `chore`: 初始化、依赖和工具配置

## 禁止提交

- Token、`.env`、私钥和服务器凭据。
- 模型权重、数据集和共享缓存。
- 构建产物、导出文件、日志和大型临时产物。
- 嵌套的第三方 Git 仓库。

## 远端

默认只维护本地 Git，不自动创建 GitHub 仓库或推送。用户明确要求推送时，再配置远端并确认
目标账号、仓库名和可见性。
