---
name: htmlmini
description: >
  Use when the user wants to summarize, analyze, review, or extract information from HTML files or web pages — local design mockups, dashboards, panels, page source code, or URLs. Forces core-content extraction (strips CSS/JS/boilerplate, ~75-99% token savings) before any summarizing. Engine chain is automatic: Defuddle article -> optional Trafilatura -> semantic -> UI-component inventory for dashboards. Trigger keywords: html, 网页, 页面, 设计稿, 面板, 仪表盘, 总结, 分析, 审查, summarize, review, parse, 渲染后.
---

# htmlmini — 网页核心骨架提取

## 何时触发（必须）

用户要求**总结 / 分析 / 审查 / 理解**任何 HTML 文件或网页（本地设计稿、面板、页面源码、URL）时。
**禁止直接 Read 原始 HTML**——CSS/JS 常占 90%+ 体积，纯浪费 token。

## 调用方式（按优先级）

1. MCP 工具（已配置时）：`htmlmini_extract_file(path, mode?, extractor?)` / `htmlmini_extract_url(url, mode?, extractor?)` / `htmlmini_extract_html(html_content, mode?, extractor?)`
   - 旧拼写 `htmmini_*` 是兼容别名，行为相同；新配置一律用 `htmlmini_*`。
2. CLI：`htmlmini <文件|URL|stdin> [--mode <模式>] [--extractor <引擎>]`（详见本目录 `README.md`；支持 `--completion bash|powershell`）。

## 模式选择

| 模式 | 何时用 |
|---|---|
| `markdown`（默认） | 常规总结；文章页走 Defuddle，面板/UI 页自动切组件清单 |
| `json` | 需要元数据（标题/作者/日期）+ `used` 实际引擎 + `reductionPct` 节省统计 |
| `skeleton` | 巨页只要大纲（标题层级 + 表格 + 代码块语言） |
| `ui` | UI 设计稿强制完整清单：标题/地标/表单字段/按钮/表格/图片/链接/文本 |
| `text` | 纯文本、去掉所有标记 |
| `title` | 只要页面标题 |

`extractor` 默认 `auto`（Defuddle → 有则用 Trafilatura → semantic → ui），不用指定；只有排查抽取质量时才强制单个引擎（`--json` 看 `used` 字段确认实际命中）。

## 动态页流水线（静态抓取不够时）

`htmlmini_extract_url` 只做静态抓取。JS 重度渲染 / 被反爬拦截的页面：先用 `resilient-browser-fetch` 的 `save_page` 保存渲染后 HTML，再用 `htmlmini_extract_file` 读该文件（同目录 `<name>.html.meta.json` 会被自动利用，无需手动传 URL）。

## 不用 htmlmini 的情况（选型结论）

| 场景 | 用什么 |
|---|---|
| office/pdf/音视频转 Markdown | `markitdown`，htmlmini 只做 HTML |
| 批量新闻正文 + 只要最高精度且有 Python | `pip install trafilatura` 后 htmlmini `auto` 会自动用上，无需换工具 |
| 动态交互页要"可操作结构"而非文本摘要 | 浏览器可访问树（Playwright 类 MCP），而非静态提取 |

## 输出后

直接基于 htmlmini 的输出总结/回答；**不要回读原文验证**。若输出明显为空或标题缺失，可加 `--ui` 或 `--json` 重试一次（`json` 的 `used` 会告诉你命中了哪级引擎）。
