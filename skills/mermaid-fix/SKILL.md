---
name: mermaid-fix
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

1. **提块**：从文档提取 `mermaid` 块存临时 `.mmd`，禁手抄。先跑 `scripts/check_mermaid.py <文件>` 做秒级预检。
2. **复现**：用 mmdc 本地渲染拿到原始报错；本地无 mmdc 时用 kroki 在线接口交叉验证。
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   $OutputEncoding = [System.Text.Encoding]::UTF8
   npx mmdc -p <puppeteer-config.json> -i <block.mmd> -o <block.svg> 2>&1 | Out-String
   Write-Output ("EXIT=" + $LASTEXITCODE)
   ```
   `puppeteer-config.json` 指向本机浏览器可执行文件（示例：`%ProgramFiles%\Google\Chrome\Application\chrome.exe`），免下载 Chromium。
3. **修**：每次只改报错行及同类行。最高频根因是节点文本里的 `[` 未加引号
   （报错常为 `got 'SQS'`），修法是给整个节点文本加双引号，
   如 `G["...[Console]::OutputEncoding..."]`。其余转义查 markdown-style 正本。
4. **复验**：同一命令重跑，`EXIT=0` 才算通过；再出 PNG 目视确认中文与特殊符号。
5. **回写**：把验证过的块写回原位置，保持最小 diff；报告根因行、改法与两次 EXIT。

## 约束

- 复验通过前不写回原文件；`EXIT=1` 的输出不作为完成证据。
- 不重排图结构，不批量改文件编码；时序图分号等细节以 markdown-style 为准，不自立第二套规则。
- 脚本只做启发式预检，不能替代真实渲染结论。

## 验证协议

- `check_mermaid.py` 在已知坏块上报 SUSPICIOUS、修好后报 OK（本次已实跑）。
- mmdc 对同一块复现失败（非零退出）→修复后成功（零退出），PNG 目视确认。
