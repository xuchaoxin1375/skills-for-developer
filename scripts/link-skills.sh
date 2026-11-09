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
#   scripts/link-skills.sh --plan             # 只打印部署计划，不修改
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
# 当前为 htmlmini）：只对未就绪项询问，依赖与命令合并确认；
# 非交互默认跳过依赖，命令仍装到 ~/.local/bin。
# 第三方 skill（config/third-party-skills.txt）：实体不入本仓库，交互默认 No，
# 实体放 $THIRD_PARTY_SKILLS_HOME/<name>（默认 ~/.local/share/skills-for-developer/third-party），
# 各已登记的 harness 目录都用链接指向它。
set -euo pipefail

# 让本次校验能看到脚本安装到 ~/.local/bin 的命令（当前进程未必继承更新后的 PATH）
export PATH="$HOME/.local/bin:$PATH"


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
PLAN=0
INCLUDE=""
APPLY_RECOMMENDED=0
SKIP_RECOMMENDED=0
APPLY_REC_SKILLS=0
SKIP_REC_SKILLS=0
APPLY_TP=0
SKIP_TP=0
SYNC_TP=0
QUIET=0

# -Quiet 只隐藏逐项成功/进度行，警告、失败和最终汇总照常输出。
say() { [[ $QUIET -eq 1 ]] || echo "$@"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=1; shift ;;
    --plan) PLAN=1; shift ;;
    --quiet) QUIET=1; shift ;;
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
    -h|--help) sed -n '2,36p' "$0"; exit 0 ;;
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
if [[ ${#SKILLS[@]} -eq 0 ]]; then
  upstream_selection=0
  if [[ $UNLINK -eq 0 && $SKIP_TP -eq 0 && -f "$REPO_ROOT/config/upstream-skills.json" ]]; then
    selection_py="$(command -v python3 || command -v python || true)"
    if [[ -n "$selection_py" ]] && "$selection_py" -X utf8 -c \
      'import json,sys; data=json.load(open(sys.argv[1],encoding="utf-8")); wanted=set(sys.argv[2].split(",")); sys.exit(0 if any(n in wanted for r in data["repositories"] for n in r["skills"]) else 1)' \
      "$REPO_ROOT/config/upstream-skills.json" "$INCLUDE"; then
      upstream_selection=1
    fi
  fi
  [[ $upstream_selection -eq 1 ]] || { echo "没有可处理的 skill。" >&2; exit 1; }
fi

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
      say "  [$name] 悬空链接已清理（目标不存在）: $cur"
    fi
  done
}

failures=0

# --plan 只预览，不创建目录、不改链接。
if [[ $PLAN -eq 0 ]]; then
for target in "${TARGETS[@]}"; do
  say "== $target =="
  if [[ ! -d "$target" ]]; then
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "  缺失目录（VerifyOnly，不创建）: $target" >&2
      failures=$((failures + 1))
      continue
    fi
    mkdir -p "$target"
    say "  创建目录"
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
            say "$label 将被移除（VerifyOnly）"
          else
            rm "$link"
            say "$label 已移除"
          fi
        else
          echo "$label 是指向别处的链接（${cur}），不动" >&2
        fi
      else
        say "$label 无链接，跳过"
      fi
      continue
    fi

    if [[ -L "$link" ]]; then
      cur="$(readlink "$link")"
      if [[ "$cur" == "$dest" ]]; then
        say "$label OK"
        [[ -f "$link/SKILL.md" ]] || { echo "$label 链接存在但 SKILL.md 不可读" >&2; failures=$((failures + 1)); }
      else
        if [[ $VERIFY_ONLY -eq 1 ]]; then
          echo "$label 指向错误：${cur}（期望 ${dest}）" >&2
          failures=$((failures + 1))
        else
          rm "$link"
          ln -s "$dest" "$link"
          say "$label 已纠正 -> $dest"
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
        say "$label 实体已备份到 ${backup}，链接已创建"
      fi
    else
      if [[ $VERIFY_ONLY -eq 1 ]]; then
        echo "$label 缺失（期望 -> ${dest}）" >&2
        failures=$((failures + 1))
      else
        ln -s "$dest" "$link"
        say "$label 已创建 -> $dest"
      fi
    fi
  done

  clean_stale_links "$target"
done
fi

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
    say "  [$skill] 命令已就绪: $link"
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
  # 链接完成后的推荐部署：只对未就绪项询问，依赖与命令合并成一个决策。
  [[ $UNLINK -eq 1 || $VERIFY_ONLY -eq 1 ]] && return 0
  mapfile -t REC < <(recommended_skills)
  [[ ${#REC[@]} -eq 0 ]] && return 0
  if [[ $SKIP_REC_SKILLS -eq 1 ]]; then
    echo "已跳过推荐 skill 部署（--skip-recommended-skills）：${REC[*]}"
    return 0
  fi
  local s line need_deps need_cmd need_any=0 need_deps_any=0
  local action="" hint=""
  local -a REC_PLAN=()
  for s in "${REC[@]}"; do
    line="$(plan_rec_line "$s")"
    REC_PLAN+=("$line")
    IFS='|' read -r s need_deps need_cmd <<< "$line"
    if [[ $need_deps -eq 1 || $need_cmd -eq 1 ]]; then
      need_any=1
      if [[ $need_deps -eq 1 ]]; then
        need_deps_any=1
        [[ -n "$action" ]] && action+="+"
        action+="依赖"
      fi
      if [[ $need_cmd -eq 1 ]]; then
        [[ -n "$action" ]] && action+="+"
        action+="命令"
      fi
    fi
  done
  if [[ $need_any -eq 0 ]]; then
    echo "推荐 skill 已就绪：${REC[*]}"
    return 0
  fi
  [[ $need_deps_any -eq 1 ]] && hint="（依赖安装会联网）"
  echo "== 推荐 skill（需依赖/命令）：${REC[*]} =="
  local do_all=0
  if [[ $APPLY_REC_SKILLS -eq 1 ]]; then
    do_all=1
  elif [[ -t 0 ]]; then
    local ans
    read -r -p "安装/创建推荐 skill 的${action}${hint}？[Y/n] " ans
    [[ "$ans" =~ ^([yY]([eE][sS])?)?$ ]] && do_all=1
  else
    echo "非交互环境，跳过依赖安装（用 --apply-recommended-skills 执行）；命令仍默认安装。"
    do_all=2
  fi
  if [[ $do_all -eq 0 ]]; then
    echo "已跳过推荐 skill（依赖与命令均未改动）。"
    return 0
  fi
  for line in "${REC_PLAN[@]}"; do
    IFS='|' read -r s need_deps need_cmd <<< "$line"
    if [[ $do_all -eq 1 && $need_deps -eq 1 ]]; then
      deploy_skill_deps "$s" || echo "  [$s] 依赖安装未完成，命令照常安装" >&2
    fi
    if [[ $need_cmd -eq 1 ]]; then
      install_skill_command "$s" || true
    fi
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
      local ans detail="" n
      for n in "${TP[@]}"; do
        [[ -n "$detail" ]] && detail+=", "
        detail+="${n}（$(plan_tp_state "$n")，$(third_party_field "$n" repo)@$(third_party_field "$n" ref)）"
      done
      read -r -p "是否安装/更新第三方 skill（${detail}；来自上游，默认 No）？[y/N] " ans
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
        say "推荐 skill [$s] 命令 OK：$cmd"
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
    if [[ ! -f "$dst" ]]; then
      read -r -p "推荐 cli.json 不存在，是否应用？[Y/n] " ans
      [[ "$ans" =~ ^([yY]([eE][sS])?)?$ ]] && do_apply=1
    else
      read -r -p "推荐 cli.json 与当前配置不同（覆盖前备份），是否应用？[y/N] " ans
      [[ "$ans" =~ ^[yY]([eE][sS])?$ ]] && do_apply=1
    fi
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

plan_link_counts() {
  # 输出 create|replace|ok|missing_dirs，供 --plan 与完成摘要复用。
  local target skill link dest create=0 replace=0 ok=0 missing_dirs=0
  for target in "${TARGETS[@]}"; do
    [[ -d "$target" ]] || missing_dirs=$((missing_dirs + 1))
    for skill in "${SKILLS[@]}"; do
      link="$target/$skill"
      dest="$SKILLS_DIR/$skill"
      if [[ -L "$link" ]]; then
        if [[ "$(readlink "$link")" == "$dest" ]]; then
          ok=$((ok + 1))
        else
          replace=$((replace + 1))
        fi
      elif [[ -e "$link" ]]; then
        replace=$((replace + 1))
      else
        create=$((create + 1))
      fi
    done
  done
  printf '%s|%s|%s|%s\n' "$create" "$replace" "$ok" "$missing_dirs"
}

plan_cli_state() {
  local repo_cli="$REPO_ROOT/config/opencode/cli.json"
  local dst="$HOME/.config/opencode/cli.json"
  [[ -f "$repo_cli" ]] || { echo absent; return 0; }
  [[ -f "$dst" ]] || { echo missing; return 0; }
  if cmp -s "$repo_cli" "$dst"; then echo same; else echo different; fi
}

plan_rec_line() {
  # 输出 skill|need_deps|need_cmd；只读状态，不安装。
  local skill="$1" dir="$SKILLS_DIR/$1" cmd entry link
  local need_deps=0 need_cmd=0
  if [[ -f "$dir/package.json" && ! -d "$dir/node_modules" ]]; then
    need_deps=1
  fi
  cmd="$(skill_command_name "$skill")"
  entry="$(skill_command_entry "$skill")"
  if [[ -n "$cmd" && -n "$entry" ]]; then
    link="$HOME/.local/bin/$cmd"
    if [[ ! -f "$link" ]] || ! grep -qF "$entry" "$link" 2>/dev/null \
      || ! command -v "$cmd" >/dev/null 2>&1; then
      need_cmd=1
    fi
  fi
  printf '%s|%s|%s\n' "$skill" "$need_deps" "$need_cmd"
}

third_party_field() {
  # 从第三方名单读取字段：third_party_field <name> repo|kind|ref
  local want="$1" field="$2" line name repo kind ref preserve desc
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    IFS='|' read -r name repo kind ref preserve desc <<< "$line"
    name="$(printf '%s' "$name" | tr -d '[:space:]')"
    [[ "$name" == "$want" ]] || continue
    case "$field" in
      repo) printf '%s' "$repo" | tr -d '[:space:]' ;;
      kind) printf '%s' "$kind" | tr -d '[:space:]' ;;
      ref) printf '%s' "$ref" | tr -d '[:space:]' ;;
    esac
    return 0
  done < "$REPO_ROOT/config/third-party-skills.txt"
}

plan_tp_state() {
  local name="$1"
  local home="${THIRD_PARTY_SKILLS_HOME:-$HOME/.local/share/skills-for-developer/third-party}"
  if [[ -d "$home/$name" ]]; then echo "已安装"; else echo "未安装"; fi
}

print_deploy_plan() {
  local create replace ok missing_dirs state skill need_deps need_cmd name repo ref
  IFS='|' read -r create replace ok missing_dirs <<< "$(plan_link_counts)"
  echo "== 部署计划（只预览，不修改）=="
  echo "  链接: ${#SKILLS[@]} 个 skill -> ${#TARGETS[@]} 个目录；新建 ${create}，修正/替换 ${replace}，已就绪 ${ok}；缺目录 ${missing_dirs}"
  case "$(plan_cli_state)" in
    same) echo "  cli.json: 已是最新（跳过）" ;;
    missing) echo "  cli.json: 目标不存在（交互默认应用，--apply-recommended-cli 可直接应用）" ;;
    different) echo "  cli.json: 与真源不同（交互默认保留，覆盖前备份）" ;;
    absent) echo "  cli.json: 仓库没有推荐文件（跳过）" ;;
  esac
  while IFS='|' read -r skill need_deps need_cmd; do
    state=""
    [[ "$need_deps" -eq 1 ]] && state+="依赖未安装 "
    [[ "$need_cmd" -eq 1 ]] && state+="命令未安装 "
    [[ -z "$state" ]] && state="已就绪"
    state="${state% }"
    echo "  推荐 skill [$skill]: $state"
  done < <(while IFS= read -r skill; do [[ -n "$skill" ]] && plan_rec_line "$skill"; done < <(recommended_skills))
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    repo="$(third_party_field "$name" repo)"
    ref="$(third_party_field "$name" ref)"
    echo "  第三方 [$name]: $(plan_tp_state "$name") 来源 ${repo}@${ref}（默认不装）"
  done < <(third_party_names)
  if [[ -f "$REPO_ROOT/config/upstream-skills.json" ]]; then
    echo "  上游 clone 链接: 由 link-upstream-skills.py 检查/修正"
  fi
  echo "  本脚本未自动处理（scripts/deploy.sh 会串起来）: 全局 AGENTS.md 合并、OpenCode 插件链接、依赖套餐检查"
}

