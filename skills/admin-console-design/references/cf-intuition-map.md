# Cloudflare 直觉映射表（cf-intuition-map）

> 用途：Cloudflare 老用户零学习上手新控制台的对齐清单。一行一条：左列是用户在 CF 里的既有直觉，中列是本 skill 的对应实现，右列是落地位置。Agent 还原 UI 时按表逐项对，缺一项即直觉断层。
> 边界声明：本表映射的是三参考工程沉淀的交互语义（见 `builds-comparison.md`），时序/尺寸数值以 `SKILL.md` 收敛口径为准，不直接复用产物数值；均为独立设计决策，不代表 Cloudflare 官方规范。
> 动手前：先双击 `references/builds/` 对应产物亲手点一遍（折叠/悬停/抽屉/命令面板/窄屏），再看表。

## 1 导航心智（"我在哪，我在管哪个站"）

| CF 用户直觉 | 本 skill 对应实现 | 落点 |
|---|---|---|
| 左侧栏平时只占一条图标带，鼠标划过整栏浮出来，看完移开自动收回，页面内容不抖 | pinned/rail/peek 三态，peek 覆盖不推挤（槽与视觉宽度解耦），意图延迟进/出，键盘 Tab 聚焦同样 peek，触屏给明确点开按钮 | `references/shell-sidebar.md`；产物：`builds/fable5.1-high`（状态机正本） |
| 顶栏永远告诉我当前是哪个站，点一下就能换 | 资源切换器：星标收藏 + 域名 truncate + 套餐 Badge，下拉搜索切换；上下文常驻，切模块不丢失 | `SKILL.md` 步骤1 顶栏节；产物：三家顶栏任选其一亲手点 |
| 任何地方 `⌘K`/`Ctrl+K` 都能跳 | 命令面板：combobox 语义，分组（页面/业务对象），上下导航回车打开，底部快捷键说明 | `references/shell-sidebar.md`；产物：`builds/fable5.1-high` |
| 收起按钮按一次就收，不会刚收又弹出来 | suppressed 语义：点收起后直到鼠标离开一次，不再 peek；`[` 快捷键同样可切 | `references/shell-sidebar.md` |
| 窄屏下导航变成从左边滑出的抽屉 | <768px 汉堡→抽屉（原生 dialog，Esc/遮罩/导航项关闭+焦点移入） | `references/responsive-a11y.md` |

**零偏差自测**：合上眼，鼠标划到左边缘能浮出导航、移开自动收回且页面没动过；`⌘K` 输入站名能跳。否则导航心智未还原。

## 2 表格心智（以 DNS 记录表为基准形态）

| CF 用户直觉 | 本 skill 对应实现 | 落点 |
|---|---|---|
| 顶部永远是"搜索框最大、Add 按钮最右" | 工具栏：搜索 flex-1 max520 + Filters + Display + Import/Export + Add primary 最右 | `references/tables.md` |
| 筛选条件可以慢慢配，配完点一下才生效，配错了能逐个删 | Filters 草稿/应用分离（Apply/Enter 生效）+ chips 逐删 + 计数徽标 | `references/tables.md`；产物：三家 Filters 浮层任点其一 |
| 列宽不够就拖一下，下次来还在 | 列宽拖拽（8px 热区 + 键盘←→/Shift + 双击/一键还原）+ localStorage 持久化；固定列禁调 | `references/tables.md`（sonnet 口径，见收敛口径表） |
| 横向滚表时勾选框和操作列一直看得见 | 首列勾选 + 末列操作双粘性（行实色不透明），滚到边才现阴影提示还有内容 | `references/tables.md` |
| 点 Edit 就在行里改，不想分心就弹大框改，两边行为一样 | 行内展开与弹窗共用同一表单同一校验；开后焦点进首字段，关后回 Edit | `references/tables.md` |
| 选多了底部浮出一条深色操作条，删错了能 Undo | 浮动批量条（fixed bottom，不插表格上方防错位）+ 删除 Undo 8s 优于强确认 | `references/tables.md`（Undo 快照判定见 `builds-comparison.md` §3） |
| 手机上表变成一张张卡片，按钮照样能点 | 容器 <640 切卡片（三行式，thead 保语义视觉隐藏），表卡只渲染其一 | `references/tables.md` |

