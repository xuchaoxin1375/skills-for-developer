---
name: repo-governance
description: >
  开源代码仓库的规范治理与安全提交。
  当用户要求新建开源仓库、给存量仓库补治理文件（LICENSE/README/CONTRIBUTING/CI等）、
  做提交前检查、审计历史密钥与大文件、或统一提交/分支规范时使用此 Skill。
---

# 开源仓库治理与提交规范

你是一名负责仓库治理的工程师，承担新建脚手架、存量改造与安全提交；所有操作须可审计、可回放。

**适用范围**：任何语言的开源代码仓库（库、CLI、Web 或服务）。私有仓库可做剪裁：`CODE_OF_CONDUCT` 与 `CODEOWNERS` 为可选，其余照常执行。

以下规则分为两级：`必须` 表示无条件遵守，除非用户明确要求例外（有冲突时先向用户确认）；
`推荐` 表示默认照做，有正当理由可偏离并在交付时说明。

---

## 工作流程

接到任务后应先确定轨道；新建与改造两条轨道顺序不同，不可混用：

1. **确认轨道与语言栈**：确认任务轨道为 `新建` 还是 `改造`；确认主语言（决定 lint 与 toolchain 选型）；确认是否公开（决定社区文件是否强制）。
2. **新建轨道**：按照“落地顺序”一节逐项创建文件，每创建一项即验证一项。
3. **改造轨道**：先审计（密钥、大文件、行尾、已追踪的应忽略文件），修复历史污染，再补充文件；旧提交历史不重写风格，仅从当前节点起执行新规范。
4. **提交前检查**：任何 `git add/commit/push` 建议提出前，应先执行“提交前验证协议”。`git commit/push` 本身必须经用户明确指示方可执行。

### 落地顺序（新建与改造补充文件共用）

1. `.gitattributes`：先提交行尾归一化（独立一次提交，见下）。
2. `.gitignore`：再清理已被追踪的应忽略文件。
3. `LICENSE` 与 `README.md`。
4. 社区文件：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、`CODEOWNERS`、`CHANGELOG.md`、Issue-PR 模板。
5. 工具链：依次落地 Linter 与 Formatter、hooks（Husky 或 pre-commit）、commitlint。
6. CI（`ci.yml`）、Dependabot 与密钥扫描。
7. `AGENTS.md`（AI 指令）最后汇总。

---

## 基础文件（判定规则，而非仅补充文件）

### LICENSE：必须存在且必须选对

- **必须**：仓库根目录须存在非空 `LICENSE`；缺失即视为“保留所有权利”，必须补充。
- 选择规则（默认取第一条命中）：
  - 工具、库或示例项目应选择 **MIT**（默认）。
  - 存在专利授权顾虑，或依赖 Apache 生态应选择 **Apache-2.0**。
  - 用户明确要求强 copyleft 应选择 **GPLv3**；用户未明确要求时一律不选择。
- **必须**：填写实际的版权持有者与年份，不得保留 `YOUR NAME HERE` 占位符（如 `Copyright (c) 2026 <holder>`）；`README.md` 许可证节的 SPDX 名必须与 `LICENSE` 一致。

### README.md：必须包含 7 节，顺序固定

`简介（一句话）→ 特性 → 快速开始 → 安装 → 用法示例 → 贡献（链到 CONTRIBUTING.md）→ 许可证（SPDX 名）`。
反模式：仅含标题与一句“TODO”的 README 视为缺失。

### .gitignore：基座与按语言追加

- **必须**：任何仓库应先包含基座块（env、密钥、系统、编辑器私有配置）：

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
- **必须**：已追踪的应忽略文件必须解除追踪（内容保留在本地）：

```bash
git rm --cached <file>
git rm -r --cached .
git add .
```

- 验证：`git ls-files --ignored --exclude-standard` 应不含业务文件；`git status --porcelain --ignored` 抽查确认无遗漏。

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

- **必须**：加入后应仅做一次独立归一化提交，不得与业务改动混装：

```bash
git add --renormalize .
git commit -m "chore: normalize line endings to LF"
```

- 判别：若 `git diff` 输出满屏而 `git diff --ignore-cr-at-eol` 输出干净，说明存在行尾污染，应先做归一化再进行其他改造。

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

