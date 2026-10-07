# 三构建产物特点与对比（fable / gpt / sonnet）

> 用途：`references/builds/` 三个单文件 `index.html` 的导读地图。先看本页决定抄谁，再双击对应产物验证，最后按 `SKILL.md` 收敛口径落地。产物是只读快照（Vite 单文件内联），实现细节以 `<参考工程根>` 源码为准，路径见 `SKILL.md` 素材来源。
> 预览：对应目录 `index.html` 双击或 `file://` 离线开，无需起服务。边界声明：时序/尺寸等数值是三工程的设计选择，非 Cloudflare 官方规范（gpt `docs/05` 原话）。

## 0 快照一览

| 目录 | 工程名（产物标题） | 体积 | 快照内容 | 一句话定位 |
|---|---|---|---|---|
| `builds/fable5.1-high/` | Console UI Reference | 605 KB | 侧栏状态机最完整实现、DNS 旗舰页、命令面板、`ResponsiveLabPage` | 调侧栏/命令面板/宽度实验室看它 |
| `builds/gpt6astra-max/` | EdgeLab | 512 KB + `docs/00-05` | 规范快照随 `public/` 拷入、`acceptance` 测试对应实现、`Workbench` | 调规范文档/验收用例/导入导出原子性看它 |
| `builds/sonnet5.5xhigh/` | Nimbus Console | 524 KB | Legacy 反例页、列宽拖拽与宽度实验室、`recordModel`/`columns`/`data` | 调列宽/Undo 快照/反例对照看它 |

快照日期见 `references/builds/README.md`（三工程 `dist/` 均晚于各自 `src/`，fable 含侧栏图标居中修复）。

## 1 fable5.1-high：侧栏状态机正本 + 命令面板 + ResponsiveLab

### 外壳

- 状态机最全：`pinned(展开/折叠，`cfui.sidebar.pinned` 持久化）/ hover-peek / kbFocus-peek / forced（触屏）/ suppressed（点收起后直到离开一次）/ drawer(<768)`，`[` 切 pinned，`Ctrl/⌘+K` 开命令面板。
- 覆盖不推挤：侧栏从 `top:56` 起，peek 用 `fixed + shadow-2 + z40`，本就不与顶栏（z50）重叠，故 40<50 无妨；peek 时 main 可 `opacity:.92`。
- 时序原值：进/出意图 `110/220ms`，宽度过渡 `280ms`，文字 `opacity+visibility + 展开延迟 50-75ms/折叠立即`，不用 `display:none`。
- 像素坑已修：分隔线用 `::after` 不占盒；`expanded ? px-2 : px-0` 防 `8+10+18` 图标偏右 8px；图标盒 36/40 居中 `x=28` 两态不变；行高规则至少 `(0,2,0)` 才压得住 `.sidenav button(0,1,1)`。
- 展开 `264px` / Rail `56px` / 顶栏 `56px` / 内容 `max1440`（收敛口径定死 `240`，同项目只用一个）。

### 令牌与层级（收敛默认即此套）

- 命名 `--c-*`：`--c-bg/surface/text/border/primary(#0051c3)/orange(#f6821f)/success/warning/danger(+soft)/overlay`，深色 `--c-bg:#0f1114 + --c-primary:#6ea8ff` 独立映射；Tailwind v4 `@theme inline` 映射语义类，禁裸色。
- 层级完整套： rail 20 / peek 40 / 顶栏 50 / 抽屉 60 / Popover 70 / Tooltip 80 / Dialog 90 / Toast 100（`z-index:20…100` 产物实测齐全）。

### 表格/表单

