# 令牌、主题与层级

先映射目标项目已有语义令牌，再采用所选模板的视觉值。组件用语义色，不在迁移中同时引入三套变量。以下是可用起点，不是 Cloudflare 官方色板；[对照表](builds-comparison.md)保留各工程原值。

## 颜色必须成对

区分按钮填充、按钮文字、链接文字和弱底。不能把主蓝提亮后继续假定白字合格。

```css
:root {
  --c-bg: #f5f6f7;
  --c-surface: #ffffff;
  --c-surface-2: #f6f7f8;
  --c-text: #1d1f23;
  --c-text-2: #4a4f57;
  --c-text-3: #626872;
  --c-border: #dde0e4;
  --c-input: #8c8c8c;
  --c-primary: #0051c3;
  --c-primary-hover: #003f99;
  --c-on-primary: #ffffff;
  --c-link: #0051c3;
  --c-primary-soft: #e8f0fc;
  --c-brand: #f6821f;
  --c-success: #1a7f37;
  --c-warning: #9a6700;
  --c-danger: #c62828;
  --c-focus: #0051c3;
  color-scheme: light;
}
[data-theme="dark"] {
  --c-bg: #0f1114;
  --c-surface: #17191d;
  --c-surface-2: #1e2126;
  --c-text: #e8eaed;
  --c-text-2: #b4b9c1;
  --c-text-3: #a0a6af;
  --c-border: #2c3037;
  --c-input: #7d7d7d;
  --c-primary: #6ea8ff;
  --c-primary-hover: #8dbaff;
  --c-on-primary: #0f1114;
  --c-link: #8dbaff;
  --c-primary-soft: #16233a;
  --c-success: #4cc275;
  --c-warning: #e3b341;
  --c-danger: #ff7b72;
  --c-focus: #7fb0ff;
  color-scheme: dark;
}
.button-primary {
  background: var(--c-primary);
  color: var(--c-on-primary);
}
```

按实际背景测正文≥4.5:1、必要控件边界/图形≥3:1。装饰分隔线不等于输入边界，无需一概3:1。上例浅色辅助文字已与原fable的#7b8089区分；原值配白底约3.97:1，不用于小字正文。#6ea8ff配白字约2.41:1，配#0f1114约7.84:1；不能称提亮保白字对比。

状态色搭配图标/文字；用在填充按钮时另外配置on-success/on-danger等前景。橙默认少量品牌点缀，≤5%是样例审美建议，不是可验证的通用门槛；小字橙须另测对比。

## 尺度与主题

默认保留基底字体阶梯、间距、圆角、阴影和图标。fable为11/12/13/14/16/20/28字号、4/6/8/12圆角、4/8/12/16/24/32/48间距；作为体系起点，不阻断合理新档。

Lucide为样例默认，存量沿用既有整套图标库；同动作同语义，不强迫每个导航图标全局唯一，文字与名称同样参与区分。

采用light/dark/system时缓存的是偏好，实际主题随系统变化；首屏尽早设data-theme与color-scheme，存储失败有默认。仅提供指定单主题的任务不自动加切换器。

过渡时长沿用基底；width/grid轨道/box-shadow可能触发布局或绘制，不称只用这些就“全是合成动画”。减少动态效果关闭非必要位移和自动播放，状态仍可切换，不用0.01ms数值当唯一验收依据。

## 层级

层级按挂载位置和stacking context设计，语义变量比复制z数字重要。

- fable常用层：Rail20/peek40/顶栏50/Popover70/Tooltip80/Toast100；侧栏从顶栏下方起。Drawer/Dialog采用原生模态dialog时在top layer，不是z60/z90就决定关系。
- sonnet：表操作15/顶栏20/Popover30/侧栏槽40/Tooltip70/Toast80/跳链100；侧栏通高。
- gpt另有工作台/站点双导航，其数字不可直接加入前两套。

真正位于dialog内的提示/菜单应挂在合适模态上下文；普通DOM中的Toast100不会自动盖住top-layer dialog。验证嵌套浮层、关闭后回焦、sticky遮挡与主题状态，不能靠数字表宣称通过。