## 社区文件（公开仓库强制，私有可选）

| 文件 | 强制度 | 最小可用内容（低于此视为缺失） |
| ---- | ------ | ------------------------------ |
| `CONTRIBUTING.md` | 必须 | 环境准备、分支命名、提交格式、PR 自查（关联 Issue、测试证据）、本地验证命令 |
| `SECURITY.md` | 必须 | 私有上报渠道（邮箱或私有通道占位符）、**禁止公开提 Issue 披露漏洞**、确认响应 SLA 占位符（如 5 个工作日） |
| `CODE_OF_CONDUCT.md` | 公开必须、私有可选 | 声明遵循 Contributor Covenant v2.1 + 举报联系方式占位符 |
| `CODEOWNERS`（放 `.github/`） | 推荐 | 至少一行：`* @owner`；多 Owner 示例：`docs/ @docs-owner`、`*.js @js-owner` |
| `CHANGELOG.md` | 推荐 | Keep a Changelog 格式：`## [Unreleased]` 起手，发版按 `## [x.y.z] - 日期` 追加 |
| Issue / PR 模板 | 推荐 | 路径 `.github/ISSUE_TEMPLATE/bug_report.md`、`feature_request.md`、`PULL_REQUEST_TEMPLATE.md`；bug 模板须含复现步骤、期望、实际、环境四栏；PR 模板须含关联 Issue、变更说明、测试证据三栏 |

---

## 隐私与安全红线（最高优先级，阻塞提交）

### 永远不得提交的内容（命中任何一条即停止）

`.env*`（`example` 除外）、`*.pem/*.p12/*.key`、`credentials.json`、含密码的数据库配置、私钥、构建产物（`dist/`、`build/`、`target/`、`__pycache__/`）、依赖目录（`node_modules/`、`.venv/`）、`*.log`、覆盖率目录、编辑器私有配置、本地证书、大体积媒体与数据库文件（`.db` 或 `.sqlite`）、压缩包与二进制（`.zip`、`.exe`、`.so`、`.dll`，例外见下）。

### 敏感信息规则（具体化）

1. 应仅提交 `.env.example`，值一律使用占位符（如 `YOUR_API_KEY_HERE`）；生产密钥应通过 CI Secrets 注入。
2. 泄露史观：**历史清除 ≠ 安全**。凡曾公开即视为泄露，必须立即吊销轮换，再用 BFG 或 `git filter-repo` 清理历史。
3. 用户要求提交二进制时，必须先询问用途：
   - 测试 fixture：单文件须小于 `1 MB`，存放于 `testdata/` 或 `fixtures/`，注释写明用途，并在 `.gitignore` 中用 `!` 显式放行。
   - 项目必需的静态资源（如 `favicon.ico`）：须体积小，并在 `.gitignore` 中用 `!` 显式放行。
   - 预编译工具：应在 `README.md` 中写明来源与 SHA256 校验和。
   - 大于 `10 MB` 的文件或发布产物：一律通过 GitHub Releases、LFS 或制品仓库分发，不得进入 git。
4. 对于可疑独立文件（含有大量公网 IP、非知名域名或客户数据样貌），一律不得主动 `git add`，应先警告用户。

### 改造审计命令（逐条执行，有命中先修复再补充文件）

> 以下管道适用于 **Git Bash**；PowerShell 下 `sort` 为别名、`head` 与 `grep` 不可用，等价写法：`... | Sort-Object -Descending { $_.Split()[2] } | Select-Object -First 20`、`git diff --cached | Select-String -Pattern 'password|secret|token' -CaseSensitive:$false`。

```bash
gitleaks detect --source .                                    # 密钥扫描（无工具则先装）
git rev-list --objects --all | git cat-file --batch-check | sort -k3nr | head -20   # 大文件排行
git log --all -p -S 'password|api_key|secret' --pickaxe-regex  # 历史密钥痕迹
git ls-files --ignored --exclude-standard                     # 应忽略却被追踪的文件
```

---

## 提交与分支（封闭枚举与受保护分支）

### Conventional Commits：格式 `<type>(<scope>): <subject>`