- `table.tsx` 口径：列宽键盘 `16/64`（sonnet 为 `8/32`，同项目二选一）；`table-fixed + colgroup + 每列 min/max + 填充列吸余`；末列 `sticky right0 + 行实色 + scroll+RO>1 才显阴影`；首列复选含 `indeterminate + Shift 连选`。
- 行内展开与弹窗共用 `RecordEditor + validateRecord`；批量条 `fixed bottom16 max520 深色 + 8s Undo`；持久化前缀 `cfui.dns.cols/widths/density/edit/records`。
- 表单两级校验 + 首错 `focus + scrollIntoView` + 保留输入；`dirty JSON + 站内守卫 + beforeunload`，删除清脏；`Stepper` 向导 + Review 回改；`danger` 相关 100+ 处，危险区独立。

### 验收工具

- `ResponsiveLabPage`：滑条 `280-1600 + 预设 320/390/768/1024/1440 + Auto 扫描（0.5/1/2x，Space 暂停）+ side-by-side`；`?frame=1` 同产物加载，拿到真实媒体查询而非缩放模拟。
- 命令面板：`role=combobox + aria-activedescendant`，上下导航、回车打开、Esc 关，导航项 + 业务对象按分组显示，底部快捷键说明。

## 2 gpt6astra-max：规范文档 + Workbench + 原子导入导出

### 文档与测试（仅此家随产物带文档）

- `docs/00-05`：design-plan / guidelines（MUST/SHOULD/MAY/NEVER 四级强度）/ interaction-spec / development / acceptance / reference，构建时随 `public/docs` 拷入 `dist/docs`，产物内可直接读。
- `tests/acceptance.spec.ts` 对应实现；`docs/04` 明示“构建成功≠视觉/无障碍验收”，未执行的检查标 `未执行` 而非默认通过；交付带 `版本/浏览器/视口/主题/用例/截图 trace` 报告模板。
- `Workbench`：宽度往返回放、`80ms` 步进（`document.hidden` 暂停）、模拟失败开关测表单错误态、hover 延迟等参数可调；`?preview=1` 独立按 `1440/768/390/300` 测视口。

### 外壳（双导航是其特征）

- 工作台导航 `224/64` + 站点导航 `224/56` 两套并存；断点 `工作台≤1000 转移动入口 / 站点画布<961 固定也覆盖 / ≤640 图标栏转顶抽屉`（`docs/02` 的 961 与 `docs/05` 的 960 互斥、实现里无 961，一律以实现 + SKILL 收敛断点 `768/1024` 为准）。
- 时序 `120/240 + 宽度 220ms`；层级按需套（产物实测 `20/35/50/70/500/1000`），与 fable/sonnet 都不同，同项目定死一套。
- 约束写得最细：固定按钮本身不触发焦点展开（防“点收起因聚焦又弹开”）；快速进出先清旧计时器 + 卸载清理；触屏不依赖 hover；焦点在导航内时移开不强藏。

### 令牌（命名与其他两家不同，复用需映射）

- `--canvas/subtle/hover/text/muted/border/brand(#f07832)/brand-ink(#b94f16)/brand-wash/action(#2563eb)/success-wash/danger-wash`，品牌橙偏 `#f07832`（另两家 `#f6821f`），操作蓝 `#2563eb`（另两家 `#0051c3` 系）。
- 字号档 `12/13/14/18/22/28/32`（收敛 `11/12/13/14/16/20/28`），圆角 `4/6/8/12` 与收敛一致。

### 表格/表单（无列宽拖拽是有意取舍）

- 搜索 `useDeferredValue + memo` 解耦；Filters 草稿/应用分离（最多 4 条件 AND，Apply/Enter 生效，关浮层不应用）；排序 `aria-sort`；全选仅本页；搜筛量变回页 1 并清空选择。
- 导入导出原子性标杆：JSON 先整体校验（必填 `type/name/content`、1MB 上限、总数上限 200、重复检查），任一失败整个拒绝零部分写入；导入生成本地新 ID；导出选中导所选、未选导全部，Blob 下载后释放 URL。
- 窄屏 `≤640` 三行重排（类型/名称 + 内容 + 代理/TTL），排序/全选移入显示设置，焦点移交搜索框；`≤640` 用 `@container` + `container-type` 真实重排而非缩放。
- 表单：`RecordForm` 同一套校验；`edgelab.draft` 只持久新增、编辑仅实例内；`550ms` 模拟异步 + `saving` 防重；表单实验页带“模拟保存失败”开关；删除二次确认默认焦“保留记录”，无 Undo（靠重置演示恢复 6 条初始记录）。

