## 上游 skill：安装与本地协作

第三方 skill 保持上游原样，不在 `skills/` 保存同名适配版，不修改其 description、调用元数据、正文、引用或脚本。重合处调整本地自有 skill 的职责与调用；上游缺陷可反馈或暂不采用，不静默打补丁。

### 已选入口

来源为 [mattpocock/skills](https://github.com/mattpocock/skills)。版本与精选目录由 [路径配置](../config/upstream-skills.json)唯一维护，实体是被忽略的独立 Git clone，不是本仓库 submodule。

| Skill | 上游调用类型 | 用途 |
|---|---|---|
| `grill-me` | 用户入口 | 显式启动 `grilling`，先讨论方案 |
| `grill-with-docs` | 用户入口 | 显式组合 `grilling` 与 `domain-modeling`，边讨论边记录 |
| `grilling` | 方法 | 按设计树逐轮澄清方案与取舍 |
| `domain-modeling` | 方法 | 澄清业务概念、维护术语表与必要 ADR |
| `codebase-design` | 方法 | 深模块、接口与测试边界的设计语言 |
| `code-review` | 方法 | 对固定起点到 HEAD 的提交差异做规范/规格分轴评审 |
| `diagnosing-bugs` | 方法 | 用反馈回路、最小化和可证伪假设定位难 bug |
| `tdd` | 方法 | 红—绿—重构的小步测试驱动开发 |

`tdd` 已从原先的独立 CLI 安装迁入同一 clone，迁移前四个文件与选定上游版本逐字节一致，没有改写或升级内容。`to-spec`、`to-tickets`、`implement-spec` 等未纳入本组；依赖提示不等于获准安装整包、配置工单系统或启动外部操作。

### 现成 CLI 与 clone 两种方式

现成 [skills CLI](https://github.com/vercel-labs/skills) 支持按名安装，不必安装整包：

```bash
npx skills add mattpocock/skills --skill grill-me -g -a opencode claude-code codex -y
```

但不要对**本机已由 clone+链接管理的同名 skill**再次运行安装命令，否则会重新制造实体或覆盖链接。CLI 适用于独立试用或选定另一管理方式，不与 clone 分发同时接管。旧 `third-party-skills.py` 名单也不重复登记本组。

本组最终采用 **clone + 精选链接**：

- 上游实体：`third-party/mattpocock-skills/`，由 `.gitignore` 忽略；不要对它运行 `git clean -xdf`。
- 来源、固定提交与精选源目录：`config/upstream-skills.json`；只登记要暴露的 skill，不链接整库。
- 分发：`scripts/link-upstream-skills.py` 复用现有链接工具的 Junction/symlink 与备份机制，不联网、不 clone、不更新源码。
- 现有 `link-skills.ps1` / `link-skills.sh` 也会调用它，沿用 Include 与 VerifyOnly 筛选；SkipThirdPartySkills 会跳过。原有 Unlink 仍只处理自有 skill，本组用下面的独立 unlink 命令。
- 默认创建缺失链接，冲突时报错；`--replace` 才会迁移冲突链接/实体，实体先备份。校验会拒绝提交、来源或精选 skill 内容漂移。

### 新机恢复与更新

先按 `network-access` 选择本机可用路线，然后在仓库根执行：

```bash
git clone -c core.autocrlf=false -c core.symlinks=false https://github.com/mattpocock/skills.git third-party/mattpocock-skills
git -C third-party/mattpocock-skills checkout --detach <config中的revision>
python -X utf8 scripts/link-upstream-skills.py
python -X utf8 scripts/link-upstream-skills.py --verify-only
```

`core.symlinks=false` 只用于避免上游仓库自带的分发链接在 Windows checkout 时失败；实际分发仍由本地工具创建 Junction/symlink。已有 clone 不重跑 clone；浅克隆缺少目标提交时先有界 fetch 指定提交。尚未安装且没有同名链接时，缺少 clone 只报告可选项，不能称已安装；已有链接而 clone 丢失则校验失败，先恢复 clone。

更新时先检查 clone 的 `git status`，发现本地改动先备份并迁出，不能自动 merge 到上游。fetch 后审阅精选 skill 的变化，确认采用的新提交，再切换 clone 并更新配置中的 revision，重跑链接校验；不能只移动源码版本却不更新配置。链接会实时读取源文件，切换期间避免让活跃任务混用两版。

不再需要时运行 `python -X utf8 scripts/link-upstream-skills.py --unlink`，只移除本工具的直接链接，保留 clone；更多筛选与迁移选项以 `--help` 为准。

### 本地规则归属

- 上游访谈与领域建模方法不在本地复制。已有规格与术语先复用；只讨论不默认改代码，写入范围依用户请求确定。
- 工程约束与可选 ADR 结构由 `swe-gov` 维护；文档规划由 `project-docs` 维护。上游简短 ADR 模板不是缺陷，不强制替换为本地完整模板。
- 测试覆盖、替身与真实集成的证明范围由 `web-app-testing` 维护；不能因接口测试新增就未经覆盖核对删除旧用例。
- 上游 `code-review` 的提交范围不覆盖全部工作区，本地调用方按 [差异快照](../skills/ai-verified-delivery/references/diff-scope.md)补齐并明确未执行部分；最终交付证据仍归 `ai-verified-delivery`。
- 上游委派、工具、安装和写入要求仍受有效权限与费用授权约束；缺条件时说明偏离或暂停，不修改上游来假装执行了完整流程。

### 迁移验证范围

本机曾尝试 skills CLI 1.7.4 的远端克隆、archive 与本地路径安装；最终按用户选择改为独立 clone。八个 Matt skill（含原先独立安装的 `tdd`）均已撤销 CLI 登记，统一通过同一 clone 分发，其他来源的 CLI 登记保留。迁移前的旧实体有离线备份，不参与 harness 的 skill 发现。

链接和源码检查能证明路径、版本与文件对应，不证明模型一定正确触发或完整执行上游方法。`grill-me`、`grill-with-docs` 保留仅用户调用配置，不出现在模型自动选择列表是预期；各 harness 的用户入口仍需实际交互验收。