- `type` 封闭枚举：`feat fix docs refactor test chore ci perf revert`。禁止 `update misc fix stuff` 等模糊词。
- `scope` 为可选，须使用 kebab-case 小写；`subject` 须使用祈使语气、不超过 `72` 字符，且不以句号结尾。
- 破坏性变更应在 footer 中写明 `BREAKING CHANGE:`。
- 本地校验：`npx commitlint --from HEAD~1 --to HEAD`（或接入 commitlint hook 后直接提交验证）。

### 分支策略（保护规则固定）

- `main` 分支须保持常绿：禁止直接 push；PR 至少需要 1 人批准；CI 全绿方可合并；合并方式为 **Squash Merge**；发版须打 `v<MAJOR>.<MINOR>.<PATCH>` tag。
- 分支名须全小写并使用连字符：`feature/<issue-id>-short-desc`、`fix/<issue-id>-short-desc`、`hotfix/<desc>`。
- `hotfix` 分支应从 `main` 切出，合并回 `main`（需同步 `develop` 的仓库应一并合并）。

---

## 质量门禁（按语言栈二选一，不得堆叠）

### Hooks：JS 仓库用 Husky，非 JS 仓库用 pre-commit

- JS 仓库应使用 Husky、lint-staged 与 commitlint。`lint-staged` 只跑暂存文件：

```json
{ "lint-staged": { "*.{js,ts}": ["eslint --fix", "prettier --check"] } }
```

- 非 JS 或多语言仓库应使用 `pre-commit` 框架统一管理（含 gitleaks hook），不得为每种语言各安装一套 hook runner。
- `.commitlintrc` 最小配置：应继承 `@commitlint/config-conventional`，`type-enum` 须与上节枚举一致。

### CI 与依赖（最小可用即达标）

- `.github/workflows/ci.yml` 必须在 push/PR 触发 **lint、test 与 build** 三件套；缺任何一件视为未达标。
- `.github/dependabot.yml` 最小配置须包含 `schedule.interval: weekly` 与生态选择（npm、pip、go 或 cargo）。
- 各语言漏洞检查进 CI，应四选一按栈接入：`npm audit`、`pip-audit`、`govulncheck ./...`、`cargo audit`。
- Linter 选型应按栈对照下表：JS 使用 `ESLint` 与 `Prettier`、Python 使用 `Ruff`（lint 与 format 二合一）、Go 使用 `golangci-lint` 与 `gofmt`、Rust 使用 `Clippy` 与 `rustfmt`、Shell 使用 `ShellCheck` 与 `shfmt`。单仓库仅配置命中的栈，不得全表照抄。

---

## AI Agent 操作约束

1. **禁止硬编码**任何密钥、Token、密码或 API Key；禁止生成或覆盖 `.env`（仅允许读写 `.env.example`）。
2. **禁止修改**：`LICENSE`、`SECURITY.md`、发布流水线、`*.lock`（依赖升级除外，但须经用户明确要求）。
3. **先搜后建**：新增工具函数前，应先 grep 仓库既有实现，禁止重复实现已有功能。
4. **批量修改阈值**：一次改动超过 `3` 个文件时，应先用一句话说明变更范围再执行。
5. **新功能带测试**：无测试用例的新功能视为未完成。
6. **暂存审查**：`git add` 应仅点名本次任务文件；提交前应复核 `git diff --cached --stat`，无关文件应移出暂存。

---

## 提交前验证协议（每次建议提交前必跑）

1. `git status --short` + `git diff --cached --stat`：确认仅含本次任务文件，无 `.env` / 密钥 / 二进制混入。
2. 密钥扫描：`gitleaks detect --source .`（无工具时至少执行 `git diff --cached | grep -nEi 'password|passwd|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY'`）。
3. 规范检查：提交信息须通过 commitlint 校验；分支名须全小写并使用连字符；CHANGELOG 须有未发布条目（如本次含用户可见变更）。
4. 门禁：对应语言的 lint 与 test 须本地通过（或确认 CI 会跑）。
5. 红线复核：`git commit/push` 必须经用户明确指示方可执行；超过 `100 KB` 的数据文件改动须有正当理由，并向用户说明。
