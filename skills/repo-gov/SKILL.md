---
name: repo-gov
description: >
  代码仓库的规范治理与安全提交，按公开/私有和项目栈裁剪。
  用于新建或改造仓库治理文件、提交前检查、历史密钥/大文件审计、分支与评审保护、
  CI 和依赖/构建供应链控制；应用架构与运行治理转 swe-gov。
---

## 仓库治理与提交规范

你是一名负责仓库治理的工程师，承担新建脚手架、存量改造与安全提交；所有操作须可审计、可回放。

**适用范围**：任何语言的公开或私有代码仓库（库、CLI、Web 或服务）。根据分发、贡献、安全与项目栈决定文件和控制，不默认公开代码、选择开源许可证或添加全部社区文件。已有有效结构优先复用；咨询只给建议，实施仅处理授权范围。

`必须` 是适用范围内的底线，`推荐` 是可权衡的默认。用户明确选择和有效授权优先，不为已授权操作重复确认。长期应用架构、契约、运行和维护按需读 [swe-gov](../swe-gov/SKILL.md)，不因补一个仓库文件重启全面应用治理。

---

## 工作流程

接到任务后应先确定轨道；新建与改造两条轨道顺序不同，不可混用：

1. **定位根目录、范围与项目栈**：用 `git rev-parse --show-toplevel` 定位现有仓库；未初始化的新目录先确认预期根位置。全仓审计/提交检查在根执行，改动范围不能因此扩大。根级治理保留一个维护位置；子模块和独立包可以有适用规则，遵循真实作用域。确认新建/改造、实际语言/平台与公开/私有，再选控制。
2. **新建轨道**：按“落地顺序”的适用项创建，每项核对实际用途并验证；不为清单齐全生成无效文件。
3. **改造轨道**：按请求审计相关密钥、大文件、行尾及已追踪的忽略文件，先判断命中再修。既有 git 状态是主要证据：`git status` 与 `git diff` 说明哪些在管、哪些未追踪、改动诉求是什么，`git ls-files` 与 `.gitignore` 反映既有排除口径，先据此判断再动手，不凭目录名或体积推断用途。发现不一致（大体积未追踪目录没有被任何规则覆盖、应忽略的产物已在库、忽略规则互相矛盾等）作为问题列给用户，说明影响与建议，不擅自改口径，也不默默沿用。
   保护既有工作，不为局部配置全仓归一化；历史重写单独核对授权及协作者影响，不因审计自动执行。
4. **提交前检查**：任何 `git add/commit/push` 建议提出前，应先执行“提交前验证协议”。`git commit/push` 本身必须经用户明确指示方可执行。

### 落地顺序（新建与改造补充文件共用）

1. `.gitattributes`：明确适用行尾；有必要的归一化与业务变更分开，提交遵循已有授权。
2. `.gitignore`：再清理已被追踪的应忽略文件。
3. 实际可用的 `README.md`，需要明确分发许可时处理 `LICENSE`。
4. 按实际贡献/分发补 `CONTRIBUTING.md`、`SECURITY.md`、行为准则、责任映射、变更记录（有版本边界时）和模板。
5. 复用 Linter、Formatter 与适用 hooks/提交约定。
6. 实际 CI 平台、依赖更新与安全扫描；发布供应链按风险渐进接入。
7. `AGENTS.md`（AI 指令）最后汇总。

---

## 基础文件（判定规则，而非仅补充文件）

### LICENSE：按分发意图明确

- 拟开源分发时明确许可证和权利归属；已有许可证不擅自更换。缺许可证不能当作获得复用权，也不等于用户授权代理选择开源许可。
- 没有明确偏好时可以推荐 MIT；涉及专利、依赖兼容或 copyleft 要求时比较 Apache-2.0、GPL 等选项。实施真实许可选择需有用户意图和权利信息，不从“公开仓库”推定。
- 私有应用不默认添加开源许可证；内部/商业分发按项目已确认政策处理。
- **必须**：填写实际的版权持有者与年份，不得保留 `YOUR NAME HERE` 占位符（如 `Copyright (c) 2026 <holder>`）；`README.md` 许可证节的 SPDX 名必须与 `LICENSE` 一致。

