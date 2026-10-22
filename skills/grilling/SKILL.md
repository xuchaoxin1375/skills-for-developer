---
name: grilling
description: >
  设计拷问：动手前按设计树逐轮提问，把方案的分支、依赖和取舍问穿，直到双方对要做什么达成一致。
  用于 “grill me”、压力测试方案/设计、需求对齐、方案评审、动手前想清楚边界与失败模式，
  也用于用户说“先别写代码，先问我”“帮我把这个想法问清楚”。
  只做技术调研/选型报告走 tech-learning-research；已有明确 spec 直接实现走 ai-verified-delivery/tdd。
---

# Grilling

> 本地说明：正文保留上游英文原文，便于与上游 diff；触发描述已本地化。上游 main @ `5beb35b`（CHANGELOG 1.3.1，2026-10-19），MIT，见 [SOURCE.md](SOURCE.md) 与 [LICENSE](LICENSE)。
> 子代理按当前 harness 的 subagent 能力执行；事实查找由代理负责，决策交给用户。

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this round.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
