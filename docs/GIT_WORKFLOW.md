# Git 工作流

本项目是独立 Git 仓库，主分支为 `main`。

## 开始工作

```powershell
git status --short --branch
```

## 提交前检查

空白模板阶段：

```powershell
git diff --check
git status
```

确定技术栈后，必须在这里补充实际使用的构建、测试、格式化和运行验证命令。

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
