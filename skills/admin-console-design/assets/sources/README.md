# 可复用源码素材

本目录是三参考工程的源码快照，2026-10-08归档；另附一份 2026-11-23 的 Vue 3 同栈候选移植。用于复制和适配完整交互单元，解决只有压缩产物无法整块复用的问题。原始源码/文档可能有演示限制或缺陷；行为取舍以[三工程对照](../../references/builds-comparison.md)与领域reference为准。

| 目录 | 内容 | 常用入口 |
|---|---|---|
| `fable5.1-high/` | src、docs、根配置、依赖锁文件，含2026-10-08外部侧栏修复与后续OpenCode焦点/节点/点击修复 | `src/components/shell/`、`src/pages/dns/`、`src/index.css` |
| `sonnet5.5xhigh/` | src、docs、根配置、依赖锁文件，含用户新Stage | `src/ui/columns.tsx`、`src/dashboard/data.tsx`、`src/showcase/Stage.tsx` |
| `gpt6astra-max/` | src、public、tests、根配置、依赖锁文件 | `src/components/DnsConsole.tsx`、`public/docs/`、`tests/acceptance.spec.ts` |
| `vue3-cloudflare-shell/` | Vue 3 + TypeScript 外壳候选移植：App、SidebarNav、Icon、宿主导出样式与验证记录；只复刻布局与交互 | `App.vue`、`components/SidebarNav.vue`、`style.css`、`verification.json` |

不包含node_modules、dist、zip、运行日志或其他skill。可在目标项目中取对应模块，或把整个工程复制到独立开发目录后按其package.json/锁文件安装并运行；不要在素材目录原地开发，避免快照漂移。

共同技术栈是原样归档，目标应用不因此必须改框架。迁移前核对`@/`别名、全局CSS、主题/路由provider、数据模型、UI依赖和持久化键；没有真实API的示例功能不能冒充生产接线。

`vue3-cloudflare-shell/` 是**同栈候选**，不与三份 React 工程并列为主模板：它只保留顶栏、264/56 侧栏、Rail peek／抽屉、焦点与内容收纳等布局交互，示例配色使用宿主深青／中性令牌，不是 Cloudflare 官方色板；不能把它的颜色当作还原标准。使用前读该目录 `README.md` 的交互契约、集成步骤和限制。

按整体主题、侧栏、DNS可编辑列表或表单取用时，见[模板单元与依赖边界](../../references/template-units.md)。局部模板仍包含完整的视觉与交互依赖，不能仅复制入口文件后由旧UI随意补齐。

[manifest.json](manifest.json)记录来源标识、文件SHA-256、归档日期和对应产物SHA-256；文本校验先把CRLF归一为LF，避免跨平台Git换行转换造成假漂移。原文件内部措辞保持原样作为审查对象，不是skill新增的强制规则。
