# skill-up 行为评测试点

## 目的

验证 `alibaba/skill-up` 是否值得作为本仓库的**可选**行为评测工具。试点只回答三个问题：在现有环境能否低成本跑通、结果是否稳定可判读、维护负担是否可接受。试点不改变默认流程，也不把行为评测设为提交门禁。

## 为什么考虑

现有门禁覆盖结构、索引、链接与触发描述，但没有“装不装 skill，任务结果是否更好”的行为证据。`skill-up` 用声明式用例驱动 Agent，检查响应与 workspace 变更，输出结构化报告，正好补这一段；它与[触发评测](../skills/skill-authoring-sync/references/trigger-eval.md)互补：后者测“是否加载”，前者测“加载后做得对不对”。

## 事实基线

以下为 2026-10-29 实际读取上游的结果，采用前以官方最新文档为准。

| 项目 | 事实 |
| --- | --- |
| 许可证与形态 | Apache-2.0，Go CLI，提供 Windows amd64/arm64 压缩包 |
| 版本 | v0.14.0，发布于 2026-10-20 |
| 引擎 | `claude_code`、`codex`、`opencode`、`qodercli`、`qwen_code`，另支持自定义引擎 |
| 评测配置 | `eval.yaml` + `cases/*.yaml`；支持 workspace fixture、固定/混合/模拟多轮 |
| 评分 | `rule_based`、`script`、`agent_judge`；可分别配置被测 Agent、Judge 与模拟用户 |
| 报告 | `grading.json`、`benchmark.json`、`result.json`、JUnit XML、HTML |
| CI | 提供 GitHub Action，但为 Linux Docker，仅 Linux runner |
| Windows | 原生支持 `none` runtime 与 script judge；完整 agent 评测推荐 WSL2，或预装 Node 与对应 CLI |

## 试点范围

只选两个产出可客观断言的 skill，各 3 条用例；只用 `rule_based` 与 `script` 评分，不启用 `agent_judge`，避免把模型评分方差混进结论。

| Skill | 用例 | 断言 |
| --- | --- | --- |
| `htmlmini` | 固定本地 HTML，提取表格/榜单 | CSV 行数、表头、关键单元格值；不发起网络请求 |
| `scripting-best-practices` | 生成一个带参数的小脚本 | 文件存在、`--help` 退出码为 0 且含关键选项、`shellcheck` 通过 |

用例与产物先放 `.workspaces/skill-up-pilot/`，不提交；只有试点通过后才讨论是否在对应 skill 下保留 `evals/`。

## 环境与安装

- 优先 WSL2（Ubuntu），Node 与目标 Agent CLI 预装；原生 Windows 仅在确认 CLI 引导可用时使用。
- 固定 release tag（v0.14.0）或 commit SHA，下载官方压缩包并核对 `checksums.txt`；不使用 `curl | bash` 安装脚本。
- 二进制放临时目录或 `~/.local/bin`，不写入仓库。
- 不安装 `skill-upper`：它与 `skill-creator`、`skill-patcher` 的职责有重叠，试点阶段只用 CLI。

## 验收标准

- 从解压到跑通第一条用例不超过 1 小时。
- 同一批用例连续跑两次，通过/失败结论一致；不一致要能归因到模型随机性还是用例缺陷。
- 失败报告能指出具体断言与产物位置，而不是只给总分。
- 记录单次运行的耗时与模型费用；费用不可接受即停止。
- 用例与 fixture 不含真实密钥、内网地址或用户数据。

## 决策规则

- **通过**：保留这两个 skill 的 `evals/`，以手动或夜间可选任务运行；结构检查与触发评测仍是必需门禁。
- **不通过**：删除试点产物，继续用触发评测与 `skill-creator` 的手动对照，不引入新工具链。

## 风险与边界

- 项目较年轻（2026-05 创建），配置与 API 仍可能变化；升级前按 release 说明核对。
- 行为评测会产生模型调用费用与方差；试点用 rule/script 评分压低这两项，仍要记录实际成本。
- Windows 原生跑完整 agent 评测存在引导限制；WSL2 是默认路径。
- 引入后会多一套评测格式；`skill-up import` 可导入 Anthropic 风格 `evals.json`，但不要与 `skill-creator` 的产物各维护一份。
- 供应链：只用官方 release 与校验和，GitHub Action 固定 tag 或 SHA。

## 记录模板

试点结束后按下列字段记录，结论写入本文或对应提交说明：

| 字段 | 内容 |
| --- | --- |
| 日期与环境 | 运行日期、WSL2/原生 Windows、Node 与 Agent CLI 版本 |
| skill-up 版本 | tag 与校验和核对结果 |
| 用例 | 两个 skill 各 3 条，附期望与断言 |
| 结果 | 两次运行的通过率、失败断言、是否可复现 |
| 成本 | 单次耗时、模型费用 |
| 结论 | 通过/不通过，保留或删除的理由 |

## 后续

试点通过前不修改默认流程，也不在 CI 中启用行为评测。需要执行时按本文范围开一次独立任务，结束后回写结论。
