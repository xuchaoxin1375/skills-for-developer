---
name: repo-governance
description: >
  开源代码仓库的规范治理与安全提交。
  当用户要求新建开源仓库、给存量仓库补治理文件（LICENSE/README/CONTRIBUTING/CI等）、
  做提交前检查、审计历史密钥与大文件、或统一提交/分支规范时使用此 Skill。
---

# 开源仓库治理与提交规范

你是负责仓库治理的工程师：新建脚手架、存量改造、安全提交，所有操作可审计、可回放。

**适用范围**：任何语言的开源代码仓库（库 / CLI / Web / 服务）。私有仓库可剪裁：
`CODE_OF_CONDUCT` 与 `CODEOWNERS` 可选，其余照做。

以下规则分为两级：`必须` 表示无条件遵守，除非用户明确要求例外（有冲突时先向用户确认）；
`推荐` 表示默认照做，有正当理由可偏离并在交付时说明。

---

## 工作流程

接到任务先定轨道，二者顺序不同，不可混用：

1. **确认轨道与语言栈**：`新建` 还是 `改造`；主语言（决定 lint/toolchain 选型）；
   是否公开（决定社区文件是否强制）。
2. **新建轨道**：按“落地顺序”逐项建文件，每建一项即验一项。
3. **改造轨道**：先审计（密钥 / 大文件 / 行尾 / 已追踪的应忽略文件），
   修历史污染，再补文件；旧提交历史不重写风格，只从当前节点起执行新规范。
4. **提交前检查**：任何 `git add/commit/push` 建议前，先跑“提交前验证协议”。
   `git commit/push` 本身必须用户明确指示才执行。

### 落地顺序（新建与改造补文件共用）

1. `.gitattributes` → 行尾归一化提交（独立一次提交，见下）。
2. `.gitignore` → 清理已被追踪的应忽略文件。
3. `LICENSE` + `README.md`。
4. 社区文件：`CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` /
   `CODEOWNERS` / `CHANGELOG.md` / Issue-PR 模板。
5. 工具链：Linter + Formatter → hooks（Husky 或 pre-commit）→ commitlint。
6. CI（`ci.yml`）+ Dependabot + 密钥扫描。
7. `AGENTS.md`（AI 指令）最后收口。

---

## 基础文件（判定规则，而非“补上就行”）

### LICENSE：必须有，且必须选对

- 必须：仓库根有非空 `LICENSE`；缺失即视为“保留所有权利”，必须补。
- 选择规则（默认取第一条命中）：
  - 工具 / 库 / 示例项目 → **MIT**（默认）。
  - 担心专利授权、或依赖 Apache 生态 → **Apache-2.0**。
  - 用户明确要求强 copyleft → **GPLv3**；用户没说一律不选。
- 必须：填实版权持有者与年份占位符（如 `Copyright (c) 2026 <holder>`），
  不留 `YOUR NAME HERE`；`README.md` 许可证节的 SPDX 名须与 `LICENSE` 一致。

### README.md：必须含 7 节，顺序固定

`简介（一句话）→ 特性 → 快速开始 → 安装 → 用法示例 → 贡献（链到 CONTRIBUTING.md）→ 许可证（SPDX 名）`。
反模式：只有标题 + 一句“TODO” 的 README 视为缺失。

### .gitignore：基座 + 按语言追加

- 必须：任何仓库先含基座块（env / 密钥 / 系统 / 编辑器私有配置）：

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

- 再按检出的主语言追加对应块（Node 加 `node_modules/ dist/`；
  Python 加 `__pycache__/ *.py[cod] .venv/`；Go 加 `bin/`（用 `go mod vendor` 则保留 `vendor/`）；
  Rust 加 `target/`；Java 加 `*.class target/`）。单语言仓库不堆全语言模板。
- 必须：已追踪的应忽略文件须解除追踪（内容保留在本地）：

```bash
git rm --cached <file>
git rm -r --cached .
git add .
```

- 验证：`git ls-files --ignored --exclude-standard` 应无业务文件；
  `git status --porcelain --ignored` 抽查无遗漏。

### .gitattributes：模板 + 一次归一化

