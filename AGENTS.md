## 本仓库维护入口

本仓库保存可分发的 skill 真源。修改前读取 [仓库治理](docs/skill-governance.md)；编写或调整 skill 正文时按需读取 [内容与语言规范](docs/skill-content-guidelines.md)。子目录有自己的 `AGENTS.md` 时同时读取，规则冲突以会话指令和实际作用域为准。

- 先检查工作区，保留用户和前序任务已有改动；实体修改在 `skills/`（skill）与 `plugins/`（OpenCode 插件）真源完成。
- 按主问题选择编写、资料提炼、实战补丁或分发入口；不默认启动所有流程或子代理。
- 改动职责或触发条件时更新 README 索引和相关引用；可变规则保持一个维护位置。
- 验证强度与变更风险相称，报告结构检查、桌面走查和真实执行各自的事实与限制。
- skill 有外部运行时/工具依赖时，在 skill 目录声明 `dependencies.json`（格式见 [skill 依赖声明](docs/skill-dependencies.md)）；用 `python -X utf8 scripts/check-skill-deps.py` 检查本机可用性。
- 本仓库不维护 CHANGELOG：变更以 `git log` 和提交信息为准；只有影响使用、触发或兼容性的变化需要同步到 README 或相关说明。
- 分发复用仓库链接脚本；过程产物放被忽略的 `.workspaces/`，不进入 skill 实体。
- OpenCode 插件制品（`plugins/`）的入口约定、装载规则与分发见 [插件制品](docs/plugins.md)；插件只对 OpenCode 生效，不进各 harness 的 skills 目录。
- 文档排版与图示按 [markdown-style](skills/markdown-style/SKILL.md)：结构、流程、依赖类示意图用 Mermaid，不用框线字符画。
- Windows 下通过 PowerShell 读取含非 ASCII 的 UTF-8 文件前，按 [PowerShell 编码读取规则](skills/powershell-pitfalls/SKILL.md#文件读取与输出编码agent-读文件前)选择命令与保真回退。
- 提交、推送及外部操作遵循有效会话授权，不从修改文档或创建 skill 推定授权。

治理文档是维护入口，不要求每次修改通读全部 skill、运行所有应用级检查或做全仓格式迁移。
