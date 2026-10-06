# 极窄容器适配（≤320px 直至设计下限）

> 何时读：卡片/模块进 320 以下容器、侧栏窄态、弹窗窄复用，或验收要覆盖 `<320` 极限时。A/B 叠加态的深化，不是新轨道。
> 来源：`自适应-响应式设计/极窄自适应/` 五项目实证——
> `responsive-card-layout-optimization-opus5.5max`（docs 01–06 + `robust-card.css` + `RobustProjectCard.tsx` + `MenuButton.tsx` + `lib/audit.ts` + `lib/text.tsx`，五级阶梯/P0–P3/零 Observer 收纳/诊断探针）；
> `responsive-card-layout-optimization-qwen3.8-27b`（`ProjectCard.tsx` 朴素/健壮对照 + `index.css` cqi 流体 + `useOverflowMonitor.ts` + `Docs.tsx` 蓝图条款）；
> `designing-resilient-card-layouts-gpt6luna-max`（adaptive/fixed 对照 + 溢出读数）、`designing-resilient-card-layouts-kimi-k3`（RFC 分级 + WidthLab + 内容样本切换）、`responsive-card-layout-optimization-grok4.6-high`（六失效分类 + 全树扫描 + 媒体井规范）。

## 1 范围与分界

- 极窄 = 容器内容宽约 104–320px（含 200px 侧栏、240–280 极限复用）。目标与通用响应式一致：零页面横滚、P0 可达、截断可恢复。
- 分界（qwen 与 opus 互补的两极，写方案时先选边）：
  - 纯展示卡（无操作）：用 qwen 降级——全保留，换行/截断/降列，不删块（与本 skill AVOID“窄屏 display:none 删内容”一致）。
  - 带操作卡（信息+状态+操作复合）：用 opus 收纳——操作可进菜单、标签可按档 `+N`、非 P0 可隐藏，进菜单即“可达”（一次到达），不是删内容。

## 2 优先级 P0–P3 + 元素×层级矩阵

- P0 必须可见或可达（≤4 项；“可达” = 进菜单一次到达）；P1 尽量可见（缩写/收纳）；P2 按需展示（截断/隐藏）；P3 可舍弃。
- 落方案前先填矩阵（行 = 标题/状态/徽标/描述/缩略图/标签/操作，列 = 下面第 3 节档位，格 = 显示/缩写/截断+恢复方式/收纳/隐藏）。频率相近不硬点主操作（见 `patterns.md`）。
- 组件规范建议 12 字段：设计下限、阈值表、P0–P3 定义、矩阵、截断恢复出口、菜单内容与顺序、极值样本、已知限制。

## 3 五级 em 阶梯 + 设计下限（阈值一律实测，不抄数）

下表是 opus 验证过的起点，照抄前必须按第 4 节方法重测：

| 档位 | 容器宽（em，相对查询容器字号） | 16px 时 | 形态示例 |
|---|---|---|---|
| Micro | `<12.5em` | <200px | 纵向堆叠，只留 P0；media/desc/meta/tags/foot 可默认隐藏 |
| XS | 12.5–16.25em | 200–259px | +横幅缩略图，短文案 |
| S | 16.25–22.5em | 260–359px | 标题与操作同行，描述 3 行，主操作文字+次操作图标，标签前 2 |
| M | 22.5–35em | 360–559px | 完整纵向，标签前 3 |
| L | `≥35em` | ≥560px | 横排缩略图约 40%，标签前 6 |

- 设计下限 floor 公式：`floor = 2×触控目标 + 间距 + 2×最小内边距`，示例 `6.5em ≈ 104px@16px`（2×44 + 4 + 2×6）。低于 floor 不再压缩，保证可点。
- em 而不用 px：em 相对查询容器字号，200% 字号自动提前进紧凑档；配合 `clamp()` 必须含 rem 项（见 `fluid-grid-media.md` 三红线）。
- 移动优先：基础即 Micro（默认隐藏低档元素），`@container pc (width>=…)` 逐级增强；`@supports not (container-type: inline-size)` 停留 Micro 安全布局。

