---
name: htmlmini
description: Use when the user wants to summarize, analyze, review, or extract information from HTML files or web pages — local design mockups, dashboards, panels, page source code, or URLs. Forces core-content extraction (strips CSS/JS/boilerplate, ~97-99% token savings) before any summarizing. Trigger keywords: html, 网页, 页面, 设计稿, 面板, 仪表盘, 总结, 分析, 审查, summarize, review, parse.
---

# htmlmini — 网页核心骨架提取

## 何时触发（必须）

用户要求**总结 / 分析 / 审查 / 理解**任何 HTML 文件或网页（本地设计稿、面板、页面源码、URL）时。
**禁止直接 Read 原始 HTML**——CSS/JS 常占 90%+ 体积，纯浪费 token。

## 调用方式（按优先级）

1. MCP 工具（已配置时）：`htmmini_extract_file(path, mode)` / `htmmini_extract_url(url, mode)` / `htmmini_extract_html(html_content, mode)`
2. CLI（全局已安装 `npm link`）：`htmlmini <文件|URL|stdin>`

## 模式选择

| 模式 | 何时用 |
|---|---|
| `markdown`（默认） | 常规总结；文章/正文页走 Defuddle，面板/UI 页自动切组件清单 |
| `json` | 需要元数据（标题/作者/日期）+ `used` 抽取器 + `reductionPct` 节省统计 |
| `skeleton` | 巨页只要大纲（标题层级 + 表格 + 代码块语言） |
| `ui` | UI 设计稿强制完整清单：标题/表单字段/按钮/下拉/表格/文本 |
| `text` | 纯文本、去掉所有标记 |
| `title` | 只要页面标题 |

## 输出后

直接基于 htmlmini 的输出总结/回答；**不要回读原文验证**。若输出明显为空或标题缺失，可加 `--ui` 或 `--json` 重试一次。