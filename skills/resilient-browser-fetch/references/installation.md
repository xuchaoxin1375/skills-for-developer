# 安装与 Agent 集成

本 Skill 的安装分为两部分：

1. 将 Skill 目录放入 Agent 能发现的 skills 目录。
2. 在实际执行 Python 的 Conda/venv 环境中安装 Scrapling 和浏览器依赖。

Agent 只负责读取 `SKILL.md`，不会替代 Python 包或浏览器安装。建议优先使用目录链接，便于更新本地 Skill；不支持链接时再复制目录。不要把 `.venv`、`__pycache__`、`.pytest_cache`、profile 或真实抓取输出复制到 Agent 的 skills 目录。

## 目录变量

Linux/macOS：

```bash
export SKILL_DIR="$HOME/.codex/skills/resilient-browser-fetch"
```

Windows PowerShell：

```powershell
$SkillDir = Join-Path $HOME ".codex\skills\resilient-browser-fetch"
```

如果当前 Skill 位于其他工作区，将 `SKILL_DIR` 或 `$SkillDir` 改为实际目录。以下命令假定源目录已经存在。

## Codex CLI

Codex 从 `$CODEX_HOME/skills` 发现 Skill；未设置 `CODEX_HOME` 时通常使用 `~/.codex/skills`。本技能已经位于当前 Codex skills 目录时无需复制，启动新会话后即可使用：

```bash
ls "$HOME/.codex/skills/resilient-browser-fetch/SKILL.md"
```

若源目录在其他位置，Linux/macOS 可以创建目录链接：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$SKILL_DIR" "${CODEX_HOME:-$HOME/.codex}/skills/resilient-browser-fetch"
```

Windows PowerShell 使用目录 Junction：

```powershell
$CodexSkills = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME "skills"
} else {
    Join-Path $HOME ".codex\skills"
}
New-Item -ItemType Directory -Force -Path $CodexSkills | Out-Null
New-Item -ItemType Junction `
  -Path (Join-Path $CodexSkills "resilient-browser-fetch") `
  -Target $SkillDir
```

已有同名目录时，先确认它确实指向本 Skill；不要盲目覆盖用户目录。

参考：[OpenAI Codex Skills](https://developers.openai.com/codex/skills/)。

## Claude Code

Claude Code 支持个人、项目和插件三个层级。个人安装对所有项目生效，项目安装应提交到项目版本库：

Linux/macOS：

```bash
mkdir -p "$HOME/.claude/skills"
ln -sfn "$SKILL_DIR" "$HOME/.claude/skills/resilient-browser-fetch"
```

Windows PowerShell：

```powershell
$ClaudeSkills = Join-Path $HOME ".claude\skills"
New-Item -ItemType Directory -Force -Path $ClaudeSkills | Out-Null
New-Item -ItemType Junction `
  -Path (Join-Path $ClaudeSkills "resilient-browser-fetch") `
  -Target $SkillDir
```

项目级安装则把目录链接或复制目录放在：

```text
<project>/.claude/skills/resilient-browser-fetch/SKILL.md
```

启动 Claude Code 后使用 `/skills` 检查发现结果。插件安装应由插件自己的 `plugin.json` 管理，不要把插件目录和个人 Skill 目录混用。

参考：[Claude Code Skills](https://docs.anthropic.com/en/docs/claude-code/skills)。

## Cursor

Cursor 支持全局和项目 Skill：

```text
全局：~/.cursor/skills/resilient-browser-fetch/SKILL.md
项目：<project>/.cursor/skills/resilient-browser-fetch/SKILL.md
兼容目录：~/.agents/skills/ 或 <project>/.agents/skills/
```

全局目录可以使用同样的符号链接或 Junction 命令，将目标改成 `$HOME/.cursor/skills`。项目级 Skill 适合随代码库版本控制；全局 Skill 适合个人工具和跨项目复用。安装后在 Cursor 的 Customize → Skills 中检查是否已发现。

参考：[Cursor Agent Skills](https://cursor.com/docs/skills)。

## Gemini CLI

Gemini CLI 支持用户级和 workspace 级目录，也提供官方管理命令。推荐使用 `link`，这样源目录更新后无需重复复制：

```bash
gemini skills link "$SKILL_DIR" --scope user
gemini skills list --all
```

项目级安装：

```bash
gemini skills link "$SKILL_DIR" --scope workspace
```

如果使用已发布的 Git 仓库，也可以：

```bash
gemini skills install https://github.com/<owner>/<repo>.git --consent
```

Gemini 的默认发现位置是：

```text
用户级：~/.gemini/skills/ 或 ~/.agents/skills/
项目级：.gemini/skills/ 或 .agents/skills/
```

参考：[Gemini CLI Agent Skills](https://geminicli.com/docs/cli/skills/)。

## 其他兼容 Agent

许多遵循 Agent Skills 开放目录约定的工具会读取以下位置之一：

```text
项目：.agents/skills/resilient-browser-fetch/SKILL.md
用户：~/.agents/skills/resilient-browser-fetch/SKILL.md
```

具体工具如果同时提供官方 `skills link`、插件市场或配置项，应优先使用官方入口，不要假定所有 Agent 都支持同一目录、同一命令或同一 frontmatter 扩展。

## 安装 Python 与浏览器依赖

先选择实际运行脚本的环境。Conda 环境示例：

Windows PowerShell：

```powershell
$Python = (conda run -n scrapling python -c "import sys; print(sys.executable)" | Select-Object -Last 1).Trim()
uv pip install --python $Python -r (Join-Path $SkillDir "requirements.txt")
conda run -n scrapling scrapling install
conda run -n scrapling python (Join-Path $SkillDir "scripts\check_environment.py") --proxy "http://127.0.0.1:7897"
```

Linux/macOS：

```bash
PYTHON="$(conda run -n scrapling python -c 'import sys; print(sys.executable)')"
uv pip install --python "$PYTHON" -r "$SKILL_DIR/requirements.txt"
conda run -n scrapling scrapling install
conda run -n scrapling python "$SKILL_DIR/scripts/check_environment.py" --proxy 'http://127.0.0.1:7897'
```

没有 Conda 时，将 `<目标环境解释器>` 替换为 `.venv/bin/python` 或 Windows 的 `.venv\Scripts\python.exe`。没有 `uv` 时，在同一环境中使用 `python -m pip install -r requirements.txt`。

只有需要 CloakBrowser 回退时才安装可选依赖：

```bash
uv pip install --python <目标环境解释器> -r "$SKILL_DIR/requirements-cloak.txt"
<目标环境解释器> -m cloakbrowser install
```

开发或修改本 Skill 时，额外安装 `requirements-dev.txt`，并运行 Ruff、Pyright 和 pytest；仅使用 Skill 时不需要开发依赖。

## 验证与更新

安装后验证三层：

1. Agent 能发现 `SKILL.md`。
2. 目标 Python 环境能导入 Scrapling，浏览器诊断通过。
3. 实际调用脚本或模块成功返回结构化结果。

更新源码时，链接安装会自动看到变化；复制安装需要重新复制 Skill 目录。更新依赖或浏览器版本后，重新运行环境诊断和最小 smoke test。不要把真实 profile 当作源码同步目录，也不要在多个浏览器进程之间共享同一个持久 profile。
