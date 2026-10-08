# 设计令牌（复制即用）

为什么先写令牌：三工程组件只用语义类（`bg-surface text-fg-2 border-line`），深浅两套变量零改动跟随。
先复用下面这组，再谈配色主张。

## 颜色（浅 / 深）

```css
:root{
  --c-bg:#f5f6f7; --c-surface:#fff; --c-surface-2:#f6f7f8; --c-surface-3:#eceef0;
  --c-text:#1d1f23; --c-text-2:#4a4f57; --c-text-3:#7b8089;
  --c-border:#dde0e4; --c-border-strong:#c3c7cd; --c-input:#8c8c8c;
  --c-primary:#0051c3; --c-primary-hover:#003f99; --c-primary-soft:#e8f0fc;
  --c-brand:#f6821f; /* 标识点缀 ≤5%，两主题同值 */
  --c-success:#1a7f37; --c-warning:#9a6700; --c-danger:#c62828;
  --c-focus:#0051c3;
}
[data-theme="dark"]{
  --c-bg:#0f1114; --c-surface:#17191d; --c-surface-2:#1e2126; --c-surface-3:#262a30;
  --c-text:#e8eaed; --c-text-2:#b4b9c1; --c-text-3:#848a94;
  --c-border:#2c3037; --c-border-strong:#3d424a; --c-input:#7d7d7d;
  --c-primary:#6ea8ff; --c-primary-hover:#8dbaff; --c-primary-soft:#16233a;
  --c-success:#4cc275; --c-warning:#e3b341; --c-danger:#ff7b72;
  --c-focus:#7fb0ff;
}
```

- 主蓝浅 `#0051c3`（白字 7.6:1），深提亮 `#6ea8ff~#7fb0ff`（保对比，非滤镜反转）。
- 状态色必配 `-soft` 浅底成对 + 图标文字（不只靠色）。
- 文字三档 + 边框两档，对比：正文 ≥4.5:1，输入边框非文字 ≥3:1，主按钮白/主 ≥7:1。

## 字体/字号/间距/圆角/阴影

- 字体：`Inter,system-ui,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Noto Sans CJK SC`；
  等宽 `ui-monospace,SFMono,Menlo,Consolas` + `tabular-nums`（技术值/TTL/数字）。
- 字号 7 档：11/12/13/14/16/20/28，行高正文 1.6 标题 1.3，中文不用斜体与两端对齐。
- 间距只用 4/8/12/16/24/32/48；圆角 4/6/8/12（fable 默认；sonnet 为 4/8/12/full，项目二选一）；图标 Lucide 16/18/20。
- 阴影 3 级：`0 1px 2px .06 / 0 4px 12px .10 / 0 12px 32px .18`（深色加深）。
- Tailwind v4 CSS-first：`@import tailwindcss` + `@custom-variant dark(&:where([data-theme=dark]))` + `@theme inline` 映射语义层，禁裸色。

## 主题/动效/层级

- 主题 `light/dark/system` + localStorage + 首屏内联脚本设 `data-theme` + `color-scheme` 跟随，防闪白。
- 动效 `120/200/280ms + cubic-bezier(.2,0,0,1)`，只过渡 transform/opacity/width/grid-rows；
  `prefers-reduced-motion` 压 0.01ms；触屏粗指针控件 44px（桌面 24/36）。
- 层级两套原值，**同项目只用一套不许混**（收敛默认 fable 完整套）：
  - fable 完整套：侧栏 rail 20 / peek 40 / 顶栏 50 / 抽屉 60 / Popover 70 / Tooltip 80 / Dialog 90 / Toast 100。
  - sonnet 简化套：粘性操作 15 / 顶栏 20 / Popover 30 / 侧边槽 40 / Tip 70 / Toast 80 / 跳链 100（模态走 dialog 顶层）。
  - peek/槽是否盖顶栏取决于侧栏起点：侧栏从 `top:56` 起（fable）本就不与顶栏重叠，40<50 无妨；
    侧栏通高（sonnet）才需槽 40 > 顶栏 20。按所选套写死，别中途换。
- 控件高 36（窄/粗 44），`--content-max:1440px --topbar-h:56px --sidebar:240px --rail:56px`。
