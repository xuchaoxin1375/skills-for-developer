# 验证入口、模板、防作弊与工具选型

## 一、统一验证入口契约（CI、钩子、人调同一个）

- 命令形如 `verify --level Lx [--base origin/main] [--spec <含AC的spec路径>] [--tasks <tasks路径>]`；
Node 实现优先（Windows 无需 Git Bash），bash 实现等价亦可，`package.json` 统一暴露。
- 参数语义：`--level` 定检查组合；`--base` 定 diff 基准（本地默认 HEAD、CI 传目标分支）；
`--spec` 供 L3 追溯检查；`--tasks` 供清单检查；部分任务显式传 `--allow-open-tasks` 并在报告说明。
- 等级与检查：L0（格式/变更 Lint/类型/相关单测 + 完整性）→ L1（+ 全量单测 + 构建 + 冒烟 E2E）
→ L2（+ 全量 E2E + 覆盖率不降 + 可访问性 + 依赖审计，视觉回归推荐）
→ L3（+ 追溯 + 多浏览器 + 视觉 + 安全扫描 + 性能预算 + 开关检查）→ L4（+ 威胁建模产物 + 迁移回滚演练 + DAST + SBOM/来源证明）。
- 输出契约：每个步骤 `PASS/FAIL <step>` + 末尾汇总 JSON（含 level、变更文件数、失败步骤），`CI=1` 非交互。
- 钩子建议：PostToolUse 只做秒级格式化/Lint；Stop 做分钟级 `verify`（读进度文件 `level:` 行，识别
`stop_hook_active` 防死循环，失败以 `decision: block + reason` 回灌）；提交前跑 L0 与完整性，推送前跑 L1；
CI 按 PR 标签取最高等级（缺省按 L2 从严）。

## 二、AGENTS.md 最小骨架（保持一两百行，细节链到 docs）

项目概述与目录 → 环境与命令（含包管理器、dev/typecheck/lint/test/e2e/verify/doctor）→
变更分级与判级规则（T/R/L，不确定取高）→ 完成定义（verify 退出码 0、tasks 全勾且有证据、无 TODO 标记、
无 skip/only、无放宽断言、用户可见行为有自动化覆盖且测试名含 AC 编号、按模板写报告；禁用"基本完成/应该可以"）
→ 边界（总是做 / 先询问 / 绝不做：不许改门禁跳测试降阈值、不提交密钥、不虚报测试通过）
→ 代码风格 → 上下文与续作（progress.md + tasks.md + 最近提交）。

## 三、tasks.md 与 RTM（状态机 + 追踪）

- tasks 任务格式：`T编号 + 做什么 + 覆盖 AC + 验证命令`；状态只用 `[ ]` 未开始 / `[~]` 进行中（同时最多一个）
/ `[x]` 完成且有证据 / `[!]` 阻塞（写原因与待决策问题）。禁止证据为空勾选。
- RTM 每行：`REQ-ID | 要求 | 关键程度 | 实现位置 | 测试 ID | 证据 | 状态(pending/passing)`。
完成公式：`DONE = 范围覆盖 ∧ 场景覆盖 ∧ 质量门通过 ∧ 证据完整 ∧ 发布就绪`，任一不满足不许 DONE。
- 长任务另存机器可读 `task-state.json`：taskId、acceptanceLevel、status
（planned/in_progress/blocked/failed/verified）、requirements（含 state，只能凭证据更新）、
blockers、nextAction，供跨会话续作。

## 四、完成报告模板字段（ALWAYS 按 SKILL.md 八节输出，此处为字段说明）

定级与标签 → 基线（分支/提交/已有失败）→ RTM 逐条 → 实际执行命令（命令/环境/退出码/产物，
未执行写 Not executed）→ 人工实操（场景/浏览器设备/结果/截图）→ 已有失败与新增失败 →
跳过项（检查/原因/批准/后果）→ 工具依赖变更（含锁文件与安全评审）→ 残留风险 → 发布回滚
（开关/监控/回滚命令/数据回滚/发布后冒烟）→ 最终状态与下一步。命令输出禁止编造。

## 五、防作弊表（作弊方式 → 检测）

