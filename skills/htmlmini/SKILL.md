---
name: htmlmini
description: >
  Use when the user wants to summarize, analyze, review, view, or extract information from HTML files or web pages — local design mockups, dashboards, panels, page source code, or URLs. Always consult this skill first for any URL/page + view/extract/scores/tables request, even if phrased casually without naming HTML (e.g. "看一下...分数/表格/榜单"), and before using generic fetch or hand-written regex on raw HTML.
  Forces core-content extraction (strips CSS/JS/boilerplate, ~75-99% token savings) before any summarizing.
  Engine chain is automatic: Defuddle article -> optional Trafilatura -> semantic -> UI-component inventory for dashboards.
  Trigger keywords: html, URL, 网页, 页面, 设计稿, 面板, 仪表盘, 总结, 分析, 审查, 查看, 看一下, 提取, 取数, 分数, 评分, 表格, 榜单, 排名, summarize, review, parse, view, extract, 渲染后.
---

# htmlmini — 网页核心骨架提取

## 何时触发（必须）

用户要求**总结 / 分析 / 审查 / 理解**任何 HTML 文件或网页（本地设计稿、面板、页面源码、URL）时。
URL 或页面 + 查看/取数意图同样触发：含 URL 并要求看其中数据、分数、表格、榜单时，先走提取再回答，不得直接手抓原文正则取数。例：给 URL 问其中表格分数，先提取核对覆盖度再取值。
**禁止直接 Read 原始 HTML**——CSS/JS 常占 90%+ 体积，纯浪费 token。

## 调用方式（按优先级）

1. MCP 工具（已配置时）：`htmlmini_extract_file(path, mode?, extractor?)` / `htmlmini_extract_url(url, mode?, extractor?)` / `htmlmini_extract_html(html_content, mode?, extractor?)`
   - 旧拼写 `htmmini_*` 是兼容别名，行为相同；新配置一律用 `htmlmini_*`。
2. CLI：`htmlmini <文件|URL|stdin> [--mode <模式>] [--extractor <引擎>]`（选项与示例以 `htmlmini --help` 为准，清单用 `--list-modes` / `--list-extractors`；支持 `--completion bash|powershell`）。
   - 进度日志一律走 stderr（`htmlmini: [read|parse|extract|format|write] …`，带耗时与体积），stdout 只放提取结果；取载荷只读 stdout，别把 stdout/stderr 混着解析。要安静用 `--quiet`，要排查用 `--verbose`（或环境变量 `HTMLMINI_LOG=quiet|info|debug`）。
   - 需要落盘时用 `-o <文件>`（文件尾恰好一个换行）；不要用 PowerShell 管道接 `Set-Content` 收载荷——它会多补行尾，非 ASCII 还要你显式加 `-Encoding utf8`。
   - CLI 不在 PATH 时用 `node <本 skill 目录>/src/cli.js <同样参数>`，无需全局安装。例：`htmlmini` 命令报无法识别，直接 node 跑本 skill 目录里的 cli.js。
   - 报 `ERR_MODULE_NOT_FOUND`（如缺 `linkedom`）是依赖未装，不是选型问题：本目录有 `pnpm-lock.yaml`，`package.json` 也声明了 `packageManager`，按锁文件装一次即可，缺 pnpm 时**不必先全局安装**——`corepack pnpm install --frozen-lockfile` 随 Node 分发、按 `packageManager` 取版本（详见 `README.md`「安装」）。装完重跑，不改走其他工具，也不换包管理器。

## 模式选择

**先判页面类型再选模式**：文章页（新闻/博客/文档）跑默认 `markdown` 就够；营销/产品/定价页与面板/设计稿优先 `ui`——首屏标题与 CTA、定价卡、按钮、链接都在清单里，而文章引擎会把它们当样板整段剔除。例：产品定价页只跑 `markdown` 会从第一张功能卡开始，首屏标题与全部定价卡都取不到。

| 模式 | 何时用 |
|---|---|
| `markdown`（默认） | 常规总结；文章页走 Defuddle，面板/UI 页自动切组件清单 |
| `json` | 需要元数据（标题/作者/日期）+ `used` 实际引擎 + `reductionPct` 节省统计 |
| `skeleton` | 巨页只要大纲（标题层级 + 表格 + 代码块语言） |
| `ui` | UI 设计稿强制完整清单：标题/地标/表单字段/按钮/表格/图片/链接/文本。清单有预算上限（标题 100、表单字段 100、按钮 100、链接 30、图片 30、文本 200，按**去重后**条数计），超长页尾部（如定价卡只到中间一档）仍可能被截断：见下方"清单被截断时" |
| `html` | 要**结构**而不是摘要时用：保留完整 DOM 与文本顺序，剥掉脚本/样式/模板/图标与注释，属性按 `--attrs`（默认 `semantic` 保 `href/src/alt/colspan/rowspan` 与表格/表单状态），排版按 `--format`（默认 `compact` 压掉源码缩进与空行；`pretty` 重排为可读缩进、`raw` 保留源码空白）。token 高于 `markdown`/`ui`，但不受清单预算截断（看表格、嵌套层级、表单初始态时用它，别去读原始 HTML）。要更小体积再加 `--prune-empty`（剪掉清洗后变空的容器，表格/表单结构豁免） |
| `text` | 纯文本、去掉所有标记 |
| `title` | 只要页面标题 |

