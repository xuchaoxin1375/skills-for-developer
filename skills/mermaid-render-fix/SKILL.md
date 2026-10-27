---
name: mermaid-render-fix
description: >
  诊断并修复渲染失败的 Mermaid 图：提取代码块复现 Parse error，按报错行修复后用 mmdc 或 kroki 复验；
  也用于体检/规范化现有 Mermaid 块（引号与转义、跨渲染器版本隐患、象限图非 ASCII 文案）。
  渲染失败、Parse error、节点含方括号导致断裂、检查或规范化 mermaid 代码时使用；纯新建图或排版统一走 markdown-style。
---

# Mermaid 渲染失败修复

## 适用范围

输入是 Mermaid 代码块，有两种入口：渲染失败要复现并修复，或渲染正常但要体检/规范化（跨渲染器分发、
修好一处后同类行连带排查）。产出可独立渲染的最小修改版，不重排图结构。语法规则的维护位置在
`../markdown-style/SKILL.md` 的 Mermaid 一节，本 skill 只保留最高频根因摘要与体检清单，
完整转义规则以该正本为准。只改写法不改图语义；渲染正常但样式不好看不归本 skill 管。

## 工作流程

1. **提块**：从文档提取 `mermaid` 块存临时 `.mmd`，禁手抄。先跑 `python -X utf8 scripts/check_mermaid.py <文件>` 做秒级预检（仅需 Python 3.9+，无第三方包）。
2. **探测依赖**：先确认 mmdc、包管理器与浏览器；文档目录通常没有 `package.json`/`node_modules`，直接 `pnpm exec` 会报 `Command "mmdc" not found`。三条命令跨平台通用（Windows 写 `where` 亦可）：
   ```bash
   command -v mmdc pnpm npx
   ```
   浏览器写成 puppeteer 配置再传给 `-p`，如 `{"executablePath": "/usr/bin/google-chrome"}`，免下载 Chromium。浏览器探测、临时配置和本步骤其余环节都由 `render_mmd.py` 自动完成。
3. **复现**：优先用 `scripts/render_mmd.py`（Python 3.9+，仅标准库，Windows/Linux/macOS 同一份），一条命令完成预检、渲染与耗时上报；它自动探测浏览器（Chrome/Edge/Chromium，含 Playwright 自带的那份）并生成临时 puppeteer 配置，不下载 Chromium。退出码 0 成功 / 1 输入或用法 / 2 预检 SUSPICIOUS（仅 `-c`）/ 3 无渲染器 / 4 渲染失败或产物缺失 / 5 无浏览器。
   ```bash
   python -X utf8 render_mmd.py -i block.mmd                        # 默认出 PNG：parse 校验与目视一次完成
   python -X utf8 render_mmd.py -i block.mmd -o block.svg -s 1200   # 需要矢量交付时再单独出 SVG
   python -X utf8 render_mmd.py -i block.mmd -c                     # 只跑预检
   ```
   选项与取值以 `--help` 为准，本文不重复清单。
   需要手工控制时才拆开跑：
   ```bash
   PUPPETEER_SKIP_DOWNLOAD=true pnpm exec mmdc -p <puppeteer-config.json> -i block.mmd -o block.png
   ```
   - **先确认已装版本再写参数**：`mmdc --version` 与 `mmdc --help`。12.x 移除了 `-w/--width`，
     尺寸改用 `--size`；puppeteer 配置的长名为 `--puppeteerConfigFile`（`-p` 仍可用）。
   - 本机无 mmdc：把前缀换成 `pnpm dlx --allow-build=puppeteer --package @mermaid-js/mermaid-cli mmdc` 或 `npx -y -p @mermaid-js/mermaid-cli mmdc`；pnpm 10+ 默认拦截 puppeteer 构建脚本，需带 `--allow-build=puppeteer`（漏加报 `ERR_PNPM_IGNORED_BUILDS`），pnpm 9 及以下无此参数、去掉即可。单次运行不装全局；首次联网下载，先按 `network-access` 选路。
   - **以产物判成功，不只看退出码**：mermaid-cli 在 Parse error 时可能仍返回 0（经 pnpm/包装层时更常见）；
     产物不存在或为空即失败（脚本已内置该校验，手工跑时自行检查文件与大小）。
   - 渲染器不可用：用 kroki 交叉验证，非 2xx 时读响应正文的行号。
     ```bash
     curl -sS -X POST -H "Content-Type: text/plain" --data-binary @block.mmd https://kroki.io/mermaid/svg -o block.svg
     ```
   - 高频使用再全局安装：全局工具用 `npm i -g @mermaid-js/mermaid-cli`（pnpm 的全局 bin 默认不在 PATH，
     不为装机工具去改 shell 配置），装时设 `PUPPETEER_SKIP_DOWNLOAD=true` 免下 Chromium；先征询不擅自改环境。
