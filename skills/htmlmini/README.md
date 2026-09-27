# htmlmini v2

把 HTML 网页（含大量 CSS/JS 样板）压成"核心骨架"，以 Markdown 输出，专为 **LLM 总结省 token** 设计。实测本地设计稿：原始 24KB~99KB → 提取后 300B~1.3KB，**节省约 75%~99.5%**。

- 引擎链（`auto` 默认）：**Defuddle** 正文提取 → **Trafilatura**（可选，见下）→ **semantic** 纯 JS 语义回退 → **UI 组件清单**（面板/仪表盘/设计稿）。
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
npm install
npm link        # 可选：全局注册 htmlmini 命令（Windows 会生成 .cmd 垫片）
```

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

动态/受保护页面先渲染，再提取（`save_page` 会在 HTML 旁生成 `<name>.html.meta.json`，htmlmini 自动读取其中的真实 URL 参与提取并回填到 `--json` 的 `meta` 字段）：

```bash
python ../resilient-browser-fetch/scripts/example_save_page.py "https://example.com/app" --out app.html
htmlmini app.html --json
```

## MCP 接入

启动：`node <仓库>/skills/htmlmini/src/mcp.js`（stdio）。六个工具：3 个正式名 + 3 个旧拼写别名（`htmmini_*`，v0.1 兼容保留）。

| 工具 | 说明 |
|---|---|
| `htmlmini_extract_file(path, mode?, extractor?)` | 提取本地 HTML 文件（含渲染后产物） |
| `htmlmini_extract_url(url, mode?, extractor?)` | 抓取并提取远程 URL（静态抓取；动态页走上面流水线） |
| `htmlmini_extract_html(html_content, mode?, extractor?)` | 就地清洗一段已抓取的 HTML 字符串 |

`mode`：`markdown`(默认) | `skeleton` | `text` | `json` | `title` | `ui`；
`extractor`：`auto`(默认) | `defuddle` | `trafilatura` | `semantic` | `ui`。

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
  (+同目录.meta   │  1. linkedom 解析                 │
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
npm test                        # 内置合成 fixture，17 项断言
node tests/test-mcp.mjs         # MCP 6 工具 + 别名调用
node tests/test-batch.mjs <目录>  # 本地 HTML 目录批量抽查（fixture 不入库）
```

## 从 v0.1 迁移

- MCP 工具改名 `htmmini_*` → `htmlmini_*`，旧名保留为别名，已配置的客户端不用改。
- 新增 `--mode/--extractor/--completion`，原有单字母 flags 全兼容。
- 实现体已收进本仓库（`src/` + `package.json` + `tests/` + `completions/`），MCP 配置里的绝对路径请改为 `<仓库>/skills/htmlmini/src/mcp.js`；旧 `Desktop/code_demo/htmlmini` 副本可删除。
- UI 清单不再认样式类：只靠 `class="btn"` 标识的"按钮"不会再进 `## 按钮`（会出现在 `## 文本`），请用 `<button>` 或 `role="button"`。

免责声明：Defuddle 与 linkedom 均以 Apache-2.0 / MIT 开源，本封装代码位于 `src/`，Trafilatura 为可选外部依赖（GPL-2.0，仅在用户自行安装时调用，不随本仓库分发）。
