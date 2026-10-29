# 触发评测

description 是唯一的自动触发入口。改描述、改职责边界或拆分能力后，用本页跑一次最小对照，确认没有把该进的请求挡在外面，也没有把邻近 skill 的活抢过来。

取样规模、何时值得跑、写法纪律以[触发描述维护](../../../docs/skill-authoring-workflow.md#触发描述维护推荐)为准；本页只给可执行的 prompt、判据、记录格式和案例库。

## 取样

- **正例**：取真实任务原话，不要写“请使用某 skill”。覆盖不同入口，例如从零新建、已有文件、长流水线里的中间产物。
- **负例**：选相邻 skill 的真实任务，优先共享关键词但归属不同的近邻。太不相关的负例测不出问题。
- 同一批正负例在改描述前后各跑一次，只改 description 与 README 行，不同时改正文。
- 下面的案例库是回归样例池：单次评测按工作流取 3–5 条正例、2–3 条负例，不必全跑；大改描述或职责拆分时再扩大。

## 子代理判定 prompt

把下面模板连同请求列表交给一个独立上下文的子代理。它只判断、不执行，避免真实加载掩盖描述本身的问题。

```text
你是 skill 触发判定器。只根据当前 available skills 列表里的 name + description 判断，
不要执行任务、不要读取任何 skill 正文、不要调用工具。

对下面每条用户请求，输出一行 JSON：
{"q":"<编号>","skills":["<skill-id>",...],"reason":"<一句话>"}

规则：skills 按会实际加载的顺序排列，最多 3 个；没有合适的就输出空数组；
不要因为请求里出现某个词就机械匹配，要看请求真正要完成的任务。

请求：
1. <原话>
2. <原话>

只输出 N 行 JSON，不要输出其他内容。
```

判定用独立子代理，不把“目标 skill 是哪个”写进 prompt；否则测的是服从性，不是触发。

## 判据

- **正例**：目标 skill 出现在 `skills` 列表中；排第一更佳，但不强制。
- **负例**：目标邻近 skill 不得出现；出现即视为改坏。合理的上游或下游 skill 可以同时出现（例如挑战页抓取同时命中 `network-access`），但不能替代目标。
- **回答质量**不作为触发证据；只看加载了哪个 skill。
- 正例漏掉、负例误命中，先回退描述改动，再换一种说法重试；不要靠加更多关键词硬压。

## 记录

每次评测在 `.workspaces/<skill-name>-workspace/` 留一份结果，至少包含：

| 字段 | 内容 |
| --- | --- |
| 日期与模型 | 实际运行日期、子代理所用模型；未记录就写明未记录 |
| 变更 | 改了哪个 skill 的 description，改前改后各一句 |
| 样本 | 正例与负例的条数与原文 |
| 结果 | 每条期望、实际、结论 |
| 限制 | 模拟判定还是真实任务执行；是否单次运行 |

单次小样本只说明“这批样例上没坏”，不宣称统计显著。要证明真实触发，需在独立会话里实际执行任务并观察加载。

## 案例库

以下是 2026-10 审计触发描述时使用的一组通用请求，可作为新 skill 或大改描述后的回归样例；判定模型未记录，复跑时补记。

### 正例

| 请求 | 期望主 skill | 可接受的附带加载 |
| --- | --- | --- |
| 手机窄屏下表格操作列的按钮放不下，总是横向滚动，怎么收纳才不挤 | `adaptive-responsive-guide` | `frontend-design` |
| 把这个榜单页面的前 20 名和分数提取成 CSV | `htmlmini` | — |
| 我们后台界面太像模板了，想要一个有辨识度的视觉方向，先别写代码 | `distinctive-design-director` | `frontend-design` |
| 这个下拉展开动画很卡，用户开了 reduced-motion 还在动 | `web-animation-guide` | `frontend-design` |
| 做一个管理后台的侧栏折叠和用户列表批量编辑 | `admin-console-design` | `frontend-design` |
| 帮我把这个 Python 脚本改成支持批量覆盖配置文件，写之前先做预检，别把误报当阻断 | `scripting-best-practices` | — |
| 新仓库要初始化，帮我选个开源许可证，再补 SECURITY 和 CONTRIBUTING | `repo-gov` | `project-docs` |
| 这个站 Cloudflare 一直过不去，普通请求只拿到挑战页，需要渲染后的 HTML | `resilient-browser-fetch` | `network-access` |
| 我想做个每天自动备份照片的小工具，但我完全不懂技术 | `lightweight-app-builder` | — |
| 帮我配置 Codex 用第三方模型，web_search 一直不下发 | `codex-model-config` | — |

### 负例（近邻，不应命中目标 skill）

| 请求 | 应加载 | 不应命中 |
| --- | --- | --- |
| 帮我把这篇现成文档润色一下，调整标题层级和表格排版 | `markdown-style` / `doc-rewrite-review` | `project-docs` |
| 这个 React 组件按钮颜色改成品牌蓝，间距调大一点 | `frontend-design` | `adaptive-responsive-guide` |
| sticky 表头滚动到一半就失效了，帮我看看 | `sticky-position` | `adaptive-responsive-guide` |
| 帮我检查这个页面的文字对比度是否达标 | `frontend-qa` | `adaptive-responsive-guide` |
| 给这个公共函数补 docstring 和参数说明 | `code-comments` | `project-docs` |
| 把这个 PDF 合同转成 Markdown | 无 | `htmlmini` |
| 帮我把这个 HTML 页面的按钮改成圆角 | `frontend-design` | `htmlmini` |
| 帮我给这个函数写单元测试 | `web-app-testing` | `project-docs` |