同一份内容的模式体积差别很大（以一份营销/产品页实测为例：`ui` ≈17 KB、`markdown` ≈42 KB、`html` ≈106 KB，`html --attrs none` ≈91 KB），所以 `ui` 与 `markdown` 是互补而非替代：`ui` 拿得到首屏标题、CTA 与定价卡，但正文类文本只到标题、没有 FAQ 正文；`markdown` 有长正文，却把首屏、品牌墙、定价卡当样板整段剔除。
产品/定价页的取法是 `ui` 打底，缺长正文再按锚点切出片段补一次 `markdown`。卡在 tab 面板/模板里的内容（定价卡常见）正文引擎会当样板丢，`ui` 与 `html` 能拿到。

`extractor` 默认 `auto`（非HTML透传 → Defuddle → 有则用 Trafilatura → semantic → ui；
面板/表单页 UI 信号多且抽出文字不长时，Trafilatura 让位给 ui 清单），不用指定；
只有排查抽取质量时才强制单个引擎（`--json` 看 `used` 字段确认实际命中）。
非 HTML（markdown/纯文本/JSON，如 gitee 直接返回的 `text/plain`）任何模式下都原样透传（`used=passthrough`）。

同一 URL 只联网抓一次：先把 HTML 落盘（`curl -s -o page.html <URL>`，需要代理时加 `-x <代理>`），之后 `ui` / `markdown` 等模式都读同一份本地文件；换视图不是重抓的理由。

**清单被截断时（`ui` 等清单类输出）**：出现"末尾停在半句"或页面尾部整块缺失（例：定价卡只到中间一档、FAQ 正文没进来），把已落盘的 HTML 按锚点切出片段再喂 htmlmini——从目标区起始标记前的 `<` 切到其后的 `>`，存成片段文件后 `htmlmini 片段.html --mode ui`。
这是"把片段交给提取器"，不是手写正则抠原文；仅用于确认漏内容后补齐，不作为常规路径。

## 动态页流水线（静态抓取不够时）

`htmlmini_extract_url` 只做静态抓取：默认跟随任务/宿主的代理环境变量，可经 `proxy` 参数覆盖（URL 或 `"direct"`）；403/5xx 自动补一次浏览器头重试（同路线）。
一步到位的用法：`htmlmini <URL> --render` 或 MCP `render:true`——静态优先，静态 403/5xx 才自动回退浏览器渲染再按文件模式提取；
渲染链为 save_page（环境就绪时用，同代理，cloak 不必接）→ 本机普通 Chrome 无头 dump-dom（零依赖）→ 友好报错，实际走了哪条会打 `htmlmini: [render] engine=… [proxy: …]` 日志；
Chrome 通路按显式 `--chrome-bin` / `chrome_bin` / `HTMLMINI_CHROME_BIN` → PATH → 系统常用路径 → Playwright 缓存（`PLAYWRIGHT_BROWSERS_PATH` 可改位置，完整版优先取版本最大者）选择；
首次人工验证用 `--headful` / `headful:true`（仅 save_page 通路支持）；
404/超时/断网直接抛错，不烧浏览器时间。
连续/成批多页不要循环调 `--render`（每页一次浏览器创建/销毁，又慢又多新指纹）：同站多页走 `resilient-browser-fetch` 的批量会话（单浏览器预热屏障 + 会话复用 + 受限并发，见其 `references/batch-workflows.md`），落盘后再逐个 `htmlmini_extract_file`；
临时 profile 随会话关闭自动清理，`--profile-dir` 只用于跨重启保留，涨磁盘且不跨进程共用。
手工两步（存量/排查用）：先走 `network-access` 双路对照（直连+代理并行 curl，必要时 `curl_cffi` 做 TLS 级伪装），用胜出路线落盘的正文按文件模式提取，不按 URL 重抓；
静态皆取不到可用正文（含挑战特征）才用 `save_page` 保存渲染后 HTML（同代理），再用 `htmlmini_extract_file` 读该文件（同目录 `<name>.html.meta.json` 会被自动利用，无需手动传 URL）。
例：直连 403、代理 200 落盘，直接提取该文件，不启浏览器；简头 curl 两路 502 但补头现挑战跳转，即转浏览器而非判死。

## 不用 htmlmini 的情况（选型结论）

