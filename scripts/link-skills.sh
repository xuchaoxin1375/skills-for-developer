#!/usr/bin/env bash
#
# 将本仓库 skills/ 下的每个 skill 通过 symlink 链接到各 agent harness 的 skills 目录。
# Linux/macOS 用；Windows 请用 scripts/link-skills.ps1（Junction）。
#
# 唯一真源: <repo>/skills/<name>/（内含 SKILL.md）。
# Harness 侧只放 symlink，不存实体：
#   - OpenCode : $HOME/.config/opencode/skills
#   - Codex    : $HOME/.codex/skills
#   - Claude   : $HOME/.claude/skills
#   - Agents 通用: ${DSH_AGENTS_HOME:-$HOME/.agents}/skills（Pi 等标准兼容 harness 共用）
#   - DeepSeek Harness (dsh): ${DSH_HOME:-$HOME/.dsh}/skills
#
# 幂等，可反复执行。只管理仓库中存在的 skill 名，
# 不会动 harness 自带内容（如 Codex 的 .system/、AGENTS.md）。
#
# 用法：
#   scripts/link-skills.sh                    # 全量链接（交互终端下会询问是否应用推荐 cli.json）
#   scripts/link-skills.sh --verify-only      # 只检查，不修改
#   scripts/link-skills.sh --unlink           # 移除本仓库创建的链接（实体不受影响）
#   scripts/link-skills.sh --include a,b      # 只处理部分 skill
#   scripts/link-skills.sh --apply-recommended-cli  # 直接应用推荐 cli.json，不询问
#   scripts/link-skills.sh --skip-recommended-cli   # 跳过推荐 cli.json
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
BACKUP_ROOT="$HOME/.skills-migration-backup"
TARGETS=(
  "$HOME/.config/opencode/skills"
  "$HOME/.codex/skills"
  "$HOME/.claude/skills"
  "${DSH_AGENTS_HOME:-$HOME/.agents}/skills"
  "${DSH_HOME:-$HOME/.dsh}/skills"
)

VERIFY_ONLY=0
UNLINK=0
INCLUDE=""
APPLY_RECOMMENDED=0
SKIP_RECOMMENDED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=1; shift ;;
    --unlink) UNLINK=1; shift ;;
    --apply-recommended-cli) APPLY_RECOMMENDED=1; shift ;;
    --skip-recommended-cli) SKIP_RECOMMENDED=1; shift ;;
    --include) INCLUDE="${2:-}"; shift 2 ;;
    --include=*) INCLUDE="${1#--include=}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$SKILLS_DIR" ]] || { echo "skills 目录不存在: $SKILLS_DIR" >&2; exit 1; }

# 收集含 SKILL.md 的 skill 名
mapfile -t SKILLS < <(for d in "$SKILLS_DIR"/*/; do
  [[ -f "$d/SKILL.md" ]] && basename "$d"
done)
# 提示缺 SKILL.md 的目录
for d in "$SKILLS_DIR"/*/; do
  [[ -f "$d/SKILL.md" ]] || echo "跳过 $(basename "$d")：缺少 SKILL.md" >&2
done

if [[ -n "$INCLUDE" ]]; then
  IFS=',' read -ra WANT <<< "$INCLUDE"
  FILTERED=()
  for s in "${SKILLS[@]}"; do
    for w in "${WANT[@]}"; do
      [[ "$s" == "$w" ]] && FILTERED+=("$s")
    done
  done
  SKILLS=("${FILTERED[@]}")
fi
[[ ${#SKILLS[@]} -gt 0 ]] || { echo "没有可处理的 skill。" >&2; exit 1; }

harness_tag() {
  case "$1" in
    *opencode*) echo opencode ;;
    *.codex*) echo codex ;;
    *.claude*) echo claude ;;
    *.agents*) echo agents ;;
    *.dsh*) echo dsh ;;
    *) echo other ;;
  esac
}

failures=0

