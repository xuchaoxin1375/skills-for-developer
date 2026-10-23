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
2. **探测依赖**：先确认 mmdc、包管理器与浏览器；文档目录通常没有 `package.json`/`node_modules`，直接 `pnpm exec` 会报 `Command "mmdc" not found`。
   ```powershell
   Get-Command mmdc -ErrorAction SilentlyContinue | Select-Object Source
   Test-Path node_modules\.bin\mmdc.cmd
   pnpm bin -g; npm root -g
   ```
   浏览器写成 puppeteer 配置再传给 `-p`，如 `{"executablePath": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"}`，免下载 Chromium；Windows 常见位置还有 `%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe`。
3. **复现**（按可用性择一）：
   ```powershell
   # 仅本机有 mmdc 时；无本地依赖改用下面的 dlx/npx
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   $OutputEncoding = [System.Text.Encoding]::UTF8
   $env:PUPPETEER_SKIP_DOWNLOAD = "true"   # 已用 -p 指向本机浏览器，不下载 Chromium
   pnpm exec mmdc -p <puppeteer-config.json> -i <block.mmd> -o <block.svg> 2>&1 | Out-String
   Write-Output ("EXIT=" + $LASTEXITCODE)
   ```
   - 本机无 mmdc：把前缀换成 `pnpm dlx --allow-build=puppeteer --package @mermaid-js/mermaid-cli mmdc` 或 `npx -y -p @mermaid-js/mermaid-cli mmdc`；pnpm 10+ 默认拦截 puppeteer 构建脚本，需带 `--allow-build=puppeteer`（漏加报 `ERR_PNPM_IGNORED_BUILDS`），pnpm 9 及以下无此参数、去掉即可。单次运行不装全局；首次联网下载，先按 `network-access` 选路。
   - 渲染器不可用：用 kroki 交叉验证 `Invoke-WebRequest -Method Post -Uri https://kroki.io/mermaid/svg -ContentType text/plain -InFile block.mmd -OutFile block.svg`，非 2xx 时读响应正文的行号。
   - 高频使用再建议用户全局安装（`pnpm add -g @mermaid-js/mermaid-cli` 或 `npm i -g`），先征询不擅自改环境；并确认全局 bin 在 PATH，pnpm 报 `ERR_PNPM_GLOBAL_BIN_DIR_NOT_IN_PATH` 时先 `pnpm setup`。
4. **修**：每次只改报错行及同类行。最高频根因是节点文本里的 `[` 未加引号
   （报错常为 `got 'SQS'`），修法是给整个节点文本加双引号，
   如 `G["...[Console]::OutputEncoding..."]`。其余转义查 markdown-style 正本。
5. **复验**：用同一条渲染方式重跑，`EXIT=0` 才算通过；再出 PNG 目视确认中文与特殊符号。
6. **回写**：把验证过的块写回原位置，保持最小 diff；报告根因行、改法与两次 EXIT。

## 约束

- 复验通过前不写回原文件；`EXIT=1` 的输出不作为完成证据。
- 不重排图结构，不批量改文件编码；时序图分号等细节以 markdown-style 为准，不自立第二套规则。
- 脚本只做启发式预检，不能替代真实渲染结论。

## 验证协议

- `check_mermaid.py` 在已知坏块上报 SUSPICIOUS、修好后报 OK（本次已实跑）。
- mmdc 对同一块复现失败（非零退出）→修复后成功（零退出），PNG 目视确认。
- 本机无 mmdc 时，`pnpm dlx` 配 Chrome 可渲染出 SVG（EXIT=0）；`pnpm exec` 在无本地依赖时报 `Command "mmdc" not found`（两者本次已实跑）。
