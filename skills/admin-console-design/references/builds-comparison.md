# 三工程对照与复用决策

来源为三份独立Cloudflare-inspired设计工程。默认 **fable外壳和DNS页整体设计**，按需补sonnet列宽/本地Undo、gpt导入/验证。偏好来自其完整页面组织与交互覆盖，不意味着每个细节都已正确或是官方标准。

源码在[assets/sources](../assets/sources/README.md)，产物在[builds](builds/README.md)。原文档、源码、运行结果不一致时核对具体版本，原文档不会自动升级为当前规范。文件哈希与归档信息见[manifest](../assets/sources/manifest.json)。

## 贡献、局限与定位

| 来源 | 优先复用 | 定位（相对各源码根） | 局限 |
|---|---|---|---|
| fable5.1-high | 外壳区域/视觉、导航、DNS整体、共享编辑、命令面板、表单模式；已分离hoverPeek/focusPeek | `src/components/shell/`、`src/pages/dns/`、`src/components/ui/` | 非完整六态模型；平板仍受pinned影响；主图标、Esc回焦、分组节点与Rail点击已修复；分组改为按钮，失去原生链接能力 |
| sonnet5.5xhigh | 显式六状态、列宽精确预览/提交、滚动提示、本地撤销、Legacy对照 | `src/dashboard/Sidebar.tsx`、`src/ui/columns.tsx`、`src/dashboard/data.tsx`、`src/dashboard/Legacy.tsx` | 记录/站点为useState内存演示数据，偏好/列宽另有localStorage；非生产API；舞台控制/展示壳不是业务外壳 |
| gpt6astra-max | 导入全量预检、失败恢复、文档与Playwright验收案例、容器重排 | `src/components/DnsConsole.tsx`、`src/lib/data.ts`、`tests/acceptance.spec.ts`、`public/docs/` | 无列宽调节是取舍；工作台/站点双导航和断点不同；原交付文档明示浏览器用例未执行 |

fable命令面板或sonnet状态机可整体迁移；不要仅抄HTML类名留下依赖/状态/焦点悬空。源码的别名、路由、全局CSS、持久化键、图标与校验连同读取，再映射到目标体系。

## 参数原值（非全项目强制收敛）

| 项 | fable | sonnet | gpt |
|---|---|---|---|
| 展开/Rail | 264/56 | 240/56 | 工作台224/64、站点224/56 |
| peek进/出 | 110/220ms | 120/250ms | 120/240ms |
| 宽度过渡 | 280ms | 220ms | 220ms |
| 列宽键盘 | 16/64，Home恢复 | 8/32，Home最小、End最大、Enter恢复 | 未实现 |
| 表卡阈值 | 640 | 700 | 640容器查询 |
| 外壳 | 768显示桌面侧栏、默认偏好随1024，存储可覆盖 | 768/1024，平板强制Rail | 工作台1000附近、站点960附近；按采用组件确认 |
| 品牌/操作蓝 | #f6821f / #0051c3 | #f6821f / #0051c3，深色填充#2f6fe0 | #f07832 / #2563eb |
| 圆角 | 4/6/8/12 | 4/8/12/full | 4/6/8/12 |
| 恢复 | 本地Undo | 本地更新快照/删除索引Undo | 删除确认，无业务Undo |

同一交互只保留一套有效参数。整体使用fable可直接沿用264、110/220、280；引入sonnet列宽可以采用其8/32和完整键位，不能把Home文案从fable混过去。断点和颜色可因业务/无障碍调整并记录依据。[令牌](tokens.md)提供经过色对测量的新起点，不宣称原值全部合格。

## 当前素材状态（2026-10-08）

sonnet用户调整相对原zip只涉及 `src/showcase/Stage.tsx`：底部dock默认收起，悬停展开、移开160ms收回、点击固定与回焦；控制区覆盖而不占舞台尺寸；舞台默认宽度跟随可用宽度，用户手动调后不再自动覆盖；方案徽标与尺寸信息重新收纳。控制台Sidebar/DNS/列宽/数据层未随本次改动改变。

当前sonnet已重新构建并更新归档产物，源码包含上述变化；旧sonnet截图仍是历史状态，不能代表新舞台。fable/gpt归档产物与当前目录对应dist哈希一致。完整文件版本见manifest，读取旧图时先查[快照说明](builds/README.md)。

