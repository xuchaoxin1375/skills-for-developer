# htmlmini v2

把 HTML 网页（含大量 CSS/JS 样板）压成"核心骨架"，以 Markdown 输出，专为 **LLM 总结省 token** 设计。实测本地设计稿：原始 24KB~99KB → 提取后 300B~1.3KB，**节省约 75%~99.5%**。

- 引擎链（`auto` 默认）：**非 HTML 透传** → **Defuddle** 正文提取 → **Trafilatura**（可选，见下）→ **semantic** 纯 JS 语义回退 → **UI 组件清单**（面板/仪表盘/设计稿）。`text/plain` 直接返回的 markdown（如某些 gitee 链接）、纯文本、JSON 不硬抽，原样返回（`used=passthrough`）。
- 双形态交付：**CLI**（任意 harness/终端可用）+ **MCP server**（opencode / Claude / Cursor 等当工具调用），共用同一核心，行为一致。

## 为什么是这个选型（结论）

JS 静态提取这条线上，[Defuddle](https://github.com/kepano/defuddle)（Obsidian 团队维护）已经是上位选择：相对 Mozilla Readability，对代码块/LaTeX/现代 SPA 更宽容，还有站点抽取器注册表。没有直接 drop-in 更强的 JS 方案。

| 工具 | 定位 | 相对 htmlmini |
|---|---|---|
| `Mozilla Readability` / `@extractus/article-extractor` | 经典正文提取 | 下位：保守启发式，代码块/SPA 易损坏 |
| `Trafilatura`（Python） | 基准测试精度冠军，多语言/元数据强 | 正文质量上位，已作为**可选二级引擎**接入（`pip install trafilatura` 后自动生效，缺席静默跳过） |
| `Microsoft MarkItDown`（+ `markitdown-mcp`） | 通用文件转 Markdown（pdf/docx/xlsx/html…） | 更通用但 HTML 去样板弱于 Defuddle；office/pdf 类任务请用它，不归 htmlmini 管 |
| `Playwright MCP` / Firecrawl / Jina Reader | 浏览器渲染 + 可访问树 / 托管提取 | 动态 JS/强反爬场景的上位，但重（浏览器/付费服务/联网）；htmlmini 只做静态，动态页先走 `resilient-browser-fetch` 渲染再喂给 htmlmini（见"流水线"） |
| `pandoc` / `html2text` / `inscriptis` | 格式转换 | 只转格式不去样板，省 token 远不如 |

UI/面板页是所有静态提取器的共同短板：没有"文章正文"可抽。v2 的做法是**按可访问语义**输出组件清单（标题/地标/表单字段/按钮/表格/图片 alt/链接/文本），只认语义标签与 ARIA，不再用 `class*="btn"` 之类正则猜样式类。

## 安装

```bash
cd skills/htmlmini
pnpm install --frozen-lockfile
# 无需全局安装：用 pnpm exec htmlmini 或 node src/cli.js 直接跑
```

没装 pnpm 时不必先全局安装：Node 自带 Corepack，在项目目录执行 `corepack pnpm install --frozen-lockfile` 会按 `package.json` 的 `packageManager` 取对应 pnpm 版本（首次会下载 pnpm 本体，其来源独立于 npm registry）。需要 `pnpm` 命令常驻时再用 `corepack enable`（写 Node 安装目录，Windows 下可能需要管理员）或 `npm i -g pnpm`——装全局工具、改 PATH 属机器变更，先向用户说明命令与影响再执行。

确实拿不到 pnpm 时，`npm install --no-package-lock --omit=dev` 不读 `pnpm-lock.yaml`，依赖版本可能与锁定不一致，只能作临时通路。国内镜像与 Corepack 下载源见 `network-access` 的 [依赖下载](../network-access/references/dependency-downloads.md)。

可选增强：`pip install trafilatura`（`auto` 链自动检测，有则用，无则跳过，不报错）。

补全：`htmlmini --completion bash|powershell`，或直接引用 `completions/` 下同名文件。

## CLI 用法

```bash
htmlmini <文件|URL|-stdin> [选项]

  -m, --markdown   输出 Markdown（默认；UI 页自动切清单）
  -j, --json       输出 JSON {title, used, requested, content, stats{reductionPct}, meta?}
  -s, --skeleton   仅大纲：标题层级 / 表格 / 代码块语言
  -u, --ui         强制 UI 组件清单
  -t, --text       纯文本
  -T, --title      仅标题
  --mode <name>    上述模式的显式写法（--mode=json 与 -j 等价）
  --extractor <n>  auto（默认）| defuddle | trafilatura | semantic | ui
                   强制指定返回该引擎原始结果（不静默切换），便于排查；
                   auto 失败不抛错，只在强制 trafilatura 缺模块时提示安装。
  --proxy <url>      本次抓取的代理覆盖：http(s) URL，或 "direct" 强制直连；
                   省略则跟随 HTTP_PROXY/HTTPS_PROXY/NO_PROXY 环境变量
  --noproxy          强制直连，忽略环境代理
  --render           静态 403/5xx 时回退浏览器渲染再提取：
                   save_page（需其 Python 环境）→ 系统 Chrome 无头 dump-dom
                   （零依赖）→ 友好报错；404/超时/断网直接抛错，不渲染
  --headful          回退渲染时显示浏览器窗口（隐含 --render；仅 save_page
                   通路支持，用于首次人工验证）
  --render-timeout-ms <ms>
                   回退渲染的超时（默认 300000；Chrome 通路封顶 120000）
  --chrome-bin <path>
                   Chrome/Chromium 可执行文件显式路径（覆盖自动探测；
                   或设环境变量 HTMLMINI_CHROME_BIN）
  --list-modes / --list-extractors / --completion <shell>
  -o, --output <文件>

示例：
  htmlmini page.html
  htmlmini page.html --json
  htmlmini 报表面板.html -u
  htmlmini dashboard.html --mode json --extractor ui
  htmlmini https://example.com/a -s
  curl -s URL | htmlmini - -t
```

## 与 resilient-browser-fetch 的流水线

静态抓取先跟随环境代理、403/5xx 自动补一次浏览器头；仍失败时两种走法：

```bash
# 一条命令（静态优先，403/5xx 自动回退渲染；cloak 不必接，
# save_page 环境就绪用它，否则用本机普通 Chrome 无头直渲）
htmlmini "https://example.com/app" --render --proxy 'http://127.0.0.1:<port>' --json

# 浏览器选择（Chrome 通路）：显式 --chrome-bin / HTMLMINI_CHROME_BIN 优先，
# 否则自动探测——PATH（google-chrome、chrome、chromium 等）→ 系统常用路径 →
# Playwright 浏览器缓存（ms-playwright，完整版优先、无头壳兜底，取版本最大者；
# 自定义缓存位置走 PLAYWRIGHT_BROWSERS_PATH）。实际用了哪个看
# `htmlmini: [render] engine=… src=…` 日志。

# 首次人工验证（save_page 通路开有头窗口；Chrome 通路不支持有头）
htmlmini "https://example.com/app" --render --headful

# 手工两步（渲染产物旁的 <name>.html.meta.json 会被自动利用）
python ../resilient-browser-fetch/scripts/example_save_page.py "https://example.com/app" --out app.html --proxy 'http://127.0.0.1:<port>'
htmlmini app.html --json
```

连续/成批多页不要循环调 `htmlmini URL --render`——每页一次浏览器创建/销毁，
又慢又多新指纹，`--render` 只适合单页/零星几页。同站多页走
`resilient-browser-fetch` 的批量会话（见其 `references/batch-workflows.md`：
单浏览器预热屏障 + 会话复用 + 受限并发），落盘后再逐个 `htmlmini_extract_file`。
临时 profile 默认随会话关闭自动清理；只有跨重启保留人工验证才用专用
`--profile-dir`（会积累缓存涨磁盘，不跨进程共用，用后确认再删）。

`--render` 只在静态 403/5xx 时触发（404/超时/断网直接抛错）；
渲染日志以 `htmlmini: [render]` 为前缀实时打到 stderr（子进程经 `-X utf8` + `PYTHONUTF8=1` 强制 UTF-8 输出；Windows 控制台查看中文时按 powershell-pitfalls 的 UTF-8 模板设置输出编码）。`save_page` 的真实 URL 即原 URL，直接提取即可。

## MCP 接入

启动：`node <仓库>/skills/htmlmini/src/mcp.js`（stdio）。六个工具：3 个正式名 + 3 个旧拼写别名（`htmmini_*`，v0.1 兼容保留）。

| 工具 | 说明 |
|---|---|
| `htmlmini_extract_file(path, mode?, extractor?)` | 提取本地 HTML 文件（含渲染后产物） |
| `htmlmini_extract_url(url, mode?, extractor?, proxy?, render?, render_timeout_ms?)` | 抓取并提取远程 URL（静态抓取：跟随环境代理，403/5xx 补一次浏览器头；`render` 为 true 时静态 403/5xx 自动回退浏览器渲染；动态页也可走上面流水线） |
| `htmlmini_extract_html(html_content, mode?, extractor?)` | 就地清洗一段已抓取的 HTML 字符串 |

`mode`：`markdown`(默认) | `skeleton` | `text` | `json` | `title` | `ui`；
`extractor`：`auto`(默认) | `defuddle` | `trafilatura` | `semantic` | `ui` | `passthrough`。

opencode（`opencode.json`，路径按本机仓库位置改）：

```json
{
  "mcp": {
    "htmlmini": {
      "type": "local",
      "command": ["node", "<仓库>/skills/htmlmini/src/mcp.js"],
      "enabled": true
    }
  }
}
```

Claude Desktop / Cursor（`claude_desktop_config.json` / Cursor MCP 设置）：

```json
{
  "mcpServers": {
    "htmlmini": {
      "command": "node",
      "args": ["<仓库>/skills/htmlmini/src/mcp.js"]
    }
  }
}
```

Claude Code：

```bash
claude mcp add htmlmini -- node <仓库>/skills/htmlmini/src/mcp.js
```

## 架构

```
                  ┌─────────────────────────────────┐
  HTML/URL/stdin  │ src/extract.js                   │──▶ Markdown / JSON / 大纲
  (+同目录.meta   │  0. 非HTML透传（md/txt/json）      │──▶ used=passthrough
   .json可选)     │  1. linkedom 解析                 │
   .json可选)     │  2. Defuddle 正文                 │──▶ used=defuddle
  ─────────────▶  │  3. Trafilatura（可选，有则用）    │──▶ used=trafilatura
                  │  4. semantic 语义回退             │──▶ used=semantic
                  │  5. UI 可访问语义清单             │──▶ used=ui
                  └──────────────┬──────────────────┘
          src/cli.js（CLI）       │     src/mcp.js（stdio MCP server）
         + completions/          │     正式名 htmlmini_* + 别名 htmmini_*
                  共用同一核心，行为一致
```

`--json` 的 `used` 标明实际命中的引擎，`requested` 标明请求的引擎，便于判断输出性质与排查。

## 自检

```bash
pnpm test                         # smoke 17 + MCP 自检 + 可靠性 95，全内置合成输入与本地回环，无外部网络依赖
node tests/test-batch.mjs <目录>  # 本地 HTML 目录批量抽查（fixture 不入库）
```

远程抓取默认 30s 超时（`fetch timeout after …`），终端裸跑无管道时直接提示而不挂等 stdin。抓取跟随 HTTP_PROXY/HTTPS_PROXY/NO_PROXY（`--proxy` 覆盖、`--noproxy` 强制直连）；403/5xx 自动补一次浏览器头重试，仍失败在状态码后带下一步指引，挑战特征会点名，429 遵守冷却。

## 从 v0.1 迁移

- MCP 工具改名 `htmmini_*` → `htmlmini_*`，旧名保留为别名，已配置的客户端不用改。
- 新增 `--mode/--extractor/--completion`，原有单字母 flags 全兼容。
- 实现体已收进本仓库（`src/` + `package.json` + `tests/` + `completions/`），MCP 配置里的绝对路径请改为 `<仓库>/skills/htmlmini/src/mcp.js`；旧 `Desktop/code_demo/htmlmini` 副本可删除。
- UI 清单不再认样式类：只靠 `class="btn"` 标识的"按钮"不会再进 `## 按钮`（会出现在 `## 文本`），请用 `<button>` 或 `role="button"`。

免责声明：Defuddle 与 linkedom 均以 Apache-2.0 / MIT 开源，本封装代码位于 `src/`，Trafilatura 为可选外部依赖（GPL-2.0，仅在用户自行安装时调用，不随本仓库分发）。