print_deploy_summary() {
  local skill need_deps need_cmd name state
  echo "== 完成 =="
  echo "- skill 链接: 已处理 ${#SKILLS[@]} 个 -> ${#TARGETS[@]} 个目录"
  if [[ $SKIP_RECOMMENDED -eq 1 ]]; then
    echo "- cli.json: 已跳过（--skip-recommended-cli）"
  else
    case "$(plan_cli_state)" in
      same) echo "- cli.json: 已就绪" ;;
      absent) echo "- cli.json: 仓库没有推荐文件" ;;
      *) echo "- cli.json: 未应用（可重跑并确认，或用 --apply-recommended-cli）" ;;
    esac
  fi
  if [[ $SKIP_REC_SKILLS -eq 1 ]]; then
    echo "- 推荐 skill: 已跳过（--skip-recommended-skills）"
  else
    while IFS='|' read -r skill need_deps need_cmd; do
      state=""
      [[ "$need_deps" -eq 1 ]] && state+="依赖未安装 "
      [[ "$need_cmd" -eq 1 ]] && state+="命令未安装 "
      if [[ -z "$state" ]]; then
        echo "- 推荐 skill [$skill]: 已就绪"
      else
        state="${state% }"
        echo "- 推荐 skill [$skill]: $state"
      fi
    done < <(while IFS= read -r skill; do [[ -n "$skill" ]] && plan_rec_line "$skill"; done < <(recommended_skills))
  fi
  if [[ $SKIP_TP -eq 1 ]]; then
    echo "- 第三方 skill: 已跳过（--skip-third-party-skills）"
  else
    while IFS= read -r name; do
      [[ -z "$name" ]] && continue
      echo "- 第三方 [$name]: $(plan_tp_state "$name")"
    done < <(third_party_names)
  fi
  echo "- 本脚本未处理（scripts/deploy.sh 会串起来）: 全局 AGENTS.md 合并、OpenCode 插件链接、依赖套餐检查"
  echo "  依赖检查: python -X utf8 scripts/check-skill-deps.py --profile standard"
}