### 边界声明（引用时抄这段）

- `docs/05`：截图只用于理解交互布局；参考 Project A11Y（标签/校验/语义表/非色传达）、CF Dark Mode（语义映射/跟随系统/非纯黑/逐态检查）、WCAG 2.2 + APG；全部颜色/字号/时序是 EdgeLab 独立决策，不代表 CF 官方。

## 3 sonnet5.5xhigh：Legacy 反例 + 列宽 + Undo 快照

### 反例与列宽（仅此家）

- `Legacy.tsx` 刻意反例即 `references/anti-patterns.md` 四缺陷实物：固定 `220px` 无抽屉 / 表格强制 `900px` 页面横滚 / 无 label + 置灰提交 + 顶部笼统错 + 无焦点 / 成功只有顶部 `Saved.`。评审先跑此页。
- `ui/columns.tsx` 口径：`8px 热区 / 1px 线 / hover 3px 主色 + role=separator + ←→8 / Shift32 / Home 还原 / 双击还原`；拖时只写 DOM（`<col>/table style`），松手才 setState + localStorage；隔条止冒泡防误排序。
- `data.tsx` Undo 快照是真 Undo 的判定标准：`bulkUpdate` 先筛 `prev` 再改并返回更新前记录，`restoreSnapshots` 按 id 回写；删除 `removeRecords` 返回 `{rec,index}`，`restoreRecords` 按 index 排序 splice 归位。无快照返回值的“可撤销”皆假。

### 外壳（通高侧栏，故层级与 fable 相反）

- 侧栏通高，槽 `40 > 顶栏 20` 才盖得住（fable 从 `top:56` 起则 `40<50` 亦可，按所选套定死）。
- `240/56`，进/出 `120/250ms + 宽度 220ms`；简化层级：粘性操作 15 / 顶栏 20 / Popover 30 / 槽 40 / Tip 70 / Toast 80 / 跳链 100，模态走原生 dialog 顶层。
- 覆盖零位移实证最多：图标列 x 与行高两态恒定（叶子 `min-height` 如 52px，分组缩进只作用文字列）；全文本 `nowrap+overflow:hidden`（空提示换行曾差 99px）；`aside.fixed` 后 `page` 锁 `grid-column:2`（否则内容掉进第一轨宽被压 52px）；收起键 Rail 下常驻；显形规则 `0,4,0` 高于隐藏 `0,3,0`；探针：peek 前后逐行 `offsetTop` 全等 + 内容 left 不变 + 点击落点仍是按钮。

### 令牌与表格

- 命名 `--bg/surface/canvas/border/text/primary(#0051c3)/link/danger/warn/ok/brand(#f6821f)/focus/scrim`；深色 `--bg:#141414 + --primary:#2f6fe0 + --link:#7fb0ff`（主蓝偏深，靠 link 提亮，复用时按 `tokens.md` 提亮到 `#6ea8ff~#7fb0ff` 保白字对比）。
- 圆角变体 `4/8/12/full`（fable `4/6/8/12`，二选一）；切卡阈值 `<700`（另两家 `<640`，统一用 `<640`）；`nimbus.dns.cols/edit + nimbus.sidebar/theme` 持久化；`AddSite` 三步向导 + 最后 Review（`dl + Change` 链）+ 输入不丢 + 离开保护；设置 `896` 分栏，一卡一决策。

## 4 横向对比（分歧即各工程的真实选择，同项目只用一列）