4. **修**：每次只改报错行及同类行。最高频根因是节点文本里的 `[` 未加引号
   （报错常为 `got 'SQS'`），修法是给整个节点文本加双引号，
   如 `G["...[Console]::OutputEncoding..."]`。其余转义查 markdown-style 正本。
   第二类根因是 `quadrantChart` 里未加引号的非 ASCII 文案（轴文案、`quadrant-N` 文案、点名称）：
   Mermaid 10.x–11.x 报 `Lexical error on line N. Unrecognized text.`，插入符落在出问题的那段 token 上，
   修法同样是给该段加双引号，不改写图语义；12.x 起不加引号也能渲染，跨版本分发仍统一加。
5. **复验**：重跑同一条路径，`RENDER=OK`（脚本）或 `EXIT=0` 才算通过；再目视产物确认中文与特殊符号。
6. **回写**：把验证过的块写回原位置，保持最小 diff；报告根因行、改法与两次 EXIT。

## 体检与规范化（可渲染不等于安全）

用户要求“检查/规范化/审一下这段 mermaid”，或要把图贴到别的渲染器（编辑器插件、文档站内嵌版本
常停在 10.x/11.x）时走这一节：先预检，再按图类型过清单，有渲染器时仍以产物为准。

**规范化按兼容性定写法，不按手头渲染器定写法。** 先确认目标环境的 Mermaid 版本，写法取“能覆盖最低
目标版本”的那一种；同一写法在低版本也通过才算稳。手头高版本能渲染，不代表交出去能用。

- 引号是兼容性开关，不是风格偏好：12.x 会把引号剥掉不显示，10.x–11.x 里多数图类型要靠它才能解析；例外见下表。
- 所有图通用：标签文本用双引号包裹；时序图 `;` 写 `#59;`；换行写 `<br>`。
- 非 ASCII 文案的支持下限随写法变化（实测，见验证协议）：

  | 图类型 | 最稳写法 | 支持下限 |
  | --- | --- | --- |
  | `quadrantChart` | 轴文案、象限文案、点名称逐处加 `"…"` | 10.9（不加引号需 12.x） |
  | `architecture-beta` | 全英文标签，边写 `-->` 或 `--` | 11.1 |
  | `architecture-beta` | 中文标签逐处加 `"…"` | 11.13（11.12.3 及以下连引号都拒） |

  要覆盖更老版本就往最省事的一格降级（架构图退英文标签），并在交付处写明所需版本下限。
- `quadrantChart`：`x-axis "低" --> "高"` 两侧都保留 `-->`，缺箭头不会提示“缺箭头”，而是报词法/解析错误；
  点格式 `"名称": [x, y]`，`x`/`y` 必须落在 `0`–`1`（越界同样只报词法错误，容易被误当成语法写错）；
  `quadrant-1` 右上、`quadrant-2` 左上、`quadrant-3` 左下、`quadrant-4` 右下；象限文案与轴方向
  冲突（如右下角写“立刻做”）时报给用户确认，不靠挪数据点掩盖。
- `architecture-beta`：标签画在图标框下方，从 `B`/`T` 出口的边会穿过标签文字（实测 `web:B --> T:cache`
  压住“Web服务”），优先改用 `L`/`R` 横向端口，端点保持成对（`R`↔`L`、`T`↔`B`）。