```css
/* 容器不能查自身：外包裹一层当容器，卡片为后代 */
.pc-cq { container: pc / inline-size; min-width: 0; }
@container pc (width >= 12.5em) { .pc__media { display: block; } }
@container pc (width >= 16.25em) { .pc__foot { display: flex; } }
@container pc (width >= 35em) { .pc { display: grid; grid-template-columns: minmax(0,2fr) minmax(0,3fr); } }
```

## 4 阈值确定四步 + 固定退让六序

- 阈值确定：① 最宽→窄拖，记“变难看”宽度 W，阈值 = W + 8–16px 余量 → 换算 em；② 阈值 ±1px 双侧成立；③ 最长语言（德语/伪本地化 ~40% 扩展）复核；④ 200% 字号复核。阈值为内容服务，不对齐 375/390/768。
- 退让顺序（固定，不跳步）：换行 → 缩写（语义无损、实测后才用）→ 截断（必须可恢复，见 5 节）→ 收纳进菜单 → 隐藏（仅非 P0）→ 到下限。缩字号、允许溢出不在流程内。
- 间距预算：嵌套 padding 叠加量化，内容占比目标 ≥70%（固定内边距在 320 下内容仅剩约 61%，200 侧栏仅剩约 37%）；流体间距 `--pad: clamp(6px, 5cqi, 16px)`，cqi 相对其父容器；呼吸式内边距示例 `padding: clamp(12px, 4.5cqw, 20px)`。

## 5 断行与截断配方（按类型分流）

- 兜底四件套（先做）：文本 flex 子 `min-width: 0`；Grid 轨道 `minmax(0,1fr)`（注意 `1fr = minmax(auto,1fr)`，文本子项不用裸 `1fr`）；长串 `overflow-wrap: anywhere`；交互元素 `flex: none` 锁触控盒。
- `anywhere` vs `break-word`：只有 `anywhere` 参与最小内容计算，`break-word` 不参与故不推荐作兜底。
- 语义断点（不改数据、复制/读屏不变，`Array.from` 保 emoji）：分隔符 `[-_./\\@:?=&#+]` 之后、lower→Upper、letter↔digit 边界插入 `<wbr/>`。
- 中间截断（保留后缀如 .pdf/数字尾）：

```css
.mt { display: inline-flex; max-width: 100%; min-width: 0; white-space: nowrap; }
.mt__head { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.mt__tail { flex: 0 0.001 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
```

- 按类型分流：名称换行 + 可复制全文/展开；摘要 `line-clamp: 3`（+ `overflow: hidden`，`text-wrap: pretty` 优化尾行）；机器串 `nowrap + ellipsis + title/复制按钮`；胶囊永单行（`white-space: nowrap; max-width: 100%`，内部 span ellipsis）。
- `line-clamp` 内焦点：`overflow: hidden` 会裁外描边，改透明 outline + 背景 + 下划线替代。
- 徽标三阶：长文案 ↔ 短文案（容器查询切换）→ 仅图标 + 文字 `sr-only`（保无障碍名）。
- 预览媒体井：`width: 100%; max-width: 320px; min-width: 0; aspect-ratio: 16/10`；禁卡片套卡片（多层边框/阴影吃掉 16–24px）；缩略图网格 `repeat(4, minmax(0,1fr))`，单阈值档示例 `@container (max-width: 352px)` 降为 2 列（设计档位，重测后用）。
- 流体字号（组件跟容器不跟视口，先写固定回退）：`font-size: 15.5px; font-size: clamp(13px, 3.2cqi + 6.5px, 15.5px);`

## 6 操作收纳二选一（零 Observer vs 动态 Priority+）

| 条件 | 选型 |
|---|---|
| 动作 ≤4 且优先级稳定 | 零 Observer 收纳：CSS 静态隐藏 + 打开瞬间读真实布局（单源真相，无阈值打架） |
| 动作多 / 文案易变（国际化/切换文案） | 动态 Priority+（见 `js-apis.md`）：隐藏测量行 + 判据 `W >= sum(B_i)+(N-1)*G` 算 k |

