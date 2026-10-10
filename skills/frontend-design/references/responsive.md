## 响应式：约束识别与专项路由

> 何时读：线框阶段识别空间约束，实施与验收时按需回读。**内容决定断点，基础验证宽度不等于布局断点。**

### 职责与读取范围

`frontend-design` 决定任务、信息层级、页面结构与视觉令牌；`adaptive-responsive-guide` 维护空间变化时的重排、收纳和响应式实现。线框阶段记录窄屏/窄容器的变化，实施时只读命中场景的参考，验收归入同一交付。

| 场景 | 响应式专项参考 |
| --- | --- |
| 视口、内容断点、首屏/全屏高度、安全区、软键盘 | [响应式基础](../../adaptive-responsive-guide/references/responsive-core.md) |
| 字号与间距流体、内在 Grid/Flex、响应式图片 | [流体、网格与媒体](../../adaptive-responsive-guide/references/fluid-grid-media.md) |
| 导航/侧栏、表格、滚动归属、普通弹窗/底部面板/全屏选型 | [页面场景](../../adaptive-responsive-guide/references/page-patterns.md) |
| 操作区放不下、主操作与更多、容器阈值 | [收纳策略](../../adaptive-responsive-guide/references/patterns.md)、[容器查询](../../adaptive-responsive-guide/references/container-queries.md) |
| 收纳后焦点、菜单定位、跨断点状态 | [空间变化中的交互](../../adaptive-responsive-guide/references/interaction.md) |
| 溢出/挤压或极窄复用 | [溢出诊断](../../adaptive-responsive-guide/references/overflow-squeeze.md)，极窄时加[极窄适配](../../adaptive-responsive-guide/references/extreme-narrow.md) |
| 基础与专项验收、实际视口、截图诊断 | [验收清单](../../adaptive-responsive-guide/references/acceptance.md)、[测试与兼容](../../adaptive-responsive-guide/references/compat-testing.md) |

通用键盘、目标尺寸、对比度与回流标准由 [a11y.md](a11y.md) 维护；响应式专项只补空间变化产生的风险。动效设计与技术沿用 [motion.md](motion.md) 的职责声明。

### 线框与项目记录

- 写清窄屏和受限容器中，区域如何重排、操作如何收纳、滚动由谁承担。
- 项目 `DESIGN.md` 记录实际视口/容器阈值及内容实测依据；断点数量按需要，不强制套设备三段。
- 滚动与浮层按上述页面场景选择；表格的列显隐、卡片化或局部滚动应保住当前任务，操作收纳不删除功能。
- 页眉与次级固定栏的主次在线框中确定，不让固定区域遮住内容与焦点；定位实现按需使用 `sticky-position`。

专项 skill 未安装时，保留最小可用方案：页面窄屏单列、模块自然换行，按钮完整或收进可发现的菜单，正文可断行，媒体受容器约束；用通用无障碍基线检查回流、缩放和键盘，不凭设备名推定断点或采用未经验证的复杂收纳。

### 验收与截图助手

验收范围由上述 `acceptance.md` 维护：基础点检加本次变更适用的容器、阈值或极窄检查，不重复生成两份报告。记录实际视口/容器宽、检查状态和未执行项。

`node scripts/screenshot.mjs <本地地址> --out <截图目录>` 产出基础宽度截图；可用 `--widths <逗号分隔的CSS像素宽度>` 追加项目阈值附近的截图。脚本默认减弱动效，仅检查静态布局；容器、交互与正常动效须另验，截图后由 Agent 查看图像。独立复用组件即使页面很宽，仍须在实际窄容器里验证。

无头截图与溢出诊断细节集中在专项 `compat-testing.md`，不将全局裁切当作修复，也不以请求的截图尺寸代替实际视口证据。