- 版本敏感项：低版本渲染器报错、高版本正常时，按低版本可渲染的写法收敛，再决定是否升级；
  不用“我这边能渲染”当结论。
- **排布差异不是语法错**：12.0.0 起默认布局引擎由 dagre 换成 ELK，同一段代码的节点位置会变。
  典型是子图内互不相连的节点：dagre 让它们共享一个 rank、沿与 `direction` 垂直的轴排
  （`TB` 横排、`LR` 竖排），ELK 则纵向分层。复现旧排布用 `layout: 'dagre'`；
  跨版本分发用 `~~~` 钉住顺序，不依赖引擎的默认摆放。
- 输出按“行号 + 隐患 + 改法”列出，并区分会直接失败的、只在低版本失败的，以及规范化结果支持的版本下限。

## 约束

- 复验通过前不写回原文件；非零退出码或 `RENDER=FAILED` 的输出不作为完成证据。
- 不重排图结构，不批量改文件编码；时序图分号等细节以 markdown-style 为准，不自立第二套规则。
- 预检只做启发式提示，不能替代真实渲染结论；预检自身失败（解释器过旧、脚本异常）不阻断渲染。

## 验证协议

- `check_mermaid.py` 在已知坏块上报 SUSPICIOUS、修好后报 OK（本次已实跑）。
- `check_mermaid.py` 的象限图规则：未加引号的中文轴文案/象限文案/点名称、缺 `-->`、坐标超出 `0`~`1` 均报 SUSPICIOUS，
  全部加引号并改正坐标后报 OK；既有流程图节点 `[` 与时序图 `;` 两条规则未回归（本次已实跑）。
- `check_mermaid.py` 的架构图规则：裸中文标签报 SUSPICIOUS 并提示“需 ≥11.13 或改英文”，逐处加引号与全英文样例
  报 OK，`junction` 行不误报（本次已实跑）。
- 非 ASCII 引号根因：同一块在 Mermaid 10.9.1、11.4.0 复现 `Lexical error on line 3. Unrecognized text.`（插入符位置一致），
  加双引号后渲染通过且 SVG 文本中无残留引号；12.2.0 上不加引号也能渲染（本次已实跑）。
- 非 ASCII 版本矩阵（逐版本跑 `mermaid.parse` + `render`，取各自 dist 的 UMD 在无头浏览器内测）：
  `quadrantChart` 引号写法自 10.9.1 起可用、裸写法到 11.13.0 仍失败；`architecture-beta` 引号写法
  11.1.0/11.4.0/11.5.0/11.8.0/11.10.1/11.12.3 全部失败、11.13.0 起可用，全英文标签自 11.1.0 起可用
  （`11.13.0` 为 Typora 实测环境）。结论一律钉住具体版本号，不按大版本外推；跨版本结论至少覆盖区间两端。
- 布局类结论同样按版本矩阵测（逐版本 dist UMD 跑 `parse`+`render`，量 `viewBox` 与节点坐标）：
  子图排布在 11.13.0–11.15.0 与 11.17.2 一致，11.16.1 不同（该版回归，11.17.0 已回滚）；
  12.0.0/12.2.0 默认 ELK 与 11.x 不同，显式 `layout: 'dagre'` 即复现 11.x 排布（本次已实跑）。
- mmdc 对同一块复现失败（非零退出）→修复后成功（零退出），PNG 目视确认。
- 本机无 mmdc 时，`pnpm dlx` 配 Chrome 可渲染出 SVG（EXIT=0）；`pnpm exec` 在无本地依赖时报 `Command "mmdc" not found`（两者本次已实跑）。
- `render_mmd.py`：好块 `RENDER=OK`（Windows 用 Chrome、Playwright 自带 Chromium 均通过）；坏块渲染 `RENDER=FAILED` 退出 4、`-c` 退出 2；
  预检脚本抛异常时只告警并继续渲染（退出 0）；无渲染器退出 3、无浏览器退出 5，失败分支在 stderr 追加 `NEXT:` 补救命令；
  Linux（WSL Ubuntu 24，Python 3.12）跑通 `--help`、预检、无渲染器与无浏览器分支（本次已实跑，Linux 侧未做真实渲染）。
