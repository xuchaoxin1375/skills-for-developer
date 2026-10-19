# 使用案例：按页面类型与症状取命令

`SKILL.md` 只保留"怎么选"；本文件给"具体怎么做"。选项、默认值与完整清单以 `htmlmini --help` / `--list-modes` / `--list-extractors` 为准，这里只写场景、前提和 help 未覆盖的坑。

命令里的 `<URL>`、`page.html` 是占位符；同一 URL 只联网抓一次，后续各模式复用已落盘的文件。

## 索引

| 场景或症状 | 案例 |
|---|---|
| 文章、博客、文档 | 1 |
| 营销 / 产品 / 定价页，要首屏与定价卡 | 2 |
| 面板、仪表盘、设计稿 | 3 |
| 静态 200，但正文要等客户端水合 | 4 |
| 输出只剩区块标题（手风琴 / 折叠面板） | 5 |
| 静态 403/5xx 或出现挑战特征 | 6 |
| 同站多页批量 | 7 |
| 超长页面只要大纲 | 8 |
| 要表格 / 嵌套 / 表单初始态 | 9 |
| 输入是 markdown / 纯文本 / JSON | 10 |

## 1 文章、博客、文档

- 命令：`htmlmini "<URL>" -o page.md`
- 预期：`[extract] used=defuddle`（装了 Trafilatura 时可能 `used=trafilatura`）。
- 坑：首页、列表页、搜索页跑默认 `markdown` 只会得到导航与标题堆叠，换具体文章 URL。
- 坑：`used=ui` 说明页面被判成面板型（UI 信号多、正文短），先确认 URL 对不对，再考虑 `-u` 是否更合适。

## 2 营销 / 产品 / 定价页

两种视图互补，不是替代：

```bash
htmlmini "<URL>" -u -o page.ui.md        # 首屏标题、CTA、定价卡、按钮、链接
htmlmini "<URL>" -m -o page.md           # 长正文（FAQ、描述），首屏与定价卡常被当样板剔除
```

- 预期：`ui` 里有首屏标题与定价卡；`markdown` 里有长段落。
- 坑：只跑 `markdown` 会从第一张功能卡开始，首屏标题与全部定价卡都不在输出里。
- 坑：卡在 tab 面板或模板里的块（定价卡常见）正文引擎当样板丢，`ui` 与 `html` 能拿到。
- 坑：`ui` 是清单，正文类文本只到标题；要完整描述还是得 `markdown` / `text`。
- 体积量级（同一份营销页实测）：`ui` ≈17 KB、`markdown` ≈42 KB、`html` ≈106 KB、`html --attrs none` ≈91 KB。只作量级参考，随页面变化。

## 3 面板、仪表盘、设计稿

- 命令：`htmlmini dashboard.html -u`
- 输出：标题 / 地标 / 表单字段 / 按钮 / 表格 / 图片 alt / 链接 / 文本清单。
- 预算按**去重后**条数计（标题 100、表单字段 100、按钮 100、链接 30、图片 30、文本 200），文本条目另有单条长度上限（默认 150 字符）。
- 症状"末尾停在半句"或页面尾部整块缺失（定价卡只到中间一档、FAQ 正文没进来）：按锚点切片段再喂一次——从目标区起始标记前的 `<` 切到其后的 `>`，存成片段文件后 `htmlmini 片段.html --mode ui`。这是把片段交给提取器，不是手写正则抠原文，只用于确认漏内容后补齐。
- 坑：长段落（商品描述、FAQ 正文、条款）默认整条不收，输出末尾会写明省略了几条；要它们用 `--text-max 0`，或改 `markdown` / `text`。

## 4 静态 200，正文要水合

典型是客户端渲染的详情页：静态抓取返回 200，但 `Details` / `Ingredients` / 参数区只有标题没有正文，`ui` 与 `markdown` 都缺。

- 判据：**渲染后 DOM 有没有**，不是"原始 HTML 有没有"。
- 命令：`htmlmini "<URL>" --render=always -m -o page.md`（MCP `render:"always"`）。
- 预期日志：`[read] … via browser render`，以及 `[render] engine=… [proxy: …]`。
- 坑：默认 `--render` **只对静态 403/5xx 回退**；静态 200 的页面它仍走静态抓取，不水合，很容易误判成"页面没写"。
- 坑：渲染后 `ui` 仍缺长正文，通常不是渲染失败，而是 `ui` 的单条长度上限——换 `markdown` / `text` 或加 `--text-max 0`。
- 要多次复用：先落盘一次 `--render=always --mode html --attrs none -o page.html`，之后 `htmlmini page.html -m` / `-u` 各视图都读本地文件，不必反复启浏览器（单次渲染通常几十秒）。

## 5 输出只剩区块标题

手风琴、标签页、折叠面板的标题在 DOM 里，正文只在数据里。**不要**据此写成"页面未提供"。按序排查：