**零偏差自测**：不看文档，能说出"筛选配完要点 Apply、列宽拖完下次还在、删错了有 Undo"。否则表格心智未还原。

## 3 表单心智（设置页与长表单）

| CF 用户直觉 | 本 skill 对应实现 | 落点 |
|---|---|---|
| 每个设置都是一张卡：左边讲清楚，右边是开关 | 一卡一决策：左说明右控件；脏时才出现底部操作条（左状态右 Save） | `references/forms.md` |
| 保存按钮永远能点，错了它会告诉我缺什么并带我过去 | 保存不置灰：可点提交→顶部汇总（数量+可点击跳转）→首错聚焦→保留已填 | `references/forms.md` |
| 填到一半走了，回来还在 | 草稿持久化（新增）+ 脏保护（站内守卫 + beforeunload）+ 删除清脏防幽灵拦截 | `references/forms.md` |
| 最危险的东西在最底下红色框里，删库要我手输名字 | 危险区垫底独立红描边远离首屏；高风险输名确认但按钮保持可点（以校验说话）；删除默认聚焦安全选项 | `references/forms.md` |
| 向导可以回退，最后有张总表让我检查再提交 | 线性 Stepper + Back 不丢数据 + 换步焦点到标题 + 最后 Review 汇总回改 | `references/forms.md` |

**零偏差自测**：空表单直接点保存，能被带到第一个错处且已填的不丢；危险按钮不在首屏。否则表单心智未还原。

## 4 反馈心智（操作之后世界如何回应）

| CF 用户直觉 | 本 skill 对应实现 | 落点 |
|---|---|---|
| 小事右下角冒个条，大事弹窗跟我确认 | toast（成功 5s/撤销 8s，右下 live polite）vs Dialog（危险/复杂确认）；Alert 留给页内重要状态 | `references/tables.md`、`references/forms.md` 相关节 |
| 空页面不说空话，告诉我下一步干嘛 | 空态分零数据/零匹配，各配恢复动作（Add / Clear） | `references/tables.md` |
| 按钮点了就变忙，不会让我连点三下提三次 | 忙态三件套：禁用态 + 文案/spinner 切换 + 不可重入；`aria-busy` 同步读屏 | `references/forms.md`；验收见 ai-verified-delivery 过渡与忙态条目 |

**零偏差自测**：断网点保存，看得到明确失败归宿而不是静默转圈；连点提交只发出一次。否则反馈心智未还原。

## 5 视觉直觉（第一眼像 CF）

| CF 用户直觉 | 本 skill 对应实现 | 落点 |
|---|---|---|
| 蓝是操作、橙只出现在 logo 和导航强调 | 语义令牌：操作蓝主按钮，品牌橙≤5%仅标识；组件禁裸色，只用变量 | `references/tokens.md`；数值按收敛口径 |
| 深色模式是另一套灰，不是反色 | 深色独立映射（非纯黑底+提亮主色保白字对比）+ 首屏防闪 + system 跟随 | `references/tokens.md` |
| 所有浮层该谁压谁心里有数 | fable 完整 z 套（Dialog 90 / Toast 100），同项目只用一套 | `references/tokens.md` |

## 6 使用顺序

1. 先看 `builds-comparison.md` §4 定参考来源（默认 fable 整体，列宽/Undo 看 sonnet，导入原子性看 gpt）。
2. 双击 `references/builds/` 产物，亲手点出本表左列的每个直觉（折叠/悬停/抽屉/命令面板/窄屏/批量 Undo）。
3. 按本表右列读 references 细节，数值一律用 `SKILL.md` 收敛口径，不抄产物原值。
4. 功能差异走 `cf-customization-guide.md`（只改功能定义与接线，不动直觉层）。