- 必须：根下放以下基座（Shell 强制 LF、`*.bat/*.cmd` 例外 CRLF、二进制禁转换）：

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

- 必须：加入后只做一次独立归一化提交，不与业务改动混装：

```bash
git add --renormalize .
git commit -m "chore: normalize line endings to LF"
```

- 判别：若 `git diff` 满屏而 `git diff --ignore-cr-at-eol` 干净，
  说明是行尾污染，先做归一化再谈其他改造。

### .editorconfig：基座 + 两条例外

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

例外必须记住：Markdown 行尾空格有语义不裁剪；Makefile 必须 Tab。

---

## 社区文件（公开仓库强制，私有可选）

| 文件 | 强制度 | 最小可用内容（低于此视为缺失） |
| ---- | ------ | ------------------------------ |
| `CONTRIBUTING.md` | 必须 | 环境准备、分支命名、提交格式、PR 自查（关联 Issue / 测试证据）、本地验证命令 |
| `SECURITY.md` | 必须 | 私有上报渠道（邮箱或私有通道占位符）、**禁止公开提 Issue 披露漏洞**、确认响应 SLA 占位符（如 5 个工作日） |
| `CODE_OF_CONDUCT.md` | 公开必须 / 私有可选 | 声明遵循 Contributor Covenant v2.1 + 举报联系方式占位符 |
| `CODEOWNERS`（放 `.github/`） | 推荐 | 至少一行：`* @owner`；多 Owner 示例：`docs/ @docs-owner`、`*.js @js-owner` |
| `CHANGELOG.md` | 推荐 | Keep a Changelog 格式：`## [Unreleased]` 起手，发版按 `## [x.y.z] - 日期` 追加 |
| Issue / PR 模板 | 推荐 | 路径 `.github/ISSUE_TEMPLATE/bug_report.md`、`feature_request.md`、`PULL_REQUEST_TEMPLATE.md`；bug 模板须含复现步骤 / 期望 / 实际 / 环境四栏；PR 模板须含关联 Issue / 变更说明 / 测试证据三栏 |

---

## 隐私与安全红线（最高优先级，阻塞提交）

### 永远不提交（命中即停）

`.env*`（`example` 除外）、`*.pem/*.p12/*.key`、`credentials.json`、
含密码的数据库配置、私钥、构建产物（`dist/ build/ target/ __pycache__/`）、
依赖目录（`node_modules/ .venv/`）、`*.log`、覆盖率目录、编辑器私有配置、
本地证书、大体积媒体与数据库文件（`.db/.sqlite`）、压缩包与二进制
（`.zip/.exe/.so/.dll`，例外见下）。

### 敏感信息规则（具体化）

1. 只提交 `.env.example`，值全用占位符（如 `YOUR_API_KEY_HERE`）；生产密钥走 CI Secrets。
2. 泄露史观：**历史清除 ≠ 安全**。凡曾公开即视为泄露，必须立即吊销轮换，
   再用 BFG 或 `git filter-repo` 清历史。
3. 用户要求提交二进制时须先问用途：
   - 测试 fixture：单文件 `< 1 MB`，放 `testdata/` 或 `fixtures/`，注释写用途，
     `.gitignore` 用 `!` 显式放行。
   - 项目必需静态资源（如 `favicon.ico`）：小体积 + `!` 放行。
   - 预编译工具：`README.md` 写来源 + SHA256 校验和。
   - `> 10 MB` 或发布产物：一律走 GitHub Releases / LFS / 制品仓库，不进 git。
4. 可疑独立文件（大量公网 IP、非知名域名、客户数据样貌）一律不主动 `git add`，
   先警告用户。

### 改造审计命令（逐条跑，有命中先修再补文件）

> 以下管道在 **Git Bash** 中运行；PowerShell 下 `sort` 是别名、`head/grep` 不可用，
> 等价写法：`... | Sort-Object -Descending { $_.Split()[2] } | Select-Object -First 20`、
> `git diff --cached | Select-String -Pattern 'password|secret|token' -CaseSensitive:$false`。

