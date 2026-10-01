# 设计令牌：唯一的视觉依据

三层结构，组件只许用语义层：

- 原始层：调色板与尺度，如`--gray-50..950`、`--blue-500: #2563eb`。禁止组件直接引用。
- 语义层：表达意图，如`--color-bg-surface`、`--color-text-danger`、`--space-inset-md`。主题切换只改这一层。`:root`声明`color-scheme: light dark`，配`<meta name="theme-color">`。
- 组件层（小项目可省）：如`--button-bg: var(--color-primary)`。

DTCG JSON交换格式已到2025.10稳定版。运行时以`tokens.css`为准；只有设计工具需要时才用DTCG JSON。

## 推荐默认值（直接填进DESIGN.md）

- 间距（4px网格）：`4、8、12、16、24、32、48、64`。父子用`padding`，兄弟用`gap`。层级间距差≥1.5倍。
- 字号：`12、14、16、20、24、30、36`，全站不超过6–7档。正文中文14px/1.7、西文16px/1.5。字体栈：`system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`。需比对的数字用`font-variant-numeric: tabular-nums`。用真省略号`…`与弯引号；截断必须给`title`或tooltip。
- 圆角：`4、8、12、9999`。阴影：最多3级，颜色带背景色相，不用纯黑。
- 动效：`120ms、200ms、320ms`，缓动`cubic-bezier(0.2,0,0,1)`。
- 布局：内容≤1280px，阅读宽65–75字符/中文每行30–40字。断点`640、768、1024、1280`，移动优先，组件优先容器查询。
- 颜色：一个主色（占比≤10%）、一套中性灰9–11档（只带一种色相倾向）、四个语义色。对比度在令牌层预验。`oklch()`已广泛可用（Chrome 111+），老WebView给sRGB回退。合规看WCAG 2.x比率，APCA只作设计参考。
- 图标：全站只用一套（如lucide），尺寸16/20/24。
