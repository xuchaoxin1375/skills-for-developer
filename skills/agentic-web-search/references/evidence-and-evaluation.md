# 研究依据与评测

本文件说明本 Skill 各项规则的来源，并给出公开基准与自建回归集的用法。文中论文与基准信息来自两篇联网搜索指南，使用前建议核实最新版本。

## 核心研究依据

| 主题 | 来源 | 结论要点 |
| --- | --- | --- |
| 快变知识与错误前提 | [FreshLLMs / FreshQA](https://arxiv.org/abs/2310.03214)（Google，2023） | 提出 FreshQA 动态基准，覆盖快变知识与**错误前提**两类问题；所有模型在这两类问题上都表现吃力 |
| 证据组织与幻觉 | [FreshPrompt](https://aclanthology.org/2024.findings-acl.813/) | 检索证据的数量与顺序都显著影响正确性；将证据按时间从旧到新排列、最新最靠近问题，并要求简洁直接回答，可减少幻觉 |
| 检索循环训练 | [Search-R1](https://arxiv.org/pdf/2503.09516)（COLM 2025） | 用强化学习让模型在推理中自主生成多条查询并实时检索；7B 模型相对基线提升 26%，说明“何时搜、搜什么、搜几次”本身可学 |
| 浏览深度基准 | [BrowseComp](https://openai.com/index/browsecomp/)（OpenAI，2025-04） | 1,266 道多跳难题；“browsing alone is not sufficient”，需要策略性推理与路径选择，准确率随测试时计算量平滑上升 |
| 工具工程 | [Anthropic：Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) | 工具命名空间、返回有意义的上下文、token 效率、错误信息引导 |
| 智能体范式 | [Anthropic：Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) | ReAct 式“推理与行动交替”是 Agentic Search 的思想来源 |

## BrowseComp 的量化差距

OpenAI BrowseComp 官方数据说明“开了联网”与“会联网搜索”的差距：

| 配置 | BrowseComp 准确率 |
| --- | --- |
| GPT-4o（不联网） | 0.6% |
| GPT-4o（开启浏览） | 1.9% |
| Deep Research（专门训练的持续浏览 Agent） | 51.5% |

数据来源：[OpenAI BrowseComp 官方页](https://openai.com/index/browsecomp/)。差距超过一个数量级，瓶颈在使用方式而非联网本身。

## 可用公开基准

| 基准 | 侧重 | 适用 |
| --- | --- | --- |
| FreshQA（Google，持续更新答案） | 快变知识、错误前提 | 检验时间锚定与前提纠错能力 |
| BrowseComp（OpenAI，1,266 题） | 难找、多跳、需持续浏览 | 检验搜索深度与策略 |
| SimpleQA | 短事实问答与校准 | 检验引用准确与“不知道就说不知道” |

## 自建回归集

公开基准用于定位弱项，业务效果靠自建回归集守住。

- 收集 20 到 50 个“答案会随时间变化”的问题（当前版本号、当前负责人、当前价格），人工标注答案与标注日期，定期更新。
- 每次修改系统提示词、更换搜索供应商或调整工具参数后，跑一遍回归集。
- 除最终正确率外，记录**过程指标**：搜索次数、是否读全文、是否交叉验证、是否发生引用幻觉（数字张冠李戴、把“某文章说 X”写成“X 是事实”、给出不存在 URL）。

## 引用

- FreshLLMs：`arXiv:2310.03214`
- Search-R1：`arXiv:2503.09516`
- BrowseComp：`arXiv:2504.12516`
