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
# 幂等，可反复执行。只管理仓库中存在的 skill 名，并顺手清理指向本仓库
# 但目标已不存在的悬空链接（重命名/删除 skill 的残留）；
# 不会动 harness 自带内容（如 Codex 的 .system/、AGENTS.md）。
#
# 用法：
#   scripts/link-skills.sh                    # 全量链接（交互终端下会询问是否应用推荐 cli.json
#                                             # 及推荐 skill 依赖；命令默认安装）
#   scripts/link-skills.sh --verify-only      # 只检查，不修改（含推荐 skill 依赖与命令）
#   scripts/link-skills.sh --unlink           # 移除本仓库创建的链接与命令（实体、依赖目录不受影响）
#   scripts/link-skills.sh --include a,b      # 只处理部分 skill（推荐部署同步取交集）
#   scripts/link-skills.sh --apply-recommended-cli  # 直接应用推荐 cli.json，不询问
#   scripts/link-skills.sh --skip-recommended-cli   # 跳过推荐 cli.json
#   scripts/link-skills.sh --apply-recommended-skills  # 直接安装推荐 skill 依赖，不询问
#   scripts/link-skills.sh --skip-recommended-skills   # 跳过推荐 skill 依赖与命令安装
#   scripts/link-skills.sh --apply-third-party-skills  # 安装名单中的第三方 skill，不询问
#   scripts/link-skills.sh --skip-third-party-skills   # 跳过第三方 skill 安装与校验
#   scripts/link-skills.sh --sync-third-party-skills   # 同步第三方 skill（安装缺失并更新版本）
#
# 推荐 skill（config/recommended-skills.txt，需外部依赖或命令安装的复杂 skill，
# 当前为 htmlmini）：依赖安装走询问/显式开关，命令默认装到 ~/.local/bin。
# 第三方 skill（config/third-party-skills.txt）：实体不入本仓库，交互默认 No，
# 实体放 $THIRD_PARTY_SKILLS_HOME/<name>（默认 ~/.local/share/skills-for-developer/third-party），
# 各已登记的 harness 目录都用链接指向它。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
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
APPLY_REC_SKILLS=0
SKIP_REC_SKILLS=0
APPLY_TP=0
SKIP_TP=0
SYNC_TP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=1; shift ;;
    --unlink) UNLINK=1; shift ;;
    --apply-recommended-cli) APPLY_RECOMMENDED=1; shift ;;
    --skip-recommended-cli) SKIP_RECOMMENDED=1; shift ;;
    --apply-recommended-skills) APPLY_REC_SKILLS=1; shift ;;
    --skip-recommended-skills) SKIP_REC_SKILLS=1; shift ;;
    --apply-third-party-skills) APPLY_TP=1; shift ;;
    --skip-third-party-skills) SKIP_TP=1; shift ;;
    --sync-third-party-skills) SYNC_TP=1; shift ;;
    --include) INCLUDE="${2:-}"; shift 2 ;;
    --include=*) INCLUDE="${1#--include=}"; shift ;;
    -h|--help) sed -n '2,35p' "$0"; exit 0 ;;
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

normalize_path() {
  # 词法归一化：折叠 //、/./、/../，不要求路径存在（悬空链接的目标通常不存在）
  # 用 read -a 切分，避免未加引号的路径被当作 glob 展开
  local p="$1" out="" part
  local -a parts
  IFS=/ read -r -a parts <<< "$p"
  for part in "${parts[@]}"; do
    case "$part" in
      ''|'.') ;;
      '..') out="${out%/*}" ;;
      *) out="$out/$part" ;;
    esac
  done
  printf '%s\n' "${out:-/}"
}

