---
name: mermaid-render-fix
description: >
  诊断并修复渲染失败的 Mermaid 图：提取代码块复现 Parse error，按报错行修复后用 mmdc 或 kroki 复验。
  渲染失败、Parse error、节点含方括号导致断裂时使用；纯新建图或排版统一走 markdown-style。
---

# Mermaid 渲染失败修复

## 适用范围

输入是渲染失败的 Mermaid 代码块，产出可独立渲染的最小修改版。语法规则的维护位置在
`../markdown-style/SKILL.md` 的 Mermaid 一节，本 skill 只保留最高频根因摘要，
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
5. **复验**：重跑同一条路径，`RENDER=OK`（脚本）或 `EXIT=0` 才算通过；再目视产物确认中文与特殊符号。
6. **回写**：把验证过的块写回原位置，保持最小 diff；报告根因行、改法与两次 EXIT。

## 约束

- 复验通过前不写回原文件；非零退出码或 `RENDER=FAILED` 的输出不作为完成证据。
- 不重排图结构，不批量改文件编码；时序图分号等细节以 markdown-style 为准，不自立第二套规则。
- 预检只做启发式提示，不能替代真实渲染结论；预检自身失败（解释器过旧、脚本异常）不阻断渲染。

## 验证协议

- `check_mermaid.py` 在已知坏块上报 SUSPICIOUS、修好后报 OK（本次已实跑）。
- mmdc 对同一块复现失败（非零退出）→修复后成功（零退出），PNG 目视确认。
- 本机无 mmdc 时，`pnpm dlx` 配 Chrome 可渲染出 SVG（EXIT=0）；`pnpm exec` 在无本地依赖时报 `Command "mmdc" not found`（两者本次已实跑）。
- `render_mmd.py`：好块 `RENDER=OK`（Windows 用 Chrome、Playwright 自带 Chromium 均通过）；坏块渲染 `RENDER=FAILED` 退出 4、`-c` 退出 2；
  预检脚本抛异常时只告警并继续渲染（退出 0）；无渲染器退出 3、无浏览器退出 5；Linux（WSL Ubuntu 24，Python 3.12）跑通
  `--help`、预检、无渲染器与无浏览器分支（本次已实跑，Linux 侧未做真实渲染）。