加 skip/only、删测试 → 完整性扫描 + CI 对比测试用例数不下降；放宽断言 → 受保护路径人工确认 + 验证者看测试 diff；
过度 mock（mock 掉被测逻辑、E2E mock 内部网络）→ 规则禁 + 复核抽查；降覆盖率阈值 → 配置受保护 + CI 用主干阈值覆盖；
硬编码返回值 → 禁用标记扫描 + AC 至少两组数据参数化；吞失败（`|| true`、改警告）→ 全等级禁 + 审退出码；
`console.log` 与空实现（`=> {}`、仅 return null）→ 扫描拦截（noop 命名可例外，knip 查未引用导出）。

## 六、WebUI 测试分层与工具选型

静态（tsc/ESLint 或 Biome/Prettier/knip）→ 单元（Vitest）→ 组件（Testing Library/jsdom 或浏览器模式，
按角色标签文本定位）→ 集成（MSW 复用浏览器与 Node 网络行为）→ E2E（Playwright，自动等待、Trace、
截图视频网络记录，失败看 DOM 快照）→ 视觉（截图基线，Linux CI 装 CJK 字体，混系统一在容器生成基线）
→ 可访问性（axe 自动查 + 键盘/焦点/读屏/缩放/高对比/减动画人工抽）→ 契约（Pact/OpenAPI，前后端独立发布时必备）
→ 真实依赖（Testcontainers/Compose，涉库行为不全 mock）→ 性能（Lighthouse CI/size-limit，看相对基线回退）
→ 安全（CodeQL/Semgrep、OSV/Trivy、ZAP 被动常开主动隔离、gitleaks）→ 发布（SBOM SPDX/CycloneDX、SLSA 来源证明、Rulesets/Environment 保护）。

选型四原则：有 CLI 且退出码可靠、输出可机读、无头可跑、跨平台可装；沿用仓库现有栈优先，不重复装功能重叠工具；
新项目做 3–5 个代表性场景 PoC（含至少一个失败诊断）；MCP 用于探索、CLI 用于验收。
国内注意：npm 镜像、Playwright 浏览器镜像与缓存路径、代理变量（*nix export / PowerShell `$env:` / git 单独配）、
`.gitattributes` 锁 LF、终端 UTF-8（`chcp 65001`）。

## 七、弱模型任务提示模板（放 `docs/prompts/task.md`，每次复制使用）

```markdown
你正在执行 tasks.md 中的任务 T3。只做 T3，不要碰其他任务。
步骤（严格按顺序）：
1. 把 T3 标记为 [~]。
2. 先写出 T3 验收标准对应的失败测试。
3. 实现使测试通过。
4. 运行 `pnpm verify --level L1 --base HEAD`，把输出最后 20 行贴出来。
5. 若出现 FAIL，只修复该步骤，最多重试 3 次；仍失败则把 T3 标记为 [!] 并写明原因，停止。
6. 通过后填证据（测试名），标记 [x]，`git commit`（信息含 T3）。
禁止：留下 TODO；使用 test.skip；修改门禁脚本或放宽断言让它通过。
```

强弱分工：规格、任务拆分、独立复核用强模型；逐任务实现可用弱模型——弱模型短板在判断与自评，不在局部编码。
停止条件显式化：最大步数、最大工具调用数、最大 token 预算，触顶返回部分结果并询问下一步，
让"部分完成"成为显式状态而非伪装成完成。

## 八、持续改进循环与度量

每个逃逸 bug 回答"哪一层门禁本应拦住它"，沉淀为三者之一：AGENTS 规则、verify 新检查、新测试用例。
月度回顾：门禁一次通过率、钩子阻止次数、独立验证不通过率、逃逸缺陷数、每等级平均验收耗时；
等级判据按数据调整（只升不降的规则不变，判据的边界可以调）。

## 九、团队落地顺序（从零建这套体系时按序，别一次全上）

1. **第一周**：AGENTS.md（判级 + DoD + 边界）+ 统一 verify 入口 + doctor 自检 + 完成报告模板。
此时没有 E2E，"做一半"也已大幅收敛。
2. **第二周**：pre-commit/pre-push 钩子接入 + 5–10 条核心路径 `@smoke` E2E，L1 生效。
3. **第三至四周**：CI 按标签分级、覆盖率阈值、可访问性扫描；L2/L3 走独立验证与人工清单。
4. **之后**：安全扫描、SBOM、发布保护与回滚演练（L4 才需要）；每个逃逸 bug 沉淀为规则/检查/用例。

最小必做集（只有精力做最少一组时）：禁止虚假完成与禁止静默跳过 → L0–L4 等级 → verify 快/标准/严格三档命令
→ 每条 AC 有测试或人工证据 → 实现与验证分离 → 四态状态机 → PR 必过 CI 才能合并。