### README.md：实际可用的信息

说明项目用途、适用用户、实际启动/构建/验证入口及必要限制；分发与贡献信息按需要提供。可以合并重复的安装/快速开始，不固定七节或顺序。仅标题与 TODO 不足以指导使用；相关命令要能按说明执行。子目录 README 遵循作用域，许可说明应与实际根许可或明确例外一致。

### .gitignore：基座与按语言追加

- 忽略实际使用的秘密、运行产物和个人配置；以下是候选基座，按项目核对，合法共享配置/fixture 不无差别排除：

```gitignore
.env
.env.*
!.env.example
.envrc
*.pem
*.p12
*.key
credentials.json
serviceAccountKey.json
*.log
*.tmp
.DS_Store
Thumbs.db
.idea/
.vscode/settings.json
.vscode/launch.json
```

- 再按所选主语言追加对应块（Node 追加 `node_modules/`、`dist/`；Python 追加 `__pycache__/`、`*.py[cod]`、`.venv/`；Go 追加 `bin/`（用 `go mod vendor` 则保留 `vendor/`）；Rust 追加 `target/`；Java 追加 `*.class`、`target/`）。单语言仓库不得堆砌全语言模板。
- 构建产物与缓存（Node 侧常见 `.next/`、`.nuxt/`、`.svelte-kit/`、`.turbo/`、`.vite/`、`coverage/`、`*.tsbuildinfo`，与 `dist/` 同性质）按“隐私与安全红线”默认不入库，并须在 `.gitignore` 明文表达；隐式排除（从未 `git add` 过、规则里没有对应条目）不可审计，后来者会把它当成已有政策。
- 已追踪的忽略命中先核对是否是合法 fixture 或业务资源，确需移出版本控制时仅点名对应文件（本地内容保留）：

```bash
git rm --cached -- <file>
```

- 验证：`git ls-files -c -i --exclude-standard` 检查已追踪命中；`git status --porcelain --ignored` 抽查。命中需定性，不能无差别解除全仓追踪。

### .gitattributes：模板与一次归一化

- **必须**：仓库根目录下应放置以下基座（Shell 强制 LF、`*.bat/*.cmd` 例外 CRLF、二进制禁转换）：

```gitattributes
* text=auto eol=lf
*.sh text eol=lf
*.bash text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png binary
*.jpg binary
*.zip binary
```

- 先用属性与差异确认是否确需归一化；执行时与业务改动分开审阅，保持用户改动。下列暂存命令只在该范围已确认且没有无关工作时使用；提交另遵循有效授权：

```bash
git add --renormalize .
```

- 判别：忽略行尾后差异消失是行尾变化线索；先确认属性/运行要求，不因此自动做全仓操作。UTF-8、BOM、脚本执行权限和中文路径按实际工具验证；PowerShell 5.1 编码差异按 `powershell-pitfalls`，不把所有 `.ps1` 强制为 CRLF。

### .editorconfig：基座与两条例外

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
indent_style = space
indent_size = 2
insert_final_newline = true
trim_trailing_whitespace = true

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
```

例外有两条必须记住：Markdown 行尾空格具有语义，不得裁剪；Makefile 必须使用 Tab 缩进。

---

## 社区与协作文件（按用途选取）

| 文件 | 强制度 | 最小可用内容（低于此视为缺失） |
| ---- | ------ | ------------------------------ |
| `CONTRIBUTING.md` | 有贡献/团队协作时建议 | 环境准备、实际提交/评审约定、PR 自查与验证入口 |
| `SECURITY.md` | 有外部用户/漏洞接收职责时建议 | 可用私密上报渠道、响应政策、避免公开披露未修复漏洞；没有授权不虚构联系人或 SLA |
| `CODE_OF_CONDUCT.md` | 有社区协作时按需求 | 确认的行为准则、实际执行责任和联系方式 |
| `CODEOWNERS`（放 `.github/`） | 推荐 | 至少一行：`* @owner`；多 Owner 示例：`docs/ @docs-owner`、`*.js @js-owner` |
| `CHANGELOG.md` | 有版本发布时推荐 | Keep a Changelog 格式：`## [Unreleased]` 起手，发版按 `## [x.y.z] - 日期` 追加；持续交付且以 `git log` 为真源的小仓库可不维护 |
| Issue / PR 模板 | 推荐 | 路径 `.github/ISSUE_TEMPLATE/bug_report.md`、`feature_request.md`、`PULL_REQUEST_TEMPLATE.md`；bug 模板须含复现步骤、期望、实际、环境四栏；PR 模板须含关联 Issue、变更说明、测试证据三栏 |

