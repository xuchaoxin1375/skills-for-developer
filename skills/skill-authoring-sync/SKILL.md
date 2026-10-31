---
name: skill-authoring-sync
description: >
  在 agent harness 中新建自定义 skill 并同步到真源仓库集中管理：skill 真源提交、治理规则的定义与修改，
  以及把本机 harness 配置偏好（如 OpenCode TUI `cli.json`）回写真源、按真源恢复本机配置。
  当用户要求新建 skill、判断是否值得新建 skill、把 skill 安装到 harness、说“同步配置”“同步 opencode 设置/偏好”，
  或复盘/同步/分发/校验/查变更已有 skill，以及需要定位真源仓库、避免在任意目录全盘搜索时使用此 Skill。
---

# Skill 新建与真源同步规范

你是负责 skill 全生命周期的工程师：新建、评审、分发、同步，所有操作可审计、可回放。

**核心原则：真源唯一、无副本**。实体只存真源仓库
`skills-for-developer/skills/<skill-name>/`；各 harness 侧一律放
**链接**（Windows Junction、Linux symlink），不存实体。任何修改直接改真源，
改完即对本机所有 harness 生效；跨机器靠 `git push/pull` 同步实体，
每台机器跑一遍自己平台的链接脚本即可。

## 定位真源仓库

在任意目录工作时，按下列顺序查找，命中即停，不做全盘 `find` 或逐级向上遍历：

1. **当前目录**：同时存在 `skills/` 与 `scripts/link-skills.ps1`（Linux 为 `scripts/link-skills.sh`），即真源根。
2. **本机惯例克隆位置**（分发默认约定，实际以本机克隆为准）：
   - Windows：`C:\repos\skills-for-developer`
   - WSL / Linux / macOS：`~/repos/skills-for-developer`
3. **仍未命中**：只在用户主目录及各盘 `repos` 类目录的两层内做有界搜索，或直接向用户询问路径；不扫描全盘、不反复猜测。

Windows 与 WSL/Linux 各用自己的克隆：WSL 内用 `~/repos/...`，不要把 `/mnt/c/...` 下的 Windows 克隆当作 Linux 真源，链接类型随宿主平台选择（Windows Junction / Linux symlink）。

**适用范围**：各 agent harness（OpenCode / Codex / Claude / Agents 通用 / dsh）的自定义 skill，
以及 harness 侧配置偏好（如 OpenCode TUI `cli.json`、全局 `AGENTS.md`）的真源同步。
本仓库的 OpenCode 插件（`plugins/`）同样走真源唯一与链接分发，细则见[插件制品](../../docs/plugins.md)。
分发与校验统一走仓库 `scripts/` 下的链接脚本，不手写零散命令。

维护本仓库先读 [治理规范](references/skill-governance.md)；职责设计、正文约束与语言风格按 [内容与语言规范](references/skill-content-guidelines.md)。本 skill 继续维护真源、路径、索引和分发规则，不另复制写作规范；新建前核对邻近能力，适合扩展已有 skill 时不强行新建。

写 skill 正文、全局 `AGENTS.md` 或任何被指针引用的文档时，按需读 [面向代理的文档写作](references/writing-for-agents.md)：指针措辞、信息层级、主词、完成标准与修剪。

---

## 目录与命名约定

真源布局（一个 skill 一个目录）：

```text
skills-for-developer/
  skills/
    <skill-name>/
      SKILL.md                 # 必需：frontmatter + 正文
      references/              # 可选：执行所需的详细规则与示例
      scripts/                 # 可选：配套脚本
  plugins/
    <plugin-name>/             # OpenCode 插件真源：入口 index.ts 必须在包根目录
  scripts/
    link-skills.ps1            # Windows：创建 / 校验 / 移除 Junction（幂等）
    link-skills.sh             # Linux/macOS：创建 / 校验 / 移除 symlink（幂等）
    link-plugins.ps1           # Windows：把 plugins/ 链到 ~/.config/opencode/plugins（幂等）
    link-plugins.sh            # Linux/macOS：同上（symlink）
```

- 必须：`<skill-name>` 使用 kebab-case 小写英文（如 `scripting-best-practices`）。
- 推荐：名称简短、易理解，不把职责全称堆进名字；可用 `app` 等常见缩写，避免难懂的自造缩写。详细职责写入 description。
- 必须：`SKILL.md` 以 frontmatter 开头，含 `name`（与目录名一致）与
  `description`（写清触发条件：什么请求下加载本 skill）。
- 必须：新增/修改 skill 时同步更新仓库 `README.md` 的“Skill 目录”检索表，
  两处语义保持一致。
- 推荐：正文按“适用范围 → 工作流程 → 约束/规范 → 自检 → 验证协议”组织；
  正文即工件，不套嵌套代码围栏，不夹带安装教程与链接聚合。
