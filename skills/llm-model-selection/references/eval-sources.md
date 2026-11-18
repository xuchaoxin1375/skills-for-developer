# 评测源与口径

各来源的测量对象、URL 取数路径和已知陷阱。分数与名次不写在这里，按会话当时现取。

## 来源选择与分工

| 来源 | 测什么 | 用它的场合 | 不要用它回答 |
|---|---|---|---|
| Artificial Analysis | 模型级综合能力；模型 + harness 的 agentic 编程 | 需要独立第三方、跨厂商可比的数字 | 具体 IDE 插件体验、订阅额度 |
| ModelDial | 私有题集上的编程五轴能力与中文写作 | 想看前端还原、可维护性、中文成稿 | 与公开基准名次的直接换算 |
| Terminal-Bench | 终端里端到端完成任务 | 命令行 agent、CI/运维类自动化 | 仓库级补丁质量 |
| SWE-bench 系列 | 真实 GitHub issue 的补丁是否通过测试 | 修 bug、改仓库类任务 | 终端操作、前端视觉 |
| Vals AI | 独立 harness 下的职业任务评测 | 交叉验证厂商自报 | 替代目标基准 |
| 厂商模型页 / 定价页 | 规格、价格、档位、可得性 | 定稿事实与成本 | 独立性能结论 |
| models.dev / OpenRouter | 模型 ID、窗口、模态、工具支持、上下文价 | 机器初筛与接入前核对 | 性能排名 |

同一主张至少两个独立来源时才写成结论；同一公告的转载不算独立。

## Artificial Analysis

- 模型榜：`/leaderboards/models`，`/models` 有散点图与筛选；单模型页 `/models/<slug>`，含各 effort 档位与 provider 价格。
- 编程 agent 榜：`/agents/coding-agents`；单个 harness 页 `/agents/coding-agents/<harness>`（如 `claude-code`、`codex`、`antigravity-cli`、`kimi-code-cli`、`opencode`、`muse-code`、`devin-fusion-cli`）。
- 组合对比：`/agents/coding-agents/comparisons/<a>-vs-<b>`，页面表格给出同一 harness 下各模型档位的分数、成本、耗时、token 用量——这是取"同 harness 横向比模型"最快的一页。
- 方法论：`/methodology/coding-agents-benchmarking`、`/methodology/intelligence-benchmarking`。

判读要点：

- **两个指数不要混**。Intelligence Index 是模型级；Coding Agent Index 是"模型 + harness"级，改动题集时版本号会跳（大版本变更会整体降分，旧分数不能与新分数比）。
- Coding Agent Index 是三个基准等权平均，必须同时看分项：仓库改造、终端执行、代码问答是三种能力，总分相近不代表强项相同。
- 成本页口径是**按 token 计费的 API 成本**，含缓存命中价、缓存写入价与输出价；不是订阅账单，也不含基础设施与人工复核。
- 同一模型不同 effort 档位在榜单上是独立条目，取"最高分档"和取"最便宜的高分档"会得到不同结论。
- 榜单会标注 `No publicly available API`、限量发布或仅订阅可得；这类条目不能默认可采购。
- 若模型配置里存在安全回退（拒绝后由另一个模型接手），部分尝试并非由名义模型完成，读分数时要留意脚注。

## ModelDial

- 入口：`/`（首页有总榜与前 20）、`/leaderboard/coding`、`/leaderboard/coding?axis=<维度>&view=cost`；单模型页 `/models/<slug>?config=<...>&axis=overall`；对比页 `/compare`。
- 方法：`/method`；题集范围：`/datasets`；许可：`/data-license`。

判读要点：

- 综合分是**五轴加权**：后端工程、前端交互、知识推理、视觉审美、可维护性，权重写在 `/method`，不按等权假设。
- 私有题集：能降低训练污染风险，但"私有"不等于"无偏"，任务与评分设计仍需看 `/method` 与 `/datasets`。
- 单模型页给出**各 effort 档位的完整成绩 + 该档评测费用与耗时**，适合算"每提一档的边际收益"。
- 费用是该次评测的 API 花费，不是订阅价，也不是日常对话单价；token 用量因分词器不同不可直接当效率。
- 首页的"表现与消耗"图用对数刻度，象限分界是当前范围内中位数，不是绝对阈值。
- 榜单只收录当前已发布、数据完整的配置；缺项不按 0 分补齐，跨榜比较前先确认两边都收录了同一配置。

## Terminal-Bench

- 官方榜：`https://www.tbench.ai/leaderboard/terminal-bench/<version>`。
- 版本各自独立：不同版本改了题集、任务数与资源配置，分数**不可跨版本比较**；同一版本内的重评分（小版本升级）通常落在原置信区间内，但仍应按新版本号引用。
- 榜单行是"模型 + agent + effort"的组合，不是裸模型；厂商自报的未复现结果通常列在未排名区，不能拿来自证领先。
- 公开榜只覆盖走标准 harness 的运行；自建 harness 的成绩不可与之并列。

## SWE-bench 与 DeepSWE

- `https://www.swebench.com` 下有 Verified / Lite / Multilingual / Multimodal 等多个子榜，题集不同不可混。
- 分数是"补丁通过测试的比例"，不测终端操作、不测解释质量。
- 第三方复现常用 mini-SWE-agent 等固定 harness；与厂商用自研 harness 得到的数字不可直接比。
- 推理预算（max effort、多轮重试）会显著抬分，引用时要带设置。

## Vals AI

- `https://www.vals.ai` 用自有 harness 跑职业任务，适合交叉验证厂商自报。
- 其分数与官方榜、AA 的分数量纲不同，只做方向性对照，不做名次合并。

## 厂商页面

- 定稿用：模型 ID、上下文窗口、最大输出、思考档位名称与默认值、输入模态、缓存价与缓存写入价、长上下文加价规则、限流与可得性。
- 厂商自报的基准分数只能作为"厂商主张"引用，并注明未独立复现；与独立评测冲突时以独立评测为准，并把冲突写出来。
- 定价常有条件：按 prompt 长度分档、高峰/低峰差异、缓存命中折扣、批量折扣、促销到期日。引用时带上条件与核对日期。

## 取数顺序建议

1. 先用 AA 或 ModelDial 确定候选集合与大致档位。
2. 用厂商定价页核对候选的实际价格、档位与可得性。
3. 对候选中要重点推荐的一两个，补一个不同来源的独立数字（另一榜单、Vals 或公开复现）。
4. 记录读取日期；跨会话复用时重新核对，因为榜单与价格都会变。

## 已知会误导的点

- 第三方榜单截图或二手汇总里的名次常常滞后一到两个版本，并且经常混用不同基准版本。
- "最便宜"的条目常是缓存命中价、批量价或促销价，不能当标准单价。
- 上下文窗口标称值与实际计费阈值不同：超过某个长度后单价可能翻倍，长上下文场景要单独算。
- 开源权重与开放 API 是两件事：权重可下载不等于有官方托管端点，也不等于可商用（许可证另算）。
- 免费额度、试用赠金与"限时免费"会改变短期性价比，但不构成长期成本结论。