for target in "${TARGETS[@]}"; do
  echo "== $target =="
  if [[ ! -d "$target" ]]; then
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "  缺失目录（VerifyOnly，不创建）: $target" >&2
      failures=$((failures + 1))
      continue
    fi
    mkdir -p "$target"
    echo "  创建目录"
  fi

  tag="$(harness_tag "$target")"
  for skill in "${SKILLS[@]}"; do
    link="$target/$skill"
    dest="$SKILLS_DIR/$skill"
    label="  [$skill]"

    if [[ $UNLINK -eq 1 ]]; then
      if [[ -L "$link" ]]; then
        cur="$(readlink "$link")"
        if [[ "$cur" == "$dest" ]]; then
          if [[ $VERIFY_ONLY -eq 1 ]]; then
            echo "$label 将被移除（VerifyOnly）"
          else
            rm "$link"
            echo "$label 已移除"
          fi
        else
          echo "$label 是指向别处的链接（$cur），不动" >&2
        fi
      else
        echo "$label 无链接，跳过"
      fi
      continue
    fi

    if [[ -L "$link" ]]; then
      cur="$(readlink "$link")"
      if [[ "$cur" == "$dest" ]]; then
        echo "$label OK"
        [[ -f "$link/SKILL.md" ]] || { echo "$label 链接存在但 SKILL.md 不可读" >&2; failures=$((failures + 1)); }
      else
        if [[ $VERIFY_ONLY -eq 1 ]]; then
          echo "$label 指向错误：$cur（期望 $dest）" >&2
          failures=$((failures + 1))
        else
          rm "$link"
          ln -s "$dest" "$link"
          echo "$label 已纠正 -> $dest"
        fi
      fi
    elif [[ -e "$link" ]]; then
      # 实体目录/文件：备份到 skills 目录之外，避免被 harness 误扫为重复 skill
      if [[ $VERIFY_ONLY -eq 1 ]]; then
        echo "$label 是实体目录/文件，需备份后替换为 symlink" >&2
        failures=$((failures + 1))
      else
        stamp="$(date +%Y%m%d-%H%M%S)"
        backup="$BACKUP_ROOT/$stamp/$tag/$skill"
        mkdir -p "$(dirname "$backup")"
        [[ -e "$backup" ]] && rm -rf "$backup"
        mv "$link" "$backup"
        ln -s "$dest" "$link"
        echo "$label 实体已备份到 $backup，链接已创建"
      fi
    else
      if [[ $VERIFY_ONLY -eq 1 ]]; then
        echo "$label 缺失（期望 -> $dest）" >&2
        failures=$((failures + 1))
      else
        ln -s "$dest" "$link"
        echo "$label 已创建 -> $dest"
      fi
    fi
  done
done

apply_recommended_cli() {
  # 推荐 cli.json：缺失或与真源不一致时，交互终端下询问是否应用；
  # 非交互环境默认跳过（用 --apply-recommended-cli 显式应用）。
  [[ $UNLINK -eq 1 || $VERIFY_ONLY -eq 1 ]] && return 0
  local repo_cli="$REPO_ROOT/config/opencode/cli.json"
  [[ -f "$repo_cli" ]] || return 0
  local dst="$HOME/.config/opencode/cli.json"
  if [[ -f "$dst" ]] && cmp -s "$repo_cli" "$dst"; then
    echo "推荐 cli.json 已是最新。"
    return 0
  fi
  if [[ $SKIP_RECOMMENDED -eq 1 ]]; then
    echo "已跳过推荐 cli.json（--skip-recommended-cli）。"
    return 0
  fi
  local do_apply=0
  if [[ $APPLY_RECOMMENDED -eq 1 ]]; then
    do_apply=1
  elif [[ -t 0 ]]; then
    local ans
    read -r -p "是否应用仓库推荐的 opencode cli.json（覆盖当前配置，原文件先备份）？[y/N] " ans
    [[ "$ans" =~ ^[yY]([eE][sS])?$ ]] && do_apply=1
  else
    echo "非交互环境，跳过推荐 cli.json（用 --apply-recommended-cli 应用）。"
    return 0
  fi
  if [[ $do_apply -eq 1 ]]; then
    mkdir -p "$(dirname "$dst")"
    if [[ -f "$dst" ]]; then
      local bak="$dst.bak-$(date +%Y%m%d-%H%M%S)"
      cp "$dst" "$bak"
      echo "原 cli.json 已备份到 $bak"
    fi
    cp "$repo_cli" "$dst"
    echo "推荐 cli.json 已应用。"
  fi
}

apply_recommended_cli

check_global_agents() {
  # 全局 AGENTS.md 漂移提示：缺失计异常，不一致只警告（手工合并，不自动覆盖）。
  [[ $VERIFY_ONLY -eq 1 ]] || return 0
  local repo_agents="$REPO_ROOT/config/global-AGENTS.md"
  [[ -f "$repo_agents" ]] || return 0
  local live="$HOME/.config/opencode/AGENTS.md"
  if [[ ! -f "$live" ]]; then
    echo "全局 AGENTS.md 缺失（期望按 README 从 config/global-AGENTS.md 恢复）" >&2
    failures=$((failures + 1))
  elif ! cmp -s "$repo_agents" "$live"; then
    echo "全局 AGENTS.md 与真源不一致，按 README 手工合并（不自动覆盖）" >&2
  else
    echo "全局 AGENTS.md 与真源一致。"
  fi
}

check_global_agents

if [[ $VERIFY_ONLY -eq 1 ]]; then
  if [[ $failures -gt 0 ]]; then
    echo "校验发现 $failures 处异常，见上。" >&2
    exit 1
  fi
  echo "全部链接正常。"
fi