- 材料保留按[内容与语言规范](references/skill-content-guidelines.md#正文与参考的组织)处理；从本地资料或项目提取时，不默认复制原材料或保存来源与指纹。执行确需的外部资源按实际依赖及许可要求决定归档或引用。

各 harness 的 skill 发现差异（如 dsh 的 rank、单层扫描、kebab 严格校验）见
`references/dsh-skills.md`，写 skill 时遵守即可。

## 工作流程

### 新增 skill

1. **确认需求**：skill 名称、description 触发条件、适用范围与例外；全新编写还是从现有文档改造。新建前先答三问：相邻 skill 是否已覆盖同一输入、决策与产物（能修现有就不新建）？新能力是否长期独立复用，而不是单次任务或项目专值？触发面、正文、references 与分发的维护成本由谁承担、是否值得？答案写进提交说明。
2. **写真源**：在 `skills/` 下新建目录 + `SKILL.md`，目录须含 `SKILL.md`
  （链接脚本只处理含 `SKILL.md` 的目录，缺失者警告跳过）。
3. **更新索引**：在仓库 `README.md` “Skill 目录”表追加一行（一句话说明 + 关键词）。
4. **本机分发**：Windows 跑 `scripts\link-skills.ps1`（可先 `-VerifyOnly` 预检，
   可用 `-Include <name>` 只处理新 skill）；Linux 跑 `./scripts/link-skills.sh`。
   如 skill 需外部依赖或提供 CLI 命令：将其加入 `config/recommended-skills.txt`
   （仅限本仓库自定义 skill；第三方走 `config/third-party-skills.txt`），
   并在链接脚本的命令登记分支补入口（sh 的 `skill_command_name` /
   `skill_command_entry`，ps1 的 `Get-SkillCommandName` /
   `Get-SkillCommandEntry`）；部署时会自动推荐安装依赖、默认装成命令。
   部署结束时链接脚本还会检测推荐工具 git、ripgrep、fd、Playwright、Scrapling 是否可用，缺失只提示安装命令（推荐项，不阻断）。
5. **验证同步**：链接脚本全量 `-VerifyOnly` 通过；skill 在 harness 可见/可加载。
6. **跨机器**：`git push` 推实体；其他机器 `pull` 后跑一遍自己平台的链接脚本。
   **不要把链接本体提交到 git**。

### 修改 skill

直接改真源实体，改完即对本机所有 harness 生效，无需重新链接；
跨机器用 `git push/pull` 同步。改后同步更新 `README.md` 检索表（如语义变化）。
触发描述改动按 [触发评测](references/trigger-eval.md) 跑最小对照，并同步 description 与 README 行。

- 推荐：触发不准（该加载没加载、或误加载）时，按[触发描述维护](../../docs/skill-authoring-workflow.md#触发描述维护推荐)做一次改前/改后最小对照，再同时改 `description` 与检索表；不靠改正文规则代偿触发。
- 必须：用户提及 skill 变更/改动时，先定位真源再查改动：在真源内用 `git status --short`、`git log --oneline -N`、`git diff` 核对实体改动，不得以 harness 侧目录时间判定。例：查近期改动先跑状态与差异，再按名加载对应正文。
- 必须：`skills/user-profile/` 只在用户明确要求改它时才动；它只存最常用最重要的常驻默认值，保持简洁。用户的其他长期偏好写进全局 `AGENTS.md`（真源 `config/global-AGENTS.md`），域规则写进对应 skill 正文，不往 user-profile 堆。
- 必须：全局 `AGENTS.md` 只放简短指针与最高层默认值，可展开的机制、清单与判据下沉对应自定义 skill；第三方 skill 由调用方编排，不在其正文里追加本仓库规则。

### 子模块中的 skill

`skills/<name>/` 可能是 git submodule（`git submodule status` 可见）。改动要在子仓库完成并推送，再更新主仓库指针：

1. 在子模块内提交并推送。detached HEAD 时用 `git push origin HEAD:<branch>`，不要依赖本地陈旧分支。
2. 回到主仓库 `git add skills/<name>` 更新指针，与相关描述、README 改动一起提交。
3. 推送主仓库后确认 `git submodule status` 无 `+`/`-` 前缀。

### 第三方 skill 推荐名单

`skills/` 只收本仓库自定义真源。第三方 skill 登记在 `config/third-party-skills.txt`，
实体不入库，也不在仓库内建指向上游的链接。

- 每行 `name | repo | kind | ref | preserve | description`；名称不得与自定义 skill 重名，
  `ref` 推荐固定到 tag，`branch` 只用于有意跟踪上游。
- 部署由链接脚本询问，默认 **No**；非交互用 `-ApplyThirdPartySkills` /
  `--apply-third-party-skills`，同步版本用 `-SyncThirdPartySkills` / `--sync-third-party-skills`。
- 安装器 `scripts/third-party-skills.py` 把实体放到独立共享根目录
  `$THIRD_PARTY_SKILLS_HOME/<name>`（默认 `~/.local/share/skills-for-developer/third-party/<name>`），
  各已登记的 harness 目录都建链接；升级时保留 `preserve` 列出的本地文件（如 `.env`、`runtime.conf`）。
  第三方共享根目录与自定义真源 `skills/` 分离，不占用任何 harness 的 skills 目录；默认不放仓库内，
  避免 `git clean` 误删 `.env`，需要时用 `THIRD_PARTY_SKILLS_HOME` 指向仓库内的 `third-party/`
  （`.gitignore` 已预留）。
- 用户要求“同步第三方 skill”时，先核对或更新名单 `ref`，再运行 sync；不要手工把上游实体
  复制进 harness 目录，也不要把它加入 `config/recommended-skills.txt`。

### OpenCode 插件

插件真源在 `plugins/<name>/`，只对 OpenCode 生效，不进各 harness 的 skills 目录。

1. 目录内必须有**包根目录的 `index.ts`**：OpenCode V2 对本地目录插件只认这个入口，
   `package.json` 的 `exports` / `main` 不被采纳；入口放 `src/` 会被**静默跳过**。
2. 不依赖 `@opencode/plugin` 的运行时解析：直接导出 `{ id, setup }` 纯对象最稳。
3. 分发：`scripts/link-plugins.ps1`（Windows）/ `scripts/link-plugins.sh`（Linux）建链接到
   `~/.config/opencode/plugins/<name>`，OpenCode 自动发现该目录下的插件包。
4. 验证：插件自带测试通过 + 服务端日志出现 `loading plugin` + 一次真实调用对照。
   **装载失败只写日志、不在界面报错**，只看界面会误判成"插件没生效"。

装载规则、失败排查与"插件 vs skill"分工见[插件制品](../../docs/plugins.md)。

### 跨机器同步与对齐判定

用户说“同步 skills”时，先把本地工作区状态和远端真实状态分开验证。`git status -sb` 只比较 `HEAD` 与本地缓存的 `refs/remotes/<remote>/<branch>`；该缓存可能早已过期，不能单独证明远端已对齐。

1. **列远端**：`git remote -v`。不要假定只有 `origin`；有镜像时以提交历史更全的一侧为准，必要时分别核对。
2. **直接问远端**：`git ls-remote <remote> refs/heads/<branch>`，记录远端 commit。未 fetch 也能得到远端真实 SHA。
3. **取回并比较**：`git fetch <remote> <branch>`，再运行
   `git rev-list --left-right --count HEAD...<remote>/<branch>`。
   输出为 `<ahead> <behind>`；两者都为 `0` 才算对齐。
4. **按结果处理**：
   - `behind > 0`、`ahead = 0`：先处理工作区未提交改动（提交或 stash），再 `git pull --ff-only`（或 `git merge --ff-only <remote>/<branch>`）后复跑第 3 步。
   - `ahead > 0`、`behind = 0`：本地有未推送提交；默认直接 push（多远端逐个推），push 后重新 fetch 核对；推送失败（无凭据、网络、非快进、远端拒绝）就跳过并如实报告，不改用 `--force`。网络原因（超时、连接被断、SSH 22 不通）先按 `network-access` 的 Git 客户端路线换路重试一次，仍失败再跳过。
   - 双向非零：先报告分叉点和双方提交，不擅自 merge/rebase。
5. **报告核验事实**：写明 remote、branch、远端 SHA、本地 HEAD、ahead/behind，以及是否实际执行过 fetch。ahead/behind 只描述提交历史；工作区有未提交改动时另用 `git status --short` 说明，不能把它算作已同步。不要用 `git status -sb` 的 `up to date` 代替远端结论；远端不可达时明确说“未能验证远端”。涉及远端操作时写明实际通道（直连、代理或镜像）。

### 删除 skill

1. 先运行链接脚本 `-Unlink` / `--unlink`（或手工删各 harness 下对应链接），再删仓库目录。
2. 必须：删链接只删链接不删实体——Windows 用 `Remove-Item <junction>`
  （不要加 `-Recurse`），Linux 用 `rm <symlink>`（不要加 `-r`，路径末尾不要加 `/`）。

### 评估过程产物

skill-creator 评估循环的过程产物（`outputs/`、`benchmark.json`、`review.html`
等 `*-workspace/` 目录）**禁止**放入 `skills/` 下：链接脚本只处理含
`SKILL.md` 的目录，无 `SKILL.md` 者每次运行告警；且过程产物不是 skill 实体，
不许进入真源 git 同步。

统一放仓库根 `.workspaces/<skill-name>-workspace/`（已在 `.gitignore` 忽略，
本地独占、不提交、不跨机器同步）。留到 skill 稳定作为回归基线（改 skill 时
以前次输出为 baseline 跑下一 iteration），结论过时后整目录删除。

### 副本漂移处理

harness 侧出现**实体目录**（非链接）即视为漂移：链接脚本会自动将其备份到
`~/.skills-migration-backup/<时间戳>/<harness>/<name>`（备份移出 skills 目录，
避免被 harness 误扫为重复 skill），再替换为正确链接。备份确认无误后手工删除。
备份目录永不纳入版本控制。

**悬空链接**（指向本仓库、目标已不存在）同样由链接脚本处理：skill 重命名或删除后，
下次全量运行会移除旧链接，`-VerifyOnly` / `--verify-only` 把它计为异常并提示重跑；
`check-skills.py` 报为 ERROR。只清理指向本仓库的链接，`--include` 时限于名单内的名字，
指向别处的链接与 harness 自带内容不动，不需要手工逐个删除。

### 同步 harness 配置偏好（本机 → 真源）

用户说“同步配置”“同步 opencode 设置/偏好”时，指把本机 TUI 偏好回写真源：OpenCode 侧真源是
`config/opencode/cli.json`，对应本机 `%USERPROFILE%/.config/opencode/cli.json`
（Linux `~/.config/opencode/cli.json`）；全局偏好真源是 `config/global-AGENTS.md`。
仓库 `config/` 只收非密配置；`opencode.json`（providers）与密钥（`service.json`、`auth.json`）不入库。

1. **比对**：逐字段比较本机与真源（JSON 展平后分新增 / 缺失 / 值不同三类），不只看文件是否相同。
2. **取舍**：环境相关或临时调试项留在本机；可跨机的偏好合入真源。
3. **写入**：让真源与本机字节一致（链接脚本按文件 hash 判断“已是最新”，不一致时下次部署会提示覆盖）。
4. **校验**：`python3 scripts/check-skills.py --no-harness`，以及
   `scripts\link-skills.ps1 -VerifyOnly`（Linux `./scripts/link-skills.sh --verify-only`）。
5. **报告**：列出采纳与保留项及依据；默认提交并推送，推送失败就跳过并报告。

反向分发（真源 → 本机）由链接脚本承担：`-ApplyRecommendedCli`（Linux `--apply-recommended-cli`）
应用推荐配置，覆盖前备份为同目录 `cli.json.bak-<时间戳>`；`-SkipRecommendedCli` 跳过，
非交互环境默认跳过。`-VerifyOnly` 只提示 `config/global-AGENTS.md` 漂移，不检查 `cli.json`。

## 验证协议

1. Windows：`scripts\link-skills.ps1 -VerifyOnly` 全量通过；
   Linux：`./scripts/link-skills.sh --verify-only` 全量通过。
2. 仓库侧：`python scripts/check-skills.py --no-harness --strict` 与 `python scripts/check-links.py` 通过。
3. 新 skill 在 harness 中可见/可加载（出现在可用 skill 列表即算通过；dsh 差异见 `references/dsh-skills.md`）。
4. 抽查正文：描述的触发条件在对应请求下能命中加载，含 skill 变更/查变更触发。
5. `git status` 确认无链接本体被误暂存；涉及跨机器同步时，按「跨机器同步与对齐判定」核对远端，不以 `git status -sb` 代替。
6. 查变更请求已在真源用 `git status`/`log`/`diff` 核对，未用 harness 时间判定。
7. 涉及第三方名单时，`python -X utf8 scripts/third-party-skills.py verify` 通过；
   未安装的条目只提示，不计失败。

## 红线

- 不把 harness 链接本体提交到 git；`git add` 只点名实体文件。
- 默认提交并推送（多远端逐个推）；推送失败（无凭据、网络、非快进、远端拒绝）就跳过并如实报告，不擅自 `--force`、不改写已推送历史。
- 不在 harness 侧手工存放实体副本；所有改动走“真源 → 链接生效”单向流动。
- skill 正文、引用、示例、配套脚本中不得出现仓库外真实路径（本机绝对路径如 `C:\Users\…`、`C:\tools\…`、`/home/…`，写死的 `/tmp/…`）：真实引用只许仓库内相对路径或 URL；示例路径必须用 `<…>` 占位符；约定俗成的标准位置须用环境变量形式（如 `%USERPROFILE%`、`$HOME`、`$XDG_RUNTIME_DIR`）而非写死；本文「定位真源仓库」记录的 `C:\repos\skills-for-developer` 与 `~/repos/skills-for-developer` 属分发约定位置，不视为个人机器路径；历史/迁移说明中提及的已删除旧路径须标注“旧/已删除”。