clean_stale_links() {
  # 清理指向本仓库 skills/ 但目标已不存在的悬空链接：
  # skill 重命名或删除后，旧链接不在“仓库现有 skill”名单里，正常循环不会碰到。
  # 只处理指向本仓库 skills/ 的符号链接，不动指向别处的内容与实体目录。
  # VerifyOnly 下只报告并计为异常；--include 时只清理名单内的名字。
  local target="$1" p cur abs name w hit
  for p in "$target"/*; do
    [[ -L "$p" ]] || continue
    cur="$(readlink "$p")"
    # 相对链接先合并到所在目录，再词法归一化，最后比对前缀
    case "$cur" in
      /*) abs="$cur" ;;
      *) abs="$(dirname "$p")/$cur" ;;
    esac
    abs="$(normalize_path "$abs")"
    case "$abs" in
      "$SKILLS_DIR"/*) ;;
      *) continue ;;
    esac
    [[ -e "$p" ]] && continue
    name="$(basename "$p")"
    if [[ -n "$INCLUDE" ]]; then
      hit=0
      IFS=',' read -ra WANT <<< "$INCLUDE"
      for w in "${WANT[@]}"; do
        [[ "$name" == "$w" ]] && hit=1
      done
      [[ $hit -eq 0 ]] && continue
    fi
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "  [$name] 悬空链接（目标已不存在），重跑链接脚本清理: $cur" >&2
      failures=$((failures + 1))
    else
      rm "$p"
      echo "  [$name] 悬空链接已清理（目标不存在）: $cur"
    fi
  done
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

  clean_stale_links "$target"
done

# --- 推荐 skill（需依赖/命令安装，名单见 config/recommended-skills.txt） ---

recommended_skills() {
  # 输出推荐名单与 --include 交集后的 skill 名，每行一个；
  # 名单中有但仓库无目录的不输出（由 check-skills.py 报错）。
  local f="$REPO_ROOT/config/recommended-skills.txt"
  [[ -f "$f" ]] || return 0
  local line w
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | tr -d '[:space:]')"
    [[ -z "$line" ]] && continue
    if [[ -n "$INCLUDE" ]]; then
      local hit=0
      IFS=',' read -ra WANT <<< "$INCLUDE"
      for w in "${WANT[@]}"; do
        [[ "$line" == "$w" ]] && hit=1
      done
      [[ $hit -eq 0 ]] && continue
    fi
    [[ -d "$SKILLS_DIR/$line" ]] && printf '%s\n' "$line"
  done < "$f"
}

skill_command_name() {
  # 有 CLI 入口的 skill 在此登记命令名；无命令入口输出空
  case "$1" in
    htmlmini) echo "htmlmini" ;;
  esac
}

skill_command_entry() {
  # 命令包装的入口脚本绝对路径；无则输出空
  case "$1" in
    htmlmini) echo "$SKILLS_DIR/htmlmini/src/cli.js" ;;
  esac
}

deploy_skill_deps() {
  # $1=skill：含 package.json 则跑包管理器安装（优先 pnpm）
  local skill="$1" dir="$SKILLS_DIR/$1"
  [[ -f "$dir/package.json" ]] || return 0
  echo "  [$skill] 安装依赖…"
  if command -v pnpm >/dev/null 2>&1; then
    (cd "$dir" && pnpm install) || { echo "  [$skill] pnpm install 失败，跳过" >&2; return 1; }
  elif command -v npm >/dev/null 2>&1; then
    (cd "$dir" && npm install) || { echo "  [$skill] npm install 失败，跳过" >&2; return 1; }
  else
    echo "  [$skill] 未找到 pnpm/npm，跳过依赖安装" >&2
    return 1
  fi
}

install_skill_command() {
  # $1=skill：默认把 CLI 装成 ~/.local/bin/<cmd> 包装脚本（幂等）
  local skill="$1" cmd entry bindir link
  cmd="$(skill_command_name "$skill")"
  entry="$(skill_command_entry "$skill")"
  [[ -z "$cmd" || -z "$entry" ]] && return 0
  if [[ ! -f "$entry" ]]; then
    echo "  [$skill] 入口不存在，跳过命令安装: $entry" >&2
    return 1
  fi
  bindir="$HOME/.local/bin"
  mkdir -p "$bindir"
  link="$bindir/$cmd"
  if [[ -f "$link" ]] && grep -qF "$entry" "$link" 2>/dev/null; then
    echo "  [$skill] 命令已就绪: $link"
    return 0
  fi
  printf '#!/bin/sh\nexec node "%s" "$@"\n' "$entry" > "$link"
  chmod +x "$link"
  echo "  [$skill] 命令已安装: $link"
}

remove_skill_command() {
  # $1=skill：只删本仓库安装的包装（内容含真源入口路径），不动他人命令
  local skill="$1" cmd entry link
  cmd="$(skill_command_name "$skill")"
  entry="$(skill_command_entry "$skill")"
  [[ -z "$cmd" ]] && return 0
  link="$HOME/.local/bin/$cmd"
  if [[ -f "$link" ]] && grep -qF "$entry" "$link" 2>/dev/null; then
    rm -f "$link"
    echo "  [$skill] 命令已移除: $link"
  else
    echo "  [$skill] 命令不存在或非本仓库安装，不动: $link"
  fi
}

deploy_recommended_skills() {
  # 链接完成后的推荐部署：依赖走询问/显式开关，命令默认安装
  [[ $UNLINK -eq 1 || $VERIFY_ONLY -eq 1 ]] && return 0
  mapfile -t REC < <(recommended_skills)
  [[ ${#REC[@]} -eq 0 ]] && return 0
  if [[ $SKIP_REC_SKILLS -eq 1 ]]; then
    echo "已跳过推荐 skill 部署（--skip-recommended-skills）：${REC[*]}"
    return 0
  fi
  echo "== 推荐 skill（需依赖/命令）：${REC[*]} =="
  local do_deps=0
  if [[ $APPLY_REC_SKILLS -eq 1 ]]; then
    do_deps=1
  elif [[ -t 0 ]]; then
    local ans
    read -r -p "是否安装推荐 skill 的依赖（如 htmlmini 的 pnpm install）？[Y/n] " ans
    [[ "$ans" =~ ^([yY]([eE][sS])?)?$ ]] && do_deps=1
  else
    echo "非交互环境，跳过依赖安装（用 --apply-recommended-skills 执行）；命令仍默认安装。"
  fi
  local s
  for s in "${REC[@]}"; do
    if [[ $do_deps -eq 1 ]]; then
      deploy_skill_deps "$s" || echo "  [$s] 依赖安装未完成，命令照常安装" >&2
    fi
    install_skill_command "$s" || true
  done
}

third_party_names() {
  # 输出第三方名单与 --include 交集后的名称，每行一个。
  local f="$REPO_ROOT/config/third-party-skills.txt"
  [[ -f "$f" ]] || return 0
  local line name w hit
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    name="${line%%|*}"
    name="$(printf '%s' "$name" | tr -d '[:space:]')"
    [[ -z "$name" ]] && continue
    if [[ -n "$INCLUDE" ]]; then
      hit=0
      IFS=',' read -ra WANT <<< "$INCLUDE"
      for w in "${WANT[@]}"; do
        [[ "$name" == "$w" ]] && hit=1
      done
      [[ $hit -eq 0 ]] && continue
    fi
    printf '%s\n' "$name"
  done < "$f"
}

python_bin() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  fi
}

deploy_third_party_skills() {
  # 第三方 skill：交互默认 No；非交互默认跳过；实体由 Python 安装器管理。
  [[ $UNLINK -eq 1 || $VERIFY_ONLY -eq 1 ]] && return 0
  mapfile -t TP < <(third_party_names)
  [[ ${#TP[@]} -eq 0 ]] && return 0
  if [[ $SKIP_TP -eq 1 ]]; then
    echo "已跳过第三方 skill（--skip-third-party-skills）：${TP[*]}"
    return 0
  fi
  local action="install"
  [[ $SYNC_TP -eq 1 ]] && action="sync"
  if [[ $SYNC_TP -eq 0 && $APPLY_TP -eq 0 ]]; then
    if [[ -t 0 ]]; then
      local ans
      read -r -p "是否安装/更新第三方 skill（${TP[*]}；来自上游，默认 No）？[y/N] " ans
      if [[ ! "$ans" =~ ^[yY]([eE][sS])?$ ]]; then
        echo "已跳过第三方 skill。"
        return 0
      fi
    else
      echo "非交互环境，跳过第三方 skill（用 --apply-third-party-skills 或 --sync-third-party-skills）。"
      return 0
    fi
  fi
  local py
  py="$(python_bin)"
  if [[ -z "$py" ]]; then
    echo "未找到 Python，跳过第三方 skill（需要 Python 3.6+）。" >&2
    return 0
  fi
  echo "== 第三方 skill（${action}）：${TP[*]} =="
  local args=(-X utf8 "$REPO_ROOT/scripts/third-party-skills.py" "$action")
  local s
  for s in "${TP[@]}"; do args+=(--name "$s"); done
  if ! "$py" "${args[@]}"; then
    echo "第三方 skill ${action} 失败。" >&2
  fi
}

verify_third_party_skills() {
  # --verify-only 时校验第三方 skill；未安装只提示，不阻断。
  [[ $VERIFY_ONLY -eq 1 ]] || return 0
  [[ $SKIP_TP -eq 1 ]] && return 0
  mapfile -t TP < <(third_party_names)
  [[ ${#TP[@]} -eq 0 ]] && return 0
  local py
  py="$(python_bin)"
  if [[ -z "$py" ]]; then
    echo "未找到 Python，跳过第三方 skill 校验。"
    return 0
  fi
  local args=(-X utf8 "$REPO_ROOT/scripts/third-party-skills.py" verify)
  local s
  for s in "${TP[@]}"; do args+=(--name "$s"); done
  if ! "$py" "${args[@]}"; then
    echo "第三方 skill 校验失败（运行 --sync-third-party-skills，或用 status 查看）。" >&2
    failures=$((failures + 1))
  fi
}

unlink_recommended_commands() {
  # --unlink 时同步移除本仓库安装的命令；依赖目录（node_modules）保留
  [[ $UNLINK -eq 1 ]] || return 0
  mapfile -t REC < <(recommended_skills)
  [[ ${#REC[@]} -eq 0 ]] && return 0
  local s
  for s in "${REC[@]}"; do
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "  [$s] 命令将被移除（VerifyOnly）"
    else
      remove_skill_command "$s"
    fi
  done
  if [[ $VERIFY_ONLY -eq 0 ]]; then
    echo "注：推荐 skill 的依赖目录（如 node_modules）已保留，按需手工删除。"
  fi
  mapfile -t TP_HINT < <(third_party_names)
  if [[ ${#TP_HINT[@]} -gt 0 ]]; then
    echo "注：第三方 skill 不在 --unlink 范围；卸载用 python -X utf8 scripts/third-party-skills.py uninstall --name <name>"
  fi
}

verify_recommended_skills() {
  # --verify-only 时检查推荐 skill 的依赖与命令状态
  [[ $VERIFY_ONLY -eq 1 ]] || return 0
  [[ $SKIP_REC_SKILLS -eq 1 ]] && return 0
  local s cmd entry link
  while IFS= read -r s; do
    [[ -z "$s" ]] && continue
    if [[ -f "$SKILLS_DIR/$s/package.json" && ! -d "$SKILLS_DIR/$s/node_modules" ]]; then
      echo "推荐 skill [$s] 依赖未安装（缺 node_modules，用 --apply-recommended-skills 部署）" >&2
      failures=$((failures + 1))
    fi
    cmd="$(skill_command_name "$s")"
    entry="$(skill_command_entry "$s")"
    if [[ -n "$cmd" ]]; then
      link="$HOME/.local/bin/$cmd"
      if [[ -f "$link" ]] && grep -qF "$entry" "$link" 2>/dev/null \
        && command -v "$cmd" >/dev/null 2>&1; then
        echo "推荐 skill [$s] 命令 OK：$cmd"
      else
        echo "推荐 skill [$s] 命令缺失（期望 $link 可用，重跑链接脚本安装）" >&2
        failures=$((failures + 1))
      fi
    fi
  done < <(recommended_skills)
}

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
deploy_recommended_skills
deploy_third_party_skills
unlink_recommended_commands

check_global_agents() {
  # 全局 AGENTS.md 漂移提示：缺失计异常，不一致只警告（手工合并，不自动覆盖）。
  [[ $VERIFY_ONLY -eq 1 ]] || return 0
  local repo_agents="$REPO_ROOT/config/global-AGENTS.md"
  [[ -f "$repo_agents" ]] || return 0
  # 每个消费全局 AGENTS.md 的 harness 一个目标路径，与 README「全局 AGENTS.md 同步与合并」保持一致
  local target name live
  for target in "OpenCode|$HOME/.config/opencode/AGENTS.md" "ZCode|$HOME/.zcode/AGENTS.md"; do
    name="${target%%|*}"
    live="${target#*|}"
    if [[ ! -f "$live" ]]; then
      echo "全局 AGENTS.md($name) 缺失（期望按 README 从 config/global-AGENTS.md 恢复）" >&2
      failures=$((failures + 1))
    elif ! cmp -s "$repo_agents" "$live"; then
      echo "全局 AGENTS.md($name) 与真源不一致，按 README 手工合并（不自动覆盖）" >&2
    else
      echo "全局 AGENTS.md($name) 与真源一致。"
    fi
  done
}

check_global_agents
verify_recommended_skills
verify_third_party_skills

if [[ $VERIFY_ONLY -eq 1 ]]; then
  if [[ $failures -gt 0 ]]; then
    echo "校验发现 $failures 处异常，见上。" >&2
    exit 1
  fi
  echo "全部链接正常。"
fi

if [[ $VERIFY_ONLY -eq 0 && $UNLINK -eq 0 ]]; then
  echo "提示：推荐依赖套餐见 docs/skill-dependencies.md#部署基线；检查命令 python3 -X utf8 scripts/check-skill-deps.py --profile standard"
fi
