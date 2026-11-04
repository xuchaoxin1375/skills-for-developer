---
name: htmlmini
description: >
  网页与 HTML 核心骨架提取：总结、分析、审查页面，或从 URL／本地快照取表格、榜单、分数与规格时先提取，不整份读取原始 HTML。
  常规静态提取走短路径，复杂渲染与排障按需读参考；可用时优先于普通 web_fetch，缺失可回退。
  写采集规则前可侦查结构，但选择器与字段契约须回原始或渲染 DOM 核对。
  Also for English requests to summarize, review, or extract data from a page or HTML.
  写改页面与设计评审归 frontend-design／frontend-qa；批量采集、反爬与渲染调度归 resilient-browser-fetch；不处理 office/PDF 转换。
---

## 网页核心骨架提取

把 HTML 压成正文或界面骨架，避免将 CSS、脚本与样板灌入上下文。常规成功路径只需本文件，不预读浏览器引擎与故障案例。

## 最短执行路径

1. **复用输入**：已有新鲜原文或快照就本地提取，不为换工具重新抓取。只有 URL 时按 [network-access](../network-access/SKILL.md)选路；稳定直连无需代理，已知直连不稳的站点或慢直连按其规则改路。
2. **按目标选模式**：文章／博客／文档默认 `markdown`；营销／产品／定价／面板用 `ui`，缺长正文再补 `markdown`；表格层级和表单结构用 `html`。常用形态见下文“基础用法”，非常用参数才查工具 schema 或 `htmlmini --help`。
3. **一次抓取、按需复用**：需要多视图时保存 HTML 后本地切换模式，结果用工具自身 `--output` 落盘，不接 PowerShell 文本管道。检查内容是否覆盖目标字段，而不只看状态200。
4. **据提取结果回答**：正文有效就直接使用，不为形式回读整份原始 HTML。空壳、字段缺失或挑战页才进入[渲染与排障](references/rendering-and-troubleshooting.md)；缺失无法补齐就声明，不能编造数据。

## 使用边界

- **与 `web_fetch` 的分层**：二者都能接 URL，但 `web_fetch` 是通用取回层 (HTTP + 格式转换)，htmlmini 是内容提取层 (抓取 + 去样板 + 多视图)。同一页面任务默认先用 htmlmini，不必先抓一遍再转交；不可用、用户指定其他工具或需要非 HTML／原始响应时，回退内建抓取或 HTTP 客户端；不为一次简单读取自动安装依赖。
- **选路不等于强制代理**：htmlmini 可能继承环境代理，不读取本机登记。需要绕过显式代理时用 `--proxy direct`，确需代理时才显式传入；不要将省略参数等同于直连。
- **本地提取不额外按次收费**：可按实际缺口补提取，但不因免费重复联网或穷举模式；第三方 reader 和托管服务另受费用授权约束。
- **骨架不是采集契约**：清洗产物不保留完整 `class`／`id`／`data-*`。理解与摘要可直接据骨架回答；写选择器、核对内嵌状态或接口字段时，定点回原始或渲染 DOM 验证，不整份读脚本。
- **覆盖度决定结论**：论坛、列表与榜单核对总数、分页或选中子集，不能把首屏缺席当作无数据。图表精确数字缺失就报告，不凭截图或不相关实体的首个分数填值。
- **浏览器分工**：本工具负责读懂页面，渲染与挑战处理归 [resilient-browser-fetch](../resilient-browser-fetch/SKILL.md)。先区分网络失败、权限、限流与挑战，不一见403／5xx就加渲染开关。

## 调用入口

### 基础用法

默认值就是常用路径，按目标选一行即可，不必先查 `--help`：

```shell
htmlmini "<URL>"                         # 文章、博客、文档：默认 Markdown 正文
htmlmini page.html                       # 本地快照，不联网
htmlmini page.html -u                    # 面板、仪表盘、表单：组件清单
htmlmini "<URL>" -j                      # JSON：title / used / stats 等
htmlmini "<URL>" --render=always         # 静态 200 但正文靠 JS 水合
htmlmini "<URL>" --save-html page.html   # 抓一次，后续换模式复用
```

来源可以是 `http(s)` URL、本地 `.html` 文件或 `-` (stdin)；省略来源时读 stdin。模式短选项：`-m` markdown、`-s` skeleton、`-t` text、`-j` json、`-T` title、`-u` ui。只有渲染引擎、代理、断言、超时等非常用参数才查 `htmlmini --help` (短版一屏) 或 `htmlmini --help full`。

- CLI：上面的命令；命令缺失时可直接调用本 skill 的 `src/cli.js`，缺依赖则回退可用工具或说明后再安装。
- MCP：仅调用实际暴露的文件、URL或HTML提取工具，参数以当前 schema 为准，不猜工具名。
- 排查实际提取引擎时使用 JSON 输出中的 `used`；非 HTML 输入在各模式下原样透传。

## 按需深入

| 条件 | 入口 |
| --- | --- |
| 渲染、挑战、解释器／浏览器选择或结果异常 | [渲染与排障](references/rendering-and-troubleshooting.md)的对应症状，不通读所有引擎 |
| 按页面类型、字段与快照复用查实例 | [使用案例](references/usage-cases.md) |
| 需要第三方 reader 或归档辅助 | [辅助读取渠道](references/aux-readers.md)，使用前确认授权 |
| 工具安装、架构与接口说明 | [README](README.md)；参数与默认值仍以工具帮助为准 |

## 自检与验证

- [ ] 是否先提取且覆盖目标字段，未整份读取原始HTML？
- [ ] 常见提取是否直接走基础用法，未先查 `--help`？
- [ ] 模式与页面类型是否相符，已有正文和多视图是否复用而非重抓？
- [ ] 是否区分实际路线与省略代理参数，静态成功后未启动无关诊断？
- [ ] 列表覆盖、原始契约与无法核验的字段是否如实处理？

维护时运行仓库结构、链接与分发校验；改变可执行参数时另核工具帮助与实际行为。仅调整入口与参考组织，不代表浏览器路径或端到端性能已经复验。