| 项 | fable5.1-high | gpt6astra-max | sonnet5.5xhigh | 本 skill 收敛 |
|---|---|---|---|---|
| 展开 / Rail | 264 / 56 | 224 / 64（工作台）+ 224 / 56（站点） | 240 / 56 | 240，定死一个 |
| peek 进/出 | 110 / 220ms | 120 / 240ms | 120 / 250ms | 120 / 220ms |
| 宽度过渡 | 280ms | 220ms | 220ms | 240ms |
| 列宽拖拽 | 有，键盘 16/64 | 无（有意不做） | 有，键盘 8/32 + Home/双击还原 | 8/32（sonnet 口径） |
| 切卡阈值 | 容器 <640 | ≤640（`@container`） | <700 | 容器 <640 |
| z-index | 完整套 20/40/50/60/70/80/90/100 | 按需 20/35/50/70/500/1000 | 简化套 15/20/30/40/70/80/100 | fable 完整套 |
| 圆角 | 4/6/8/12 | 4/6/8/12 | 4/8/12/full | 二选一 |
| 外壳断点 | <768 抽屉 / 768–1023 Rail / ≥1024 固定 | 工作台 ≤1000 / 站点 960（docs 与实现互斥，以实现为准） | 同左 | <768 抽屉 / 768–1023 Rail / ≥1024 固定 |
| 抽屉宽度 | min(264,85vw) | 280~300 | min(288,100vw-48) | min(288,100vw-48)，原生 dialog |
| 令牌命名 | `--c-*`（收敛同名） | `--canvas/brand/action-*`（需映射） | `--bg/primary/link-*`（深主蓝偏深） | `--c-*` + 深提亮 `#6ea8ff~#7fb0ff` |
| 持久化前缀 | `cfui.*` | `edgelab.*` | `nimbus.*` | 按项目定一个前缀 |
| 删除撤销 | Undo（8s） | 二次确认，无 Undo（重置演示恢复） | Undo 快照（prev/index 归位） | Undo 优于强确认 |
| 验收工具 | ResponsiveLab + `?frame=1` | Workbench + `?preview=1` + Playwright 用例 | 宽度实验室 + Legacy 对照 | 交付内置宽度滑条页 |
| 独有资产 | 命令面板 `combobox` 分组 | `docs/00-05` + 导入原子性 + 双导航断点 | Legacy 反例 + `recordModel` + 快照实现 | 按需各取 |

## 5 复用路线（看什么抄什么）

- 新建先定收敛值（上表右列），再谈视觉；令牌先行，组件只用语义类，禁裸色。
- 调侧栏：看 fable 状态机公式 + 零位移探针（sonnet 实证节），时序用收敛 `120/220 + 240ms`，层级按侧栏起点选一套定死（`top:56` 起用 fable 套，通高用 sonnet 套）。
- 调表格：列宽与 Undo 抄 sonnet（`columns.tsx + data.tsx` 快照），导入导出原子性抄 gpt（`docs/02 §7`），骨架 9 层三家一致。
- 调表单：两级校验 + 首焦 + 留输抄任意一家（同一 `validateRecord`），草稿键按项目前缀重命名；危险区隔离 + 输名确认看 sonnet/fable。
- 评审他人：先跑 `anti-patterns.md` 四缺陷（实物在 sonnet Legacy 页），再按 `SKILL.md` 自检九项打勾；截图先全景后特写，浮层用视口截图。
- 验收：`390/768/1440 + 320/300` 跑 `scrollWidth<=innerWidth`；peek 前后内容 left 不变；主题三态 + `reduced-motion` 各一次；200%/400% 缩放回流；纯键盘走完增改删撤销。

## 6 维护

- 刷新：源工程 `npx vite build` 后新 `dist/*` 覆盖对应目录，并更新 `references/builds/README.md` 快照日期。
- 本页只增不改口径：收敛值变更必须同步改 `SKILL.md` 收敛表 + 对应 `references/*.md`，不许只改本页。
