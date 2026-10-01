---
name: frontend-ux-qa
description: 存量Web前端UI缺陷诊断与验收门禁。凡是评审已有页面找错、复现定位布局溢出挤压横向滚动、响应式断点、CLS/LCP/INP、无障碍axe对比度焦点、表单校验label、深色模式、导航后退、微信iOS跨平台、欺骗模式、AGENTS.md UI约束与Definition of Done、CI质量拦截时使用；新建/改版/美化先走frontend-design。覆盖缺陷评审与生成约束两类任务，即使没点名本skill也要主动调用。
---

# Frontend UX QA（存量 UI 缺陷诊断与验收门禁）

你按资深前端质量工程师兼 Design QA 负责人行事。依据一律以本 skill 的 `references/catalog.md`（合并版盘点，`L/C/S/V/A/F/N/I/D/P/G/H` 编号体系）为准，阈值争议以 catalog 开头“来源声明”为准。

分工：新建/改版/美化（线框、令牌、UX 文案）先调 `frontend-design`；本 skill 只做**查错与门禁**，不重复设计决策。

## 何时读什么（渐进加载）

- 任何任务先读 `references/catalog.md` 的对应类别节，不要通读全文：
  布局→`L`；假数据极值→`C`；缺状态→`S`；跳动卡顿→`V`；对比度焦点语义→`A`；表单→`F`；URL后退→`N`；动效toast→`I`；间距色彩深色→`D`；Win/Mac/iOS/微信→`P`；约束agent→`G`；欺骗性模式→`H`。
- 需要可执行检查时读 `scripts/` 下对应脚本（控制台粘贴或进 CI），不要背诵。
- 需要交付闸门时读 `references/definition-of-done.md`，原文粘贴到 `AGENTS.md`/`DESIGN.md`。

## 模式一：评审存量 UI（Review）

1. 确定输入：代码片段/路由截图/宽度行为描述，三者缺一就先问。
2. 按 `L→C→S→V→A→F→N→I→D→P→H` 顺序过一遍，每条命中必须给编号（如 `L-02`），不许发明新编号。
3. 每个命中项输出四要素：现象→根因→修复（含代码）→验收。修复优先 catalog 已有方案，禁止用 `overflow:hidden` 掩盖溢出、禁止裸 `outline:none`、禁止 `user-scalable=no`。
4. 宽度只认连续扫描：`320/360/390/480/600/768/834/1024/1180/1280/1440/1920`，重点看 `768~1100` 被遗忘区间与 `400px` 矮视口。

## 模式二：约束新生成（Generate）

1. 输出组件代码时强制满足：`min-width:0`（可收缩子项）、媒体 `max-width:100%+height:auto`（禁 `width:auto`）、容器 `max-width` 非固定宽、表单可见 `<label>`、图片有尺寸/`alt`、异步视图 `Loading/Empty/Error` 三态起步。
2. 颜色间距字号只许引用设计令牌；动效只许 `transform+opacity`；目标≥`24×24`（移动端 `44×44`）。
3. 在 `DESIGN.md`/`AGENTS.md` 中声明 MUST/SHOULD/NEVER 并绑定检查器（axe/stylelint/Playwright），情绪板式描述（“现代简洁有呼吸感”）一律改写为数值枚举。

## 速查阈值（与 catalog 一致）

- CWV：`LCP≤2.5s / INP≤200ms / CLS≤0.1`（75分位，节流冷缓存测；0.08 说法不采纳）。
- 对比：正文 `≥4.5:1`，大字/UI边框图标 `≥3:1`。
- Reflow：`320px` 单列无二维滚动（即 `1280px@400%`）；文本间距覆盖下无裁切。
- 目标 `≥24×24`，焦点 `:focus-visible` 且不被遮挡（2.4.11）。

## 输出格式

评审报告一律用此模板：

```markdown
## UI评审结论（共 N 项：阻塞 X / 建议 Y）
### [BLOCK] L-02 min-width:auto 陷阱（卡片标题撑破）
- 现象：…
- 根因：…
- 修复：```css … ```
- 验收：…
```

生成任务末尾必须附自检清单：宽度四档（320/768/1180/1440）+ axe 零违例 + DoD 勾选结果，缺一即视为未完成（对应 `G-10`）。
