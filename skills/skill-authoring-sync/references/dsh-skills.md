# dsh skill 发现规则备忘

dsh 侧行为以 dsh 官方 Skill System / dsh-skill-filesystem 文档为准，这里只记写 skill 时必须遵守的约束。

## 根目录与优先级

| Rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<projectRoot>/.dsh/skills`（projectRoot 取最近含 `.git` 的祖先，无则取 cwd） |
| 200 | project-agents | `<projectRoot>/.agents/skills` |
| 300 | custom | `Config.customSkillDirs` |
| 400 | user-dsh | `<dshHome>/skills`（`$DSH_HOME`，默认 `~/.dsh`） |
| 500 | user-agents | `<agentsHome>/skills`（`$DSH_AGENTS_HOME`，默认 `~/.agents`） |

本仓库链接脚本默认分发用户级两处（400 + 500），项目级按需由各仓库自行处理。
user-dsh 根跳过 `.system` 子目录；`watchFollowSymlinks` 默认 `true`，
Windows Junction 与 Linux symlink 均可被跟随。

## 格式约束

- 只扫描单层：`<root>/<name>/SKILL.md` 或扁平 `<root>/<name>.md`，嵌套 `**/SKILL.md` 不发现。
- frontmatter 必含 `name` 与 `description`；`name` 须为 kebab（`/^[a-z0-9]+(-[a-z0-9]+)*$/`），且与目录名一致。
- 可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`；
  后两键只接受 YAML 布尔值及不区分大小写的 `true/false/yes/no/on/off/1/0`，
  拼写错或非布尔值则整个 skill 告警丢弃（fail-closed），缺 `name`/`description` 同理。
  无调用键时默认模型侧与用户侧均允许。
- 目录与正文生命周期分离：每次加载重读当前文件正文；frontmatter 编辑与增删改名触发目录刷新，
  bundle 内 `references/`、`scripts/`、`assets/` 编辑不触发。

## 核对

- 无效 skill 只告警跳过，目录中无法区分“缺失”与“无效”，报错先查 frontmatter 拼写与 kebab。
- 会话日志核对：`zstdcat ~/.dsh/sessions/*/*/session*.jsonl.zstd | grep -E "skills" | head`