| 场景 | 用什么 |
|---|---|
| office/pdf/音视频转 Markdown | `markitdown`，htmlmini 只做 HTML |
| 批量新闻正文 + 只要最高精度且有 Python | `pip install trafilatura` 后 htmlmini `auto` 会自动用上，无需换工具 |
| 动态交互页要"可操作结构"而非文本摘要 | 浏览器可访问树（Playwright 类 MCP），而非静态提取 |
| 通用网页正文、图快、且不需要结构化提取或取数 | harness 自带 `web_fetch`：零依赖、保留完整 DOM 顺序，一次调用且不用落盘；不剥样板也不出组件清单。内容在静态 DOM 时卡片类块也能取到，但 tab 面板/layer 模板里的块会漏、FAQ 只给每组首答。判据是目标块在不在静态 DOM 里，不是页面类别；覆盖量与成本对照见 `README.md`「与 harness 内建 fetch 的取舍」 |
| 要给采集/爬虫写选择器、抽取规则或字段契约（产物需长期成立） | 只对原始 HTML 或真实渲染 DOM 编写与回归；htmlmini 的任何模式都是清洗产物，不据它定规则 |

判据是**产物是否沉淀为抽取契约**，不是抓多少页：写规则时对照的**参考对象**（接口 JSON、原始 HTML、渲染后真实 DOM）只能取自站点本身，选择器、字段映射与回归基线都基于它编写。htmlmini 的清洗产物撑不住这件事——静态解析会重排（如 doctype 被提到最前），不是浏览器真实 DOM；`--mode html` 还整棵删掉 `script`/`noscript`/`template` 与注释、归一化文本空白，`--attrs all` 只能救回属性这一项。

反向也成立，下列用途在批量场景照样适用，但都在规则链路之外：

- 站点探路与分层判断（页面是服务端渲染还是客户端渲染、字段在 HTML 还是脚本里、要不要渲染）、页面类型与区块盘点、字段存在性判断；
- 人工抽样核查、一次性小规模导出；
- 产物不充当规则依据且不含选择器时（如把可读文本归档做检索），可作管道组件，但须固定版本并自建回归集守住输出契约。

字段级采集（电商产品数据是典型）先找 JSON 接口与内嵌数据，其次才对原始 HTML 写选择器；判断内嵌数据是否存在只能看原始源码或渲染后 DOM——`schema.org` 的 JSON-LD、`__NEXT_DATA__`、内联 state 正是 htmlmini 会删掉的 `script`，用它数不出来。

## 自检

- URL 或页面取数是否先走提取再回答，未因口语未命中而手抓原文？
- 是否先判了页面类型：营销/产品/定价页与面板/设计稿直接走 `ui`，没有只跑默认 `markdown` 就下结论？
- 目标块在静态 DOM 里、只要正文摘要时，是否先用内建 `web_fetch` 一次调用解决，而不是默认再走抓取 + 落盘 + 多视图提取？
- 同一 URL 是否只联网抓一次、后续各模式复用已落盘的 HTML？
- `ui` 清单疑似被预算截断（末尾停在半途、缺页面尾部内容）时，是否按锚点切片重提取补齐，而非手写正则抠原文？
- 需要的是页面结构（表格、嵌套层级、表单初始态）而非摘要时，是否用 `--mode html`，而不是直接读原始 HTML？
- CLI 缺失时是否用 `node` 跑本 skill 目录的 `cli.js`，而非找全局安装？
- CLI 报 `ERR_MODULE_NOT_FOUND` 时是否先按 lockfile 装依赖再重跑，而非改换工具或手写正则抠原文？
- URL 抓取优先用 `--render` / `render:true` 一条命令（静态优先、403/5xx 自动回退渲染）；手工排查才走双路对照落盘。挑战特征出现才上浏览器，而非 curl 5xx 直接判死？
- 是否按需用 `proxy` 参数或环境代理走指定路线，而非默认直连硬闯？抓取失败先看 `[read] fetching … [proxy: …]`——它写明实际生效的代理与来源（`HTTPS_PROXY`/`--proxy`/`NO_PROXY`/`none`），据此判断是路由不对还是源站问题。
- 是否把清洗产物当成了采集规则或字段契约的依据（参考对象应为站点本身的接口 JSON、原始 HTML 或渲染后 DOM），或在它上面数 JSON-LD/`__NEXT_DATA__` 这类内嵌数据？

## 输出后

直接基于 htmlmini 的输出总结/回答；**不要回读原文验证**。若输出明显为空或标题缺失，可加 `--ui` 或 `--json` 重试一次（`json` 的 `used` 会告诉你命中了哪级引擎）。
图表类数值在提取输出中缺失时如实说明缺失，不回读原文手写正则抠内嵌脚本数据补数；需动态值时按“动态页流水线”重提。