1. 静态 DOM：目标文字是否真在剥掉 `<script>` 后的 HTML 里；
2. JSON-LD：`application/ld+json` 常带明文摘要（标题、短描述、价格、库存），成本最低；
3. 内联 state：`<script type="application/json" id="…">` 的框架状态缓存，通常是完整正文所在。

要点：

- 这些数据都在 `<script>` 里，**任何模式的输出都不含它们**（`--mode html` 也整棵删 `script`），所以"输出里没有"不等于"页面里没有"。
- 整块 percent-encoded 时开头是 `%7B%22`（`%22` 是引号、`%20` 是空格），`json.loads` 会直接报错，须先 `unquote()` 一次再解析；出现 `%2522` / `%2520` 才是双层编码。
- 同一份正文可能存两份：JSON-LD 短版（SEO 用）与 state 长版，按所需长度选。
- 取法是从落盘 HTML 里按 id / type 单独取出对应 `<script>` 块（只取该块），不读原始 HTML 全文。
- 先按案例 4 渲染一次再判断：如果水合后 DOM 已有正文，直接 `markdown` / `text` 即可，不必碰内联 state。

## 6 静态 403/5xx 或挑战特征

- 一条命令：`htmlmini "<URL>" --render`——静态优先，403/5xx 才回退浏览器渲染，再按文件模式提取。
- 渲染链：save_page（本机有层 ≥1 引擎且更合适时）→ 系统 Chrome 无头 `dump-dom`（零依赖）→ 友好报错。实际通路看 `[render] engine=…`。
- 通路选择：save_page 有求解引擎（scrapling / cloak-cdp）、需要 `--headful`、或本机没有 Chrome 时走 save_page；层 1（playwright / patchright）与 Chrome 同为"只渲染不求解"，此时优先零依赖 Chrome，Chrome 崩了再回退 save_page 重试一次（错误里两段都会出现）。
- save_page 与 Trafilatura 都跑在 Python 解释器上，默认取 PATH 的 `python` / `python3`，**往往不是装了 playwright / scrapling 的那个环境**（conda / venv 常见）。用 `--python-bin <解释器>` / MCP `python_bin` / `HTMLMINI_PYTHON` 指定；`--python-bin auto`（或 `HTMLMINI_PYTHON=auto`）会扫描本机并挑一个具备层 ≥1 引擎的。显式路径不做隐式回退，指错直接报错。`HTMLMINI_ENV_SCAN=0` 关闭扫描。
- `--headful` / `headful:true` 只用于首次人工验证，需要 save_page 通路且有层 ≥1 引擎；Chrome `dump-dom` 不能开窗。
- 404 / 超时 / 断网直接抛错，不烧浏览器时间。
- 手工两步（存量或排查）：先用双路对照（直连 + 代理并行）确定可用路线并落盘，再 `htmlmini page.html`；不按 URL 重抓。

## 7 同站多页批量

- 不要循环调 `--render`：每页一次浏览器创建 / 销毁，又慢又多新指纹。
- 走 `resilient-browser-fetch` 的批量会话（单浏览器预热屏障 + 会话复用 + 受限并发）落盘，再逐个 `htmlmini <file>`；渲染后 HTML 同目录的 `<name>.html.meta.json` 会被自动利用，不用手传 URL。
- 详见 [batch-workflows.md](../../resilient-browser-fetch/references/batch-workflows.md)。

## 8 超长页面只要大纲

- 命令：`htmlmini page.html -s`（或 `--mode skeleton`）。
- 输出：标题层级 + 表格 + 代码块语言，用于先摸结构再决定提取哪块。

## 9 要结构而不是摘要

- 命令：`htmlmini page.html --mode html`
- 默认 `--attrs semantic`（保 `href/src/alt/colspan/rowspan` 与表格 / 表单状态）、`--format compact`（压掉源码缩进与空行）。
- 更小：`--attrs none`、`--prune-empty`；更好读：`--format pretty`。
- 坑：清洗产物会重排（doctype 被提到最前），**不是**浏览器真实 DOM；写选择器 / 字段契约仍要回原始 HTML 或渲染后 DOM。

## 10 非 HTML 输入

- markdown / 纯文本 / JSON 在任何模式下原样透传（`used=passthrough`），标题取首个 `#` 或首行。
- 不要指望对 markdown 做抽取；需要正文摘要请直接读输入。

## 通用坑

- 同一 URL 只联网抓一次，换视图不是重抓的理由。
- 判断这次到底命中哪个引擎，看 `--json` 的 `used`；记录结果出处时一并记 `version`（`htmlmini --version`）。
- `ui` 与 `markdown` 互补：前者有首屏与卡片但正文只到标题，后者有长正文但剔除首屏与定价卡。
- 需要排查"是不是内容根本没下发"时，先看案例 4（渲染一次）再看案例 5（内嵌数据），顺序反了会白解码。
