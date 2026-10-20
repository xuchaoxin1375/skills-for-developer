---
name: htmlmini
description: >
  凡是需要总结、分析、审查网页或 HTML 文件，或从 URL/页面取表格、榜单、分数、规格等数据，
  先使用本 skill 提取核心骨架再回答；包括本地设计稿、后台面板、仪表盘与页面源码，
  即使用户没点名 htmlmini。默认不整份读取原始 HTML。
  Also use for "summarize/analyze/review this page or HTML" and "extract the table/scores/rankings from this URL".
  不用于把清洗产物当作采集选择器/字段契约的依据，也不用于 office/PDF 转换或动态交互页的可操作结构。
---

# htmlmini — 网页核心骨架提取

把 HTML 压成核心骨架再交给模型，省掉 CSS/JS 与页面样板。先按页面类型选模式；细节和症状处理按链接跳转，不在正文重复。

## 使用边界

适合：

- 总结、分析、审查 HTML 文件或网页，包括本地设计稿、面板、仪表盘、页面源码。
- 带 URL 或页面做取数：表格、榜单、分数、规格、价格等。先提取核对覆盖度，再回答；论坛、评论区、列表页的总数按[案例 12](references/usage-cases.md#12-论坛评论区列表页首屏不是全部)用站点自身计数核对。
- 需要组件清单、页面结构、落盘复用，或正文要渲染后才出现。
- 页面由后端接口供数（SPA、白标商城、后台面板），要完整字段或核对展示值：先提取可见内容，再按[案例 11](references/usage-cases.md#11-后端接口--xhr-数据源)查接口 JSON。

先考虑其他能力：

- 目标块在静态 DOM、只要正文摘要：harness 有内建 `web_fetch` 时先用它。一次调用、零依赖、不落盘；缺点是不剥样板、不出组件清单。判据是目标块在不在静态 DOM，不是页面类别。
- 要组件清单、表格结构、取数或落盘复用：用 htmlmini。
- 写采集选择器或字段契约：只对照站点原始 HTML 或真实渲染 DOM，不用本 skill 的清洗产物。
- office/PDF/音视频转 Markdown：`markitdown`；动态交互页要可操作结构：Playwright 类 MCP。

**不要整份 `Read` 原始 HTML**：CSS/JS 常占 90%+。只有排查内嵌数据或编写选择器时，才定点读取相关 `<script>` 或原始节点。

## 选择模式

| 目标 | 起手 |
|---|---|
| 文章、博客、文档 | `markdown`（默认） |
| 营销、产品、定价、面板、设计稿 | `--mode ui`；缺长正文再补 `markdown` |
| 表格、嵌套层级、表单初始态 | `--mode html` |
| 巨页只要大纲 | `skeleton` |
| 纯文本 / 只要标题 | `text` / `title` |
| 元数据、实际引擎 | `json` |

`ui` 与 `markdown` 互补：`ui` 有首屏标题、CTA 与定价卡，但正文只到标题；`markdown` 有长正文，却常把首屏与定价卡当样板剔除。营销/定价页用 `ui` 打底，缺长正文再按锚点切片补 `markdown`。完整取舍见[案例 2](references/usage-cases.md#2-营销--产品--定价页)。`html` 用于要结构而不是摘要，选项见[案例 9](references/usage-cases.md#9-要结构而不是摘要)与 `--help`。

URL 状态：静态 200 但正文为空加 `--render=always`；静态 403/5xx 加 `--render`。同一 URL 只联网抓一次：先落盘，再用不同模式读同一份文件；多视图复用的落盘命令见[案例 4](references/usage-cases.md#4-静态-200正文要水合)。

`extractor` 默认 `auto`，通常不用指定；排查抽取质量时用 `--json` 的 `used` 确认实际引擎。非 HTML 输入（markdown/纯文本/JSON）在任何模式下原样透传。

## 调用方式

1. MCP（已配置时）：`htmlmini_extract_file(path)` / `htmlmini_extract_url(url)` / `htmlmini_extract_html(html_content)`，可选 `mode`、`extractor`。旧拼写 `htmmini_*` 是兼容别名。
2. CLI：`htmlmini <文件|URL|stdin> [--mode <模式>]`。选项、默认值与完整清单以 `htmlmini --help` / `--list-modes` / `--list-extractors` 为准。
   - 进度日志走 stderr，行首带方括号本地时间戳（`[YYYY-MM-DD HH:mm:ss,SSS]`，同 Python logging），故相邻行可直接相减看阶段耗时；`[read]` 行带抓取状态码（`status=…`）。stdout 只放载荷与一对来源哨兵行，不要时加 `--no-source-marks`。要安静用 `--quiet`，排查用 `--verbose`。
   - 落盘用 `-o <文件>`；不要用 PowerShell 管道接 `Set-Content` 收载荷。
   - CLI 不在 PATH：用 `node <本 skill 目录>/src/cli.js <同样参数>`。
   - 报 `ERR_MODULE_NOT_FOUND`：依赖未装。在 skill 目录运行 `corepack pnpm install --frozen-lockfile` 后重跑，不改换工具。

## 结果不对时

按症状走，不要先怀疑页面没内容：

- **输出只剩区块标题/正文为空**：先判断是否客户端渲染；是则按[案例 4](references/usage-cases.md#4-静态-200正文要水合)用 `--render=always` 渲染一次，确认水合后的 DOM 有没有正文。仍为空（或本来就是静态页）再按[案例 5](references/usage-cases.md#5-输出只剩区块标题)查 JSON-LD 与内联 state。任何模式的输出都不含 `<script>`，"输出里没有"不等于"页面里没有"。
- **`ui` 清单末尾被截断或长段落整条缺失**：预算与长文本上限见[案例 3](references/usage-cases.md#3-面板仪表盘设计稿)；换 `markdown` / `text`，或按锚点切出目标片段再喂一次 `ui`。
- **403/5xx/挑战页**：先加 `--render`，静态失败才回退浏览器；静态 200 但仍被挑战或需要求解时，走 `resilient-browser-fetch` 的 save_page 落盘后再提取。渲染后仍是挑战空壳时 htmlmini 会直接点名挑战特征并按[案例 6](references/usage-cases.md#6-静态-4035xx-或挑战特征)继续，不会让你反复 `--render=always`。本地引擎与有头浏览器都不行、或页面需要你的登录态时，用自己浏览器导出 HTML 再提取；第三方 reader 与归档辅助路线（含免费额度与边界）见 [references/aux-readers.md](references/aux-readers.md)，使用前需用户同意。404/超时/断网直接报错。
- **两个渲染通路都失败、或日志里解释器不像是装了引擎的那个**：只要没显式指定 `--python-bin`，htmlmini 已会自动扫描本机解释器并换更强的那个重试一次（层 2/3 优先，日志 `[render]` 打印两次用的解释器）。仍失败时才手动收窄：`--python-bin auto` 固定为扫描结果，或用 `<resilient-browser-fetch>/scripts/check_environment.py --list-envs` 找出带 scrapling/cloak-cdp 的那个环境再指名路径；不要因为默认 `python` 缺引擎就下"页面取不到"的结论。需要整机资源全景时先跑 [resource-inventory](../resource-inventory/SKILL.md)。
- **价格/计量与页面观感不符**：优先用 JSON-LD、`itemprop` 或接口 JSON 核对；CSS 生成内容的限制见[案例 2](references/usage-cases.md#2-营销--产品--定价页)。
- **SPA 渲染后仍缺字段或只有展示值**：查页面自己的后端接口（[案例 11](references/usage-cases.md#11-后端接口--xhr-数据源)），用返回 JSON 核对；不猜路径、不读整份 JS。

## 输出后

直接基于提取结果回答，不回读原文验证。输出明显为空或标题缺失时，可改用 `--mode ui` 重试一次；要看命中的引擎、元数据或版本，用 `--json`（`used` 会说明实际引擎）。

正文类字段缺失按“结果不对时”排查后再回答；图表类数值缺失就如实说明缺失，不回读原文、不手写正则从内嵌脚本抠数。

## 自检

- 取数是否先提取再回答，没有整份读原始 HTML？
- 是否先判了页面类型：营销/产品/定价/面板走 `ui`，要结构走 `html`？
- 目标块在静态 DOM 且只要摘要时，是否先用 `web_fetch`？
- 同一 URL 是否只抓一次，后续模式复用落盘文件？
- 论坛、列表、评论区是否用站点自身的总数或分页接口核对覆盖范围，而不是拿渲染后的节点数当全量？
- 客户端渲染页空输出时，是否先 `--render=always`、再查内嵌数据，而不是写成“页面未提供”？挑战特征明显时，是否换求解通路而不是反复渲染？渲染失败时，是否先看自动升档后的解释器与日志，而不是直接判定“页面取不到”？
- 字段不全或数值可疑时，是否核对页面自带的结构化数据/接口 JSON，而不是只信渲染文本或猜接口？
- 写选择器/字段契约时，是否只对照原始 HTML 或真实渲染 DOM？

## 按需深入

- [references/usage-cases.md](references/usage-cases.md)：按页面类型与症状取命令。文章 1、营销/定价 2、面板 3、水合 4、内嵌数据 5、403/5xx 6、批量 7、大纲 8、结构 9、非 HTML 10、后端接口 11、论坛/列表 12。
- [README.md](README.md)：安装、模式与体积对照、与内建 fetch 的取舍、日志、MCP、架构。
- 同站批量渲染与并发：`resilient-browser-fetch` 的 `references/batch-workflows.md`。