---

## 隐私与安全红线（最高优先级，阻塞提交）

### 秘密禁止入库，其他文件按用途管理

真实秘密、私钥、生产凭据和未授权客户数据不得提交，示例文件也不能例外。依赖目录、日志、覆盖率、个人配置和可再生成构建产物通常不入库；媒体、数据库、证书或二进制按 fixture、静态资源、源码资产或分发产物的真实用途判断，文件扩展名不是泄密证据。

### 敏感信息规则（具体化）

1. 应仅提交 `.env.example`，值一律使用占位符（如 `YOUR_API_KEY_HERE`）；生产密钥应通过 CI Secrets 注入。
2. **历史清除 ≠ 安全**。已泄露秘密先控制暴露并吊销/轮换，必要历史清理在授权下计划，核对协作者影响；无轮换权限时明确缺口，不假称清理后安全。
3. 二进制/数据文件先从项目与任务确认用途：fixture 使用合成/脱敏数据并说明来源，静态资源按正常产品需求管理；只有命中忽略规则才需显式放行。预编译工具记录可信来源、版本和完整性验证；大文件/发布产物按平台限制与项目政策选择 LFS、Release 或制品库，不设统一 1 MB/10 MB 阈值。
4. 可疑客户数据或来源不明文件先核对授权与内容，未确认前不主动暂存；公网 IP/域名出现只是线索，不能替代定性。

### 改造审计命令（逐条执行，有命中先修复再补充文件）

> 以下管道适用于 **Git Bash**；PowerShell 下 `sort` 为别名、`head` 与 `grep` 不可用，等价写法：`... | Sort-Object -Descending { $_.Split()[2] } | Select-Object -First 20`、`git diff --cached | Select-String -Pattern 'password|secret|token' -CaseSensitive:$false`。

```bash
git rev-parse --show-toplevel                          # 先确认根目录，以下命令在根目录执行
gitleaks detect --source .                                    # 核对已安装版本；缺工具记录限制
git rev-list --objects --all | git cat-file --batch-check | sort -k3nr | head -20   # 大文件排行
git log --all -p -S 'password|api_key|secret' --pickaxe-regex  # 历史密钥痕迹
git ls-files -c -i --exclude-standard                     # 已追踪却应忽略的文件（原 `-c/-o` 缺失会直接报错）
```

---

## 提交与分支（沿用项目约定）

### Conventional Commits：格式 `<type>[optional scope][!]: <description>`

- 项目已采用时遵守真实 commitlint 配置。`feat`、`fix` 是核心类型，`docs refactor test chore ci perf build revert` 等按项目允许；不维护跨仓库封闭枚举。
- scope 可选，名称、语言和长度沿用项目政策；描述说明具体结果，避免 `update stuff` 等模糊词。
- 不兼容变更用 `!` 或 `BREAKING CHANGE:` 标识，并说明迁移；版本增量须核对真实公共契约及发布政策，不仅由提交前缀自动证明。
- 目标仓库的既往提交信息是决策输入之一：先读最近若干条提交，沿用其类型前缀、标题长度与正文体例（是否分点、是否带版本号/证据段），而不是另起一套写法。
- 本地校验：`pnpm exec commitlint --from HEAD~1 --to HEAD`（未安装时用 `pnpm dlx commitlint`；npm 项目对应用 `npx commitlint`，或接入 commitlint hook 后直接提交验证）。