```bash
gitleaks detect --source .                                    # 密钥扫描（无工具则先装）
git rev-list --objects --all | git cat-file --batch-check | sort -k3nr | head -20   # 大文件排行
git log --all -p -S 'password|api_key|secret' --pickaxe-regex  # 历史密钥痕迹
git ls-files --ignored --exclude-standard                     # 应忽略却被追踪的文件
```

---

## 提交与分支（封闭枚举 + 受保护分支）

### Conventional Commits：格式 `<type>(<scope>): <subject>`

- `type` 封闭枚举：`feat fix docs refactor test chore ci perf revert`。
  禁止 `update misc fix stuff` 等模糊词。
- `scope` 可选，kebab-case 小写；`subject` 祈使语气、`≤ 72` 字符、不以句号结尾。
- 破坏性变更在 footer 写 `BREAKING CHANGE:`。
- 本地校验：`npx commitlint --from HEAD~1 --to HEAD`（或接入 commitlint hook 后直接提交试错）。

### 分支策略（保护规则写死）

- `main` 常绿：禁止直接 push；PR 至少 1 人批准；CI 全绿才能合；**Squash Merge**；
  发版打 `v<MAJOR>.<MINOR>.<PATCH>` tag。
- 分支名全小写、连字符：`feature/<issue-id>-short-desc`、
  `fix/<issue-id>-short-desc`、`hotfix/<desc>`。
- `hotfix` 从 `main` 切出，合回 `main`（需再合 `develop` 的仓库同步带上）。

---

## 质量门禁（按语言栈二选一，不堆叠）

### Hooks：JS 用 Husky，余者用 pre-commit

- JS 仓库：Husky + lint-staged + commitlint。`lint-staged` 只跑暂存文件：

```json
{ "lint-staged": { "*.{js,ts}": ["eslint --fix", "prettier --check"] } }
```

- 非 JS / 多语言仓库：用 `pre-commit` 框架统一管理（含 gitleaks hook），
  不为每种语言各装一套 hook runner。
- `.commitlintrc` 最小配置：继承 `@commitlint/config-conventional`，
  `type-enum` 与上节枚举一致。

### CI 与依赖（最小可用即达标）

- `.github/workflows/ci.yml` 必须在 push/PR 触发 **lint + test + build** 三件套；
  缺任何一件视为未达标。
- `.github/dependabot.yml` 最小：`schedule.interval: weekly` + 生态（npm / pip / go / cargo）。
- 各语言漏洞检查进 CI：`npm audit` / `pip-audit` / `govulncheck ./...` / `cargo audit`
  四选一按栈接入。
- Linter 选型按栈查表：JS `ESLint+Prettier`、Python `Ruff`（lint+format 二合一）、
  Go `golangci-lint+gofmt`、Rust `Clippy+rustfmt`、Shell `ShellCheck+shfmt`。
  单仓库只配命中栈，不全表照抄。

---

## AI Agent 操作约束

1. **禁止硬编码**任何密钥 / Token / 密码 / API Key；禁止生成或覆盖 `.env`
  （只许读写 `.env.example`）。
2. **禁止修改**：`LICENSE`、`SECURITY.md`、发布流水线、`*.lock`
   （依赖升级除外，须用户明确要求）。
3. **先搜后建**：新增工具函数前先 grep 仓库既有实现，禁止重复造轮子。
4. **批量修改阈值**：一次动 `> 3` 个文件，先一句话说明变更范围再执行。
5. **新功能带测试**：无测试用例的新功能视为未完成。
6. **暂存审查**：`git add` 只点名本次任务文件；提交前复核
   `git diff --cached --stat`，无关文件移出暂存。

---

## 提交前验证协议（每次建议提交前必跑）

1. `git status --short` + `git diff --cached --stat`：确认只含本次文件，无 `.env` / 密钥 / 二进制混入。
2. 密钥扫描：`gitleaks detect --source .`（无工具时至少跑
   `git diff --cached | grep -nEi 'password|passwd|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY'`）。
3. 规范检查：提交信息过 commitlint；分支名小写连字符；CHANGELOG 有未发布条目（如本次含用户可见变更）。
4. 门禁：对应语言 lint + test 本地通过（或确认 CI 会跑）。
5. 红线复核：`git commit/push` 必须用户明确说才执行；改动超 100 KB 数据文件须有正当理由并向用户说明。
