---
name: general-doc-writing
description: >
  编写不属于教学文档、项目配套文档、调研报告或笔记归档的通用技术文档：
  技术方案、设计说明、需求说明、备忘录、说明文、评审材料等。
  当用户要求从零写这类通用文档，且请求不属于教学、项目配套、调研或笔记归档时使用。
  已有正文的改写、审校与合并走 doc-rewrite-review；教学文档走 learning-doc-design；
  项目 README、CLI/API、部署与 Runbook 走 project-docs；调研与方案比较走 tech-learning-research；
  笔记/博客归档走 note-blog-archivist；纯排版走 markdown-style。
---

## 通用技术文档写作

目标是让目标读者能理解、判断并使用这份文档，而不只是把信息堆出来。先确认产物职责与读者，再按通用基线组织内容；落到专门领域时转对应 skill，不在本 skill 内另建流程。

## 适用与边界

适用于没有专门产物 skill 的通用技术文档：技术方案、设计说明、需求说明、备忘录、说明文、评审材料、跨团队沟通文档等。

| 请求类型 | 去向 |
| --- | --- |
| 教学文档、教材、教程、课程、解释型学习指南 | [learning-doc-design](../learning-doc-design/SKILL.md) |
| 项目 README、CLI/API 参考、部署与 Runbook | [project-docs](../project-docs/SKILL.md) |
| 调研报告、方案比较、技术选型 | [tech-learning-research](../tech-learning-research/SKILL.md) |
| 已有正文的改写、审校、多源合并 | [doc-rewrite-review](../doc-rewrite-review/SKILL.md) |
| 笔记/博客归档 | [note-blog-archivist](../note-blog-archivist/SKILL.md) |
| 纯 Markdown 排版 | [markdown-style](../markdown-style/SKILL.md) |

## 最短工作路径

1. **确认产物与读者**：写清文档类型、读者、要支持的决定或动作、成功判据、范围与非目标、交付位置；区分建议/大纲与实际写作。
2. **选择结构**：按读者任务与信息依赖组织。技术方案按“问题—目标—方案—取舍—风险—落地”；说明文按“是什么—为什么—怎么用—边界”；评审材料按“结论—依据—风险—待决项”。不机械套模板。
3. **写正文**：操作入口先给用途与当前问题；影响后续理解的概念按三层写；实际运行、示意、未验证分开；破坏性操作先说明影响与恢复。
4. **验证与交付**：按最终顺序通读；检查术语、链接、代码步骤、隐私与破坏性操作；作者自查、实际运行、真实读者走查分开报告。

## 通用底线

按[技术文档写作基线](../doc-rewrite-review/references/technical-doc-baseline.md)执行；本 skill 只补充通用文档的产物判断和结构选择，不复制基线规则。

## 使用边界

- 确定属于教学、项目、调研、笔记或已有文本改写时，转对应 skill，不在本 skill 内另建流程。
- 排版与图示语法按 [markdown-style](../markdown-style/SKILL.md)；教学编排按 [learning-doc-design](../learning-doc-design/SKILL.md)。
- 不因写一份通用文档启动调研、合并、归档或项目治理；确有需要时按对应 skill 单独处理。