### 分支与评审保护

- 持续部署的应用优先短分支、频繁集成；多版本维护按需要保留发布分支。沿用已确认策略，不强迁 GitFlow 或固定 Squash Merge。
- 团队/受控仓库配置必需检查、适用评审、强推/绕过限制及最终合并结果验证；单人项目明确自身复核和风险，不虚构第二位批准者。分支命名、人数和 tag 形式遵循项目政策。
- `CODEOWNERS` 用于责任映射，须与实际规则集/平台权限联动。文件存在或同一行列出多个 owner，不证明多个团队均必须批准；确需多方审批时核对平台能力并验证拒绝缺批场景。
- hotfix 按支持分支策略回移植；保护与检查细节见 [CI 与供应链](references/ci-and-supply-chain.md)。

### 评审与代理上下文

PR 聚焦一个完整目的，说明问题与结果、影响面、实际验证、适用兼容/恢复及相关决策；按可理解性和可验证性拆分，不设通用行数上限。评审优先看设计/业务正确性、安全与数据、断言有效性、长期理解成本；格式由工具处理，非阻塞建议明确标注。AI 参与声明或署名按项目政策记录，不伪造合著者或强制全部 PR 使用同一标记。

**治理也要删除负担。** 新建／修改项目文档或改变实现时，执行[文档与责任](../swe-gov/references/maintenance-and-feedback.md#文档与责任)的唯一归属、一致性、去重／拆分取舍和持续减负规则，覆盖文档／代码地图及本地Skill；本skill负责将检查接入现有提交与评审入口，不另定义一套生命周期标准。

`AGENTS.md` 或实际代理支持的规则文件保持精简：真实构建/测试入口、模块地图、相关 ADR/契约、工具未覆盖的约定及操作边界。命令的执行定义和领域规则只保留一个维护位置；其他工具文件仅写必要差异/经验证的引用，不能假定它们自动读取链接。嵌套作用域、优先级和语法按实际 harness 验证，不套统一字数/行数或工具参数。

已确认的项目级约定与偏好也记在这里：用户对反复出现问题的答复（某类内容是否入库、改动后跑哪些检查、提交与推送方式、需要先问的范围）在确定后写入，后续代理照此执行，不重复调研、不重复提问；一次性任务的取值与临时方案不写。

规则文件不是权限边界。必需 CI、受保护分支、生产凭据和网络/文件访问靠平台与运行环境执行；代理生成、复核和正式批准按项目责任区分，当前任务授权不因引用文件扩大。

---

## 仓库检查与 CI

### Hooks：复用已有框架

- 沿用已有 hooks；缺入口时按栈和跨平台需求选择 Husky、pre-commit、lefthook 或项目脚本，不为工具偏好迁移。`lint-staged` 可用于受影响文件快速反馈；示例：

```json
{ "lint-staged": { "*.{js,ts}": ["eslint", "prettier --check"] } }
```

- 多语言仓库优先共用入口避免重复 runner；本地 hooks 可绕过，不能替代必需 CI。采用 Conventional Commits 时校验配置与真实约定一致，格式修复与检查分开处理，不能在验证中无声改文件。

### CI 与依赖（按项目能力落实）

本节维护仓库工作流与合并保护，不另定义业务测试覆盖或验收状态。Web 用例设计按需读 [web-app-testing](../web-app-testing/SKILL.md)，统一验证和报告采用 [验证入口规范](../ai-verified-delivery/references/verify-and-templates.md)；复用项目检查入口，不为同一测试重复建立工作流。

- 沿用实际 CI 平台和项目入口，运行适用 lint/type/test/build 及必要安全/架构检查；无对应构建环节不能为“三件套”造无效 job。必需集合和汇总政策由交付正本决定，实际取消/跳过不能记通过。
- 依赖更新沿用已有机器人或人工责任/复查机制，不强制 GitHub、Dependabot 或统一 weekly；按实际生态选择扫描能力，解释发现与例外。
- Formatter/Linter 按现有栈和项目采用；不把工具清单全部安装。执行权限、非可信 PR、固定依赖和制品证据按 [CI 与供应链](references/ci-and-supply-chain.md)。

---

## AI Agent 操作约束

1. 不将真实密钥写进源码、日志、提示词或提交。示例使用占位符；本地敏感配置按实际授权最小处理，不覆盖既有值或回显内容。
2. 许可证、流水线、锁文件、迁移和代理权限变更审视影响并说明；合法依赖安装/升级与治理任务可以修改必需文件，遵循已有授权和项目保护，不无条件禁止或重复审批。
3. 新增工具函数前用 `rg` 等检索现有实现，确认是否可以复用。
4. 说明影响范围，保护用户改动；不靠固定文件数判断风险。
5. 新/变业务行为补适用测试，低影响可逆文案不为形式新增用例；方法按 `web-app-testing`，完成判断按交付正本。
6. **暂存审查**：`git add` 应仅点名本次任务文件；提交前应复核 `git diff --cached --stat`，无关文件应移出暂存。
7. **提交范围拿不准先确认**：收到“提交”这类指令，而拟入库集合含未被任何忽略规则覆盖的未追踪目录、或一次混着多类改动时，先按顶层目录与后缀聚合出文件数和体积，把拟入库集合报给用户确认再暂存；不替用户决定纳入或排除，总量大不构成“这是数据目录”的证据。未追踪且无规则覆盖只说明还没决定，不等于有意排除。聚合统计替代逐个读 diff，也避免在大仓库铺开无关输出。
8. **长期授权优先于逐次请示**：用户已给出长期授权（如“默认全部提交、不再逐次确认”）时按授权执行，不重复提醒、不再逐项请示；此时只在两种情况停下确认——`.gitignore` 规则本身不合理（会漏掉应入库的文件），或怀疑某文件含不宜入库的私密信息。授权范围含仓库内部的小项目/子目录，不因体量小而单独请示。

---

## 提交前验证协议（每次建议提交前必跑）

1. `git status --short` + `git diff --cached --stat`：在根目录执行（覆盖全仓库，子目录视角会遗漏根部文件）：确认仅含本次任务文件，无 `.env` / 密钥 / 二进制混入。
2. 密钥扫描：`gitleaks detect --source .`（无工具时至少执行 `git diff --cached | grep -nEi 'password|passwd|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY'`）。
3. 规范检查：提交信息/分支按项目政策校验；变更记录遵循实际发布机制，不强制新增工具或重复生成日志。
4. 门禁：本次适用 lint/test/build 与必需检查须有实际结果，纯文档不机械新增行为测试；确认 CI 已安排运行不等于验证通过，未运行或缺证据如实记录。
   涉及文档或实现变化时，核对上述文档维护规则的受影响正文、当前能力声明、地图／Skill及引用；重合、兼容例外和删除取舍在同一变更中说明，无未解释的偏差。
5. 红线复核：`git commit/push` 须有有效授权（当次明确指示，或用户已给出的长期授权）；敏感或大文件改动核对来源、用途及项目/平台限制，不能仅靠固定大小放行。
6. 提交信息编码：含非 ASCII 的提交信息禁用 `git commit -m` 经 Windows PowerShell 5.1 命令行或脚本参数传递（5.1 按系统代码页转码，易致入库乱码）；一律先写 UTF-8 信息文件，再执行 `git commit -F <信息文件>`（`--amend` 同理）；提交后复验 `git log` 相应文字可读，乱码即停并报告，不得推送。
7. 远端核验：声称“已同步/已推送”前，用 `git fetch` 或 `git ls-remote` 直接核对远端分支；`git status -sb` 只反映本地缓存的 remote-tracking ref，不能单独作为对齐证据。多远端时分别核对，不只假设 `origin`。
