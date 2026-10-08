# 模板单元与依赖边界

选择整体主题或完整局部单元，用已经调整的实现保留细节。以下是归档源码的取用清单，尚不是经过独立打包和目标集成验证的组件库。默认来源根目录为 [fable源码](../assets/sources/fable5.1-high/)；已知缺口和版本见[三工程对照](builds-comparison.md)。

依赖边界确定后，用[功能目录](feature-catalog.md)核对选定单元的设计和完整操作路径：侧栏见[外壳细目](feature-shell.md)，可编辑列表/表单见[DNS细目](feature-dns.md)。只选局部单元不降低该单元内部的保真程度；演示/占位功能及已知缺口需按业务接线或有依据地处理。

## 选什么、一起取什么

| 单元 | 源码入口（相对来源根） | 一起读取或迁移 | 对接目标项目 |
|---|---|---|---|
| 整体外壳 | `src/components/shell/AppShell.tsx`、`TopBar.tsx`、`Sidebar.tsx`、`ShellContext.tsx` | 主题、导航数据、UI基础组件、图标、样式；采用搜索面板时包含 `CommandPalette.tsx` | 资源上下文、导航/权限、主题、主内容、移动入口 |
| 侧栏 | `src/components/shell/Sidebar.tsx`、`ShellContext.tsx` | `src/data/nav.ts`、hooks、router接口、`cn`、Badge/Kbd及其实际依赖；`AppShell.tsx`中的槽宽和内容关系 | 导航配置、当前路径/跳转、持久化键、顶栏高度、移动开关；采用Quick search时对接面板 |
| DNS可编辑列表 | `src/pages/dns/DnsRecordsPage.tsx`、`src/pages/dns/DnsRecordForm.tsx` | `src/components/ui/`中实际使用的primitives/layout/overlays/table、ToastProvider、`src/data/records.ts`、hooks、router查询接口、`cn`、样式 | 记录模型、读写/权限、分页筛选策略、偏好与草稿；替换原localStorage模拟数据路径 |
| DNS编辑表单 | `src/pages/dns/DnsRecordForm.tsx` | `src/data/records.ts`中的类型/校验/选项，Field/Input/Select/Toggle/Button、Alert/InfoTip及其实际依赖、`cn`、样式 | 初始值、字段语义、校验、保存/取消/删除回调；挂载端负责编辑对象、容器与回焦 |

可编辑列表包括操作区、列表、编辑容器、共享表单及状态反馈；不是只取 `<table>`。只要侧栏时，不需要整个内容页；只要表单本体时，也不需要整个列表。按单元裁边界，不在单元内部任意丢细节。

## 共同视觉基础

读取来源的 `src/index.css`、主题模块及相关构建配置：字体、语义色、密度、间距、边框、图标、控件、过渡与断点一起形成外观。Tailwind类名需要目标构建链识别，Lucide图标需要实际依赖；复制JSX不能自动带来这些能力。

局部复用时，将必要令牌与样式置于目标的模板区域，检查旧全局CSS和组件库默认值的覆盖；避免为一个单元覆盖整站的字体、控件或主题。必要时抽出独立样式或包装组件，但默认值和行为仍与来源一致。

`Sidebar.tsx`依赖ShellProvider和路由接口；DNS页依赖ToastProvider。这些是当前源码接口，不能把清单误当作“复制单文件即可运行”。按实际import递归核对依赖；共享文件还可能引用浮层与hooks。

## 局部抽取与维护

同栈优先复制选定单元及依赖闭包到目标开发目录，再把导航/数据/权限/接口改成配置或适配接口。异栈按同一视觉与状态契约移植。采用来源里哪种编辑容器、排序/选择/列宽机制，要在抽取边界中写清。

表单的字段与校验可以单独抽取；展开行、弹窗、手机卡片由列表挂载端决定。复用这些编辑形态时，一并迁移打开、关闭、保存、错误恢复和回焦，避免只复制表单后由旧容器重新决定外观。

若要将抽取结果长期作为独立模板分发，应在开发目录中定义清楚的配置/回调接口、默认样式和可运行预览，再验证采用的状态。验证后归档单一实现，说明来源与必要差异；不要同时维护多份相同源码而缺少更新关系。

先用固定样例数据对照模板本身，再接真实业务检查数据长短与失败状态。每次模板修复后，核对采用单元及必要差异，更新对应预览；原型中的已验证行为不自动算目标应用通过。具体迁移与对照验收见[定制指南](cf-customization-guide.md#完整模板迁移)。