if [[ $PLAN -eq 1 ]]; then
  print_deploy_plan
  exit 0
fi

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

if [[ $UNLINK -eq 0 && $SKIP_TP -eq 0 && -f "$REPO_ROOT/config/upstream-skills.json" ]]; then
  upstream_py="$(python_bin)"
  if [[ -z "$upstream_py" ]]; then
    echo "Python missing; upstream clone links were NOT checked." >&2
    failures=$((failures + 1))
  else
    upstream_args=(-X utf8 "$REPO_ROOT/scripts/link-upstream-skills.py" --repo-root "$REPO_ROOT")
    [[ $VERIFY_ONLY -eq 1 ]] && upstream_args+=(--verify-only)
    [[ -n "$INCLUDE" ]] && upstream_args+=(--include "$INCLUDE")
    if ! "$upstream_py" "${upstream_args[@]}"; then
      echo "Upstream clone link check failed; see docs/upstream-skills.md." >&2
      failures=$((failures + 1))
      [[ $VERIFY_ONLY -eq 0 ]] && exit 1
    fi
  fi
fi

if [[ $VERIFY_ONLY -eq 1 ]]; then
  if [[ $failures -gt 0 ]]; then
    echo "校验发现 $failures 处异常，见上。" >&2
    exit 1
  fi
  echo "全部链接正常。"
fi

if [[ $VERIFY_ONLY -eq 0 && $UNLINK -eq 0 ]]; then
  # 推荐工具：只检测并提示，不自动安装；缺失不阻断部署
  check_basic_tool() {
    local label=$1 hint=$2
    local name located
    shift 2
    for name in "$@"; do
      if located=$(command -v "$name" 2>/dev/null); then
        echo "推荐工具 $label 可用：$located"
        return 0
      fi
    done
    echo "建议安装 $label（推荐，缺失不阻断）：$hint"
  }
  check_basic_tool git 'sudo apt install git（macOS: brew install git）' git
  check_basic_tool 'ripgrep（rg）' 'sudo apt install ripgrep（macOS: brew install ripgrep）' rg
  check_basic_tool fd 'sudo apt install fd-find（命令名 fdfind；macOS: brew install fd）' fd fdfind
  check_basic_tool Scrapling 'uv tool install "scrapling[fetchers]"（再运行 scrapling install）' scrapling
  check_basic_tool Playwright 'python3 -m pip install playwright && python3 -m playwright install chromium' playwright
  print_deploy_summary
fi
