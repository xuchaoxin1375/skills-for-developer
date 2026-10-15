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
   - CLI 不在 PATH 时用 `node <本 skill 目录>/src/cli.js <同样参数>`，无需全局安装。例：`htmlmini` 命令报无法识别，直接 node 跑本 skill 目录里的 cli.js。

## 模式选择

| 模式 | 何时用 |
|---|---|
| `markdown`（默认） | 常规总结；文章页走 Defuddle，面板/UI 页自动切组件清单 |
| `json` | 需要元数据（标题/作者/日期）+ `used` 实际引擎 + `reductionPct` 节省统计 |
| `skeleton` | 巨页只要大纲（标题层级 + 表格 + 代码块语言） |
| `ui` | UI 设计稿强制完整清单：标题/地标/表单字段/按钮/表格/图片/链接/文本 |
| `text` | 纯文本、去掉所有标记 |
| `title` | 只要页面标题 |

`extractor` 默认 `auto`（非HTML透传 → Defuddle → 有则用 Trafilatura → semantic → ui），不用指定；只有排查抽取质量时才强制单个引擎（`--json` 看 `used` 字段确认实际命中）。非 HTML（markdown/纯文本/JSON，如 gitee 直接返回的 `text/plain`）任何模式下都原样透传（`used=passthrough`）。

## 动态页流水线（静态抓取不够时）

`htmlmini_extract_url` 只做静态抓取：默认跟随任务/宿主的代理环境变量，可经 `proxy` 参数覆盖（URL 或 `"direct"`）；403/5xx 自动补一次浏览器头重试（同路线）。一步到位的用法：`htmlmini <URL> --render` 或 MCP `render:true`——静态优先，静态 403/5xx 才自动回退浏览器渲染再按文件模式提取；渲染链为 save_page（环境就绪时用，同代理，cloak 不必接）→ 本机普通 Chrome 无头 dump-dom（零依赖）→ 友好报错，实际走了哪条会打 `htmlmini: [render] engine=…` 日志；Chrome 通路按显式 `--chrome-bin` / `chrome_bin` / `HTMLMINI_CHROME_BIN` → PATH → 系统常用路径 → Playwright 缓存（`PLAYWRIGHT_BROWSERS_PATH` 可改位置，完整版优先取版本最大者）选择；首次人工验证用 `--headful` / `headful:true`（仅 save_page 通路支持）；404/超时/断网直接抛错，不烧浏览器时间。手工两步（存量/排查用）：先走 `network-access` 双路对照（直连+代理并行 curl，必要时 `curl_cffi` 做 TLS 级伪装），用胜出路线落盘的正文按文件模式提取，不按 URL 重抓；静态皆取不到可用正文（含挑战特征）才用 `save_page` 保存渲染后 HTML（同代理），再用 `htmlmini_extract_file` 读该文件（同目录 `<name>.html.meta.json` 会被自动利用，无需手动传 URL）。例：直连 403、代理 200 落盘，直接提取该文件，不启浏览器；简头 curl 两路 502 但补头现挑战跳转，即转浏览器而非判死。

## 不用 htmlmini 的情况（选型结论）

| 场景 | 用什么 |
|---|---|
| office/pdf/音视频转 Markdown | `markitdown`，htmlmini 只做 HTML |
| 批量新闻正文 + 只要最高精度且有 Python | `pip install trafilatura` 后 htmlmini `auto` 会自动用上，无需换工具 |
| 动态交互页要"可操作结构"而非文本摘要 | 浏览器可访问树（Playwright 类 MCP），而非静态提取 |

## 自检

- CLI 缺失时是否用 `node` 跑本 skill 目录的 `cli.js`，而非找全局安装？
- URL 抓取优先用 `--render` / `render:true` 一条命令（静态优先、403/5xx 自动回退渲染）；手工排查才走双路对照落盘。挑战特征出现才上浏览器，而非 curl 5xx 直接判死？
- 是否按需用 `proxy` 参数或环境代理走指定路线，而非默认直连硬闯？

## 输出后

直接基于 htmlmini 的输出总结/回答；**不要回读原文验证**。若输出明显为空或标题缺失，可加 `--ui` 或 `--json` 重试一次（`json` 的 `used` 会告诉你命中了哪级引擎）。