```tsx
// 零 Observer：items 传函数，打开瞬间才求值
const menuItems = () => {
  const hidden = !footRef.current || getComputedStyle(footRef.current).display === "none";
  return [...(hidden ? [open, logs, rebuild] : []), copyLink];
};
<MenuButton label={`更多：${name}`} items={menuItems} />
```

- 纯 CSS 标签“前 N + 计数”：`nth-child(n+k)` 按档隐藏 + 每档独立计数 span 由容器查询选择显示。
- 菜单定位（Portal 到 body + `position: fixed`，`useLayoutEffect` 绘制前定位）：贴触发器、越界翻转、视口夹取（8px 边距）、RTL 感知；`Esc` 关并回焦点；确认框/抽屉用原生 `<dialog>`（焦点陷阱 + Esc 自带）。
- 守恒：集合守恒、菜单顺序稳定、DOM 顺序不变（`order` 只调视觉）、状态保留。

## 7 嵌套（二级）容器

卡片容器 `pc` 内缩略图再建二级容器 `pv`，按自身宽二次查询（如 `<15em` 2 列、`<10em` 藏 tiles/dots），卡片层再控缩略图形态。命名容器并带名查询，避免命中错层；二级阈值与父档协同写进矩阵。

## 8 探针（debug 专用，上线关）

- 溢出：边框盒越过最近 `[data-qa=card/panel]` 内联边界 >1px，只计最外层；子元素取“自身 + 直接子元素最右边缘 − 卡片右边界”，`>0.75px` 记 offender（截断/省略号收缩盒子不误报）；`data-qa-ignore` 排除浮层，SVG 子元素跳过。
- 挤压三探针：`[data-qa-min]` 渲染宽 < 设计值；`[data-qa=text]` 列宽 < 3.5×字号且文本 ≥4 字；`[data-qa=pill]` 高 > 1.7×行高 + 6px。
- 节流：120ms 间隔 + rAF 同帧读 + rect 缓存 + `sameResult` 去重；`document.fonts.ready` 后复检。
- 页面级防护网确需兜底用 `overflow: clip + overflow-clip-margin: 0`（不建滚动容器，sticky 不失效）；`hidden` 掩盖判失败。
- 采样：下限 104/105/120、阈值 ±1、典型窄 160/240/280/320；示例宽度表 `[104,120,160,199,200,240,259,260,320,359,360,559,560,768] × 字号[1,2] × 德语`；极值样本 D-01~D-14（连字符串/驼峰/下划线/长中文/德语复合词/极短名/长 URL/变音人名/长分支/超大数字/多标签/缺图/伪本地化 40% 扩展/emoji 字素簇）；`scrollWidth ≤ clientWidth + 1`。
- 定级（验收报告用）：S1 页面级溢出/操作不可达，S2 挤压变形/截断不可恢复，S3 阈值带内抖动，S4 视觉瑕疵不影响任务；任一 S1/S2 阻断交付。

## 9 演示台脚手架（复现与教学）

- 定宽 wrapper（`width: simWidth`，滑杆 120–1200，预设 150/230/310/440/620）+ `transition-[width]` + 外层 `overflow: hidden` + 标尺 + 粘性状态条 + 实时溢出读数（`Npx 溢出`）+ 朴素/稳健双泳道一键切换（fixed 反例保留缺陷用于教学）+ 内容样本切换（常规/无空格机器串/全 CJK；常规连字符会“放水”需明示）+ ≥768 双列复现分蛋糕。
- 全树扫描进阶：递归查整棵子树 `scrollWidth > clientWidth + 1`，加红斜纹并计数，脆弱/弹性双计数对比。
- 六失效分类速查：溢出/挤压/碰撞/触控失效/预览变形/静默截断，各记信号-成因-修法；禁 `transform: scale()` 假适配。