随后同步fable外部修复：`ShellContext.tsx`分离hoverPeek/focusPeek、增加卸载计时器清理，手动收起与Esc采用不同关闭方法；`Sidebar.tsx`固定工具区/导航/底部外边距以消除主图标8px横移；`docs/03-shell-and-sidebar.md`同步解释。已重新构建并归档上述三个文件与产物，sonnet/gpt未变。分组展开后的纵向布局变化是预期行为，不作为所有行位置不变的要求。随后用opencode/muse-spark-1.3-contributor-free修复Esc回焦与分组节点替换，并修复独立复测发现的松开时点击语义切换、hover-only Esc焦点抑制残留；新增延迟回焦计时器纳入清理。最终源码、产物、截图已一并更新。

## 已执行抽查与已知缺口

本轮使用Chromium153，在新隔离浏览器上下文运行；只证明这些输入/版本/路径，不是全面生产验收：

- 三工程DNS预览在1440/768/390/320/300的document scrollWidth等于视口宽，已生成1440/390截图并目检。未证明所有浮层、主题、缩放或隐藏裁切均合格。
- fable修复后：收起→移出→悬停，main left=56、width=1384保持不变，17个主导航图标x均保持19，无原8px横移。焦点留在Quick search时鼠标移出，等待离开延迟后仍保持peek；焦点移出则收起。手动收起后不立即重开，移出再进入和Esc后悬停恢复均通过。
- fable静态源码已分离hoverPeek/focusPeek并增加卸载计时器清理；卸载路径只做了源码核查，未运行组件卸载测试。focusPeek仍由所有focus触发，非仅键盘输入；平板偏好策略、forced临时状态与路由/布局变更时的过期计时器处置仍不能按完整六态模型推定通过。
- fable追加修复后：Esc保留可见主入口焦点，隐藏子项回到Quick search；焦点留在侧栏时抑制即时重开，离开再键盘进入可恢复。仅hover展开且焦点在main时，Esc保留外部焦点且下一次键盘进入可展开。DNS分组在Rail/peek保持同一BUTTON节点、名称有效；按住450ms期间延后展开，松开后的click仍到达DNS，从概览实际跳转到首个子页。**图标x、DOM身份、click事件和业务结果分别验证**，不能相互代替；分组展开推动后续行属于预期布局。
- 初轮Recents的click通过只是局部证据。追加修复独立复测7项侧栏检查与4条路径（Rail DNS实际导航、子项Esc/键盘重入、hover-only Esc、手机抽屉DNS导航）；不据此推定所有分组、所有输入方式与辅助技术通过。
- sonnet：Name默认200，键盘+8/+32、Home120、End720、Enter200均验证；拖动到240并刷新保持240。完整模块没有“Home还原”行为。
- sonnet新舞台：hover打开/移出关闭不改iframe bounding rect；键盘Enter打开、面板进焦、关闭回触发器已验证。悬停时鼠标移出但键盘焦点已在面板内的混合输入，以及Esc、触屏、reduced-motion未覆盖；归档不表示全部通过。
- gpt：包含合法+非法记录的导入被拒绝，刷新仍6条，无部分写入。这里只测一批非法输入，不是所有冲突/容量/真实后端事务证明。

旧文档的“读屏仍可读”“主蓝提亮保白字对比”“三个工程完整一致”“图标零位移全部实证”均不能直接采信。DOM保留不等于可访问树保留；本轮没有NVDA/VoiceOver测试。

fable修复复测另覆盖1440/1024/1023/768/767/390/320/300，DNS页面scrollWidth均等于视口；它是默认数据和页面级指标，不证明所有抽屉、主题或缩放状态通过。当前Rail/peek与DNS截图另归档为2026-10-08版本。

## 如何选择与维护

新建/改版先确定fable或用户指定整体基底，按需补模块；仅修单项则只读其来源与依赖。目标中验证采用的行为，不为每次工作全跑三个原型。

更新素材时一并归档源码、配置与产物，更新manifest；旧截图保留历史标签或重拍，不能仅覆盖index仍说所有图最新。维护的是可核对的当前解释，不是“本页只增不改”的过时规则。
