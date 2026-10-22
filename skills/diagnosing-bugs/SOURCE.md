# 来源与本地改动

- 上游仓库：<https://github.com/mattpocock/skills>
- 上游路径：`skills/engineering/diagnosing-bugs/SKILL.md` 与 `skills/engineering/diagnosing-bugs/scripts/hitl-loop.template.sh`
- 固定版本：main @ `5beb35b040e3de97e54fa9e386d7e42d15c295c2`（CHANGELOG 最新 1.3.1，2026-10-19）
- 许可：MIT，版权归 Matt Pocock；全文见同目录 [LICENSE](LICENSE)。

## 本地改动

- frontmatter 的 `description` 改为中文触发描述，并补充与 `frontend-qa`、`web-app-testing`、`ai-verified-delivery` 的边界。
- 正文保留上游英文原文；仅增加一条本地说明。
- `scripts/hitl-loop.template.sh`：示例端口 `3000` 改为占位符 `<port>`，避免真源写入本机端口；补一条 Windows 运行提示。
- 未改写诊断流程、阈值与示例。

## 更新

按上游路径取新版本后 diff，保留本地 `description`、本地说明与端口占位符；上游变化影响触发边界时同步更新 README 索引。
