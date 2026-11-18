#!/usr/bin/env bash
#
# 一键部署：子模块检查、skill 链接、OpenCode 插件链接、全局 AGENTS.md 恢复与校验。
# 串联子模块检查、link-skills.sh、link-plugins.sh 与 AGENTS.md 同步，避免漏步；
# 结束时打印各阶段耗时与效率复盘提示，便于发现部署流程劣化。
#
# 用法（仓库根）：
#   scripts/deploy.sh                      # 部署（交互终端下按 link-skills 规则询问）
#   scripts/deploy.sh --plan               # 只预览，不修改
#   scripts/deploy.sh --verify-only        # 只校验，不修改
#   scripts/deploy.sh --quiet              # 隐藏逐项成功/进度行，保留警告与汇总
#   scripts/deploy.sh --skip-plugins       # 跳过 OpenCode 插件
#   scripts/deploy.sh --skip-global-agents # 跳过全局 AGENTS.md
#   scripts/deploy.sh --skip-dep-check     # 跳过依赖套餐检查
#   scripts/deploy.sh --skip-submodules    # 跳过 git submodule 初始化/检查
#
# 以下开关原样转给 link-skills.sh：
#   --apply-recommended-cli / --skip-recommended-cli
#   --apply-recommended-skills / --skip-recommended-skills
#   --apply-third-party-skills / --skip-third-party-skills / --sync-third-party-skills
#
# OpenCode 的 AGENTS.md 缺失时复制；内容不一致只警告。
# ZCode 仅在 ~/.zcode 存在时尝试 symlink 到 OpenCode 副本；无符号链接权限时跳过，不复制、不计失败。
set -euo pipefail

PLAN=0
VERIFY_ONLY=0
QUIET=0
SKIP_PLUGINS=0
SKIP_AGENTS=0
SKIP_DEPS=0
SKIP_SUBMODULES=0
SKILL_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
  --plan)
    PLAN=1
    SKILL_ARGS+=(--plan)
    shift
    ;;
  --verify-only)
    VERIFY_ONLY=1
    SKILL_ARGS+=(--verify-only)
    shift
    ;;
  --quiet)
    QUIET=1
    SKILL_ARGS+=(--quiet)
    shift
    ;;
  --skip-plugins)
    SKIP_PLUGINS=1
    shift
    ;;
  --skip-global-agents)
    SKIP_AGENTS=1
    shift
    ;;
  --skip-dep-check)
    SKIP_DEPS=1
    shift
    ;;
  --skip-submodules)
    SKIP_SUBMODULES=1
    shift
    ;;
  --apply-recommended-cli)
    SKILL_ARGS+=(--apply-recommended-cli)
    shift
    ;;
  --skip-recommended-cli)
    SKILL_ARGS+=(--skip-recommended-cli)
    shift
    ;;
  --apply-recommended-skills)
    SKILL_ARGS+=(--apply-recommended-skills)
    shift
    ;;
  --skip-recommended-skills)
    SKILL_ARGS+=(--skip-recommended-skills)
    shift
    ;;
  --apply-third-party-skills)
    SKILL_ARGS+=(--apply-third-party-skills)
    shift
    ;;
  --skip-third-party-skills)
    SKILL_ARGS+=(--skip-third-party-skills)
    shift
    ;;
  --sync-third-party-skills)
    SKILL_ARGS+=(--sync-third-party-skills)
    shift
    ;;
  -h | --help)
    sed -n '2,23p' "$0"
    exit 0
    ;;
  *)
    echo "未知参数: $1" >&2
    exit 2
    ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -d "$REPO_ROOT/skills" ]] || {
  echo "skills 目录不存在: $REPO_ROOT/skills" >&2
  exit 1
}

say() { [[ $QUIET -eq 1 ]] || echo "$@"; }

resolve_path() {
  local p="$1"
  if [[ "$p" != /* ]]; then p="$PWD/$p"; fi
  (cd "$(dirname "$p")" 2>/dev/null && printf '%s/%s\n' "$(pwd -P)" "$(basename "$p")") || printf '%s\n' "$p"
}

zcode_link_matches() {
  [[ -L "$1" ]] || return 1
  local target
  target="$(readlink "$1" 2>/dev/null || true)"
  [[ -n "$target" ]] || return 1
  if [[ "$target" != /* ]]; then target="$(dirname "$1")/$target"; fi
  [[ "$(resolve_path "$target")" == "$(resolve_path "$2")" ]]
}

opencode_present() {
  # 只看命令或已有配置文件，不把链接脚本刚创建的 skills/ 目录当成 OpenCode 已安装。
  command -v opencode >/dev/null 2>&1 && return 0
  local dir="$HOME/.config/opencode"
  [[ -f "$dir/AGENTS.md" || -f "$dir/opencode.json" || -f "$dir/auth.json" || -f "$dir/cli.json" ]]
}

uninitialized_submodules() {
  command -v git >/dev/null 2>&1 || return 0
  git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  git -C "$REPO_ROOT" submodule status 2>/dev/null | awk '$1 ~ /^-/ {print $2}'
}

sync_submodules() {
  # codex-model-config 是 git submodule；zip/部分包不含内容时只提示，不阻塞其他 skill。
  local uninit count
  uninit="$(uninitialized_submodules || true)"
  if [[ -z "$uninit" ]]; then
    local missing_skill=0 d
    for d in "$REPO_ROOT"/skills/*/; do
      [[ -f "$d/SKILL.md" ]] || {
        missing_skill=1
        break
      }
    done
    if [[ -f "$REPO_ROOT/.gitmodules" && $missing_skill -eq 1 ]]; then
      if ! command -v git >/dev/null 2>&1; then
        echo "WARN: 未找到 git，无法初始化子模块（codex-model-config 可能缺失）" >&2
      elif ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "WARN: 当前目录不是 git 工作区，无法初始化子模块（codex-model-config 可能缺失）；需要该 skill 时用 git clone --recurse-submodules 重新获取" >&2
      fi
    fi
    return 0
  fi
  count="$(printf '%s\n' "$uninit" | grep -c . || true)"
  if [[ $PLAN -eq 1 ]]; then
    say "计划初始化子模块（${count} 个）: $(printf '%s' "$uninit" | tr '\n' ' ')"
    return 0
  fi
  if [[ $VERIFY_ONLY -eq 1 ]]; then
    echo "WARN: 子模块未初始化（${count} 个）: $(printf '%s' "$uninit" | tr '\n' ' ')" >&2
    echo "  运行 scripts/deploy.sh 或 git -C \"$REPO_ROOT\" submodule update --init --depth 1 修复；不阻塞其他 skill。" >&2
    return 0
  fi
  say "== 初始化子模块（${count} 个）: $(printf '%s' "$uninit" | tr '\n' ' ') =="
  if GIT_TERMINAL_PROMPT=0 git -C "$REPO_ROOT" submodule update --init --depth 1; then
    say "子模块已初始化"
  else
    echo "WARN: 子模块初始化失败，继续部署其他 skill；可稍后手动运行: git -C \"$REPO_ROOT\" submodule update --init --depth 1" >&2
  fi
}

failures=0
timings=()
total_start=$SECONDS

# 0. git submodule（未初始化时自动拉取；失败只警告）
if [[ $SKIP_SUBMODULES -eq 0 ]]; then
  start=$SECONDS
  sync_submodules
  timings+=("子模块:$((SECONDS - start))")
fi

# 1. skill 链接
start=$SECONDS
if ! "$REPO_ROOT/scripts/link-skills.sh" "${SKILL_ARGS[@]+"${SKILL_ARGS[@]}"}"; then
  failures=$((failures + 1))
fi
timings+=("skill 链接:$((SECONDS - start))")

# 2. OpenCode 插件链接
if [[ $SKIP_PLUGINS -eq 0 ]]; then
  start=$SECONDS
  if [[ $PLAN -eq 1 ]]; then
    say "计划: 运行 link-plugins.sh（建链/校正）"
  else
    plugin_args=()
    [[ $VERIFY_ONLY -eq 1 ]] && plugin_args+=(--verify-only)
    [[ $QUIET -eq 1 ]] && plugin_args+=(--quiet)
    if ! "$REPO_ROOT/scripts/link-plugins.sh" "${plugin_args[@]+"${plugin_args[@]}"}"; then
      failures=$((failures + 1))
    fi
  fi
  timings+=("插件链接:$((SECONDS - start))")
fi

# 3. 全局 AGENTS.md
if [[ $SKIP_AGENTS -eq 0 ]]; then
  start=$SECONDS
  src="$REPO_ROOT/config/global-AGENTS.md"
  if [[ ! -f "$src" ]]; then
    echo "WARN: 缺少 config/global-AGENTS.md，跳过全局 AGENTS.md 同步" >&2
    failures=$((failures + 1))
  else
    opencode_agents="$HOME/.config/opencode/AGENTS.md"
    opencode_was_present=0
    opencode_present && opencode_was_present=1
    if [[ -f "$opencode_agents" ]]; then
      if cmp -s "$src" "$opencode_agents"; then
        say "全局 AGENTS.md(OpenCode) 已与真源一致"
      else
        diff_out="$(diff "$src" "$opencode_agents" || true)"
        truth_only="$(printf '%s\n' "$diff_out" | grep -c '^<' || true)"
        local_only="$(printf '%s\n' "$diff_out" | grep -c '^>' || true)"
        echo "WARN: 全局 AGENTS.md(OpenCode) 与真源不同（真源独有 ${truth_only} 行，本机独有 ${local_only} 行）；保留本机文件，按真源对齐通用条目，本机定制留在末尾「个性化规则补充」" >&2
      fi
    elif [[ $PLAN -eq 1 ]]; then
      if [[ $opencode_was_present -eq 1 ]]; then
        say "全局 AGENTS.md(OpenCode) 计划复制"
      else
        say "全局 AGENTS.md(OpenCode): 未检测到 OpenCode，计划预置副本"
      fi
    elif [[ $VERIFY_ONLY -eq 1 ]]; then
      if [[ $opencode_was_present -eq 1 ]]; then
        echo "WARN: 全局 AGENTS.md(OpenCode) 缺失" >&2
        failures=$((failures + 1))
      else
        say "全局 AGENTS.md(OpenCode): 未检测到 OpenCode，跳过（需要时运行 scripts/deploy.sh 预置）"
      fi
    else
      mkdir -p "$(dirname "$opencode_agents")"
      cp "$src" "$opencode_agents"
      if [[ $opencode_was_present -eq 1 ]]; then
        echo "全局 AGENTS.md(OpenCode) 已恢复"
      else
        echo "全局 AGENTS.md(OpenCode) 已预置（未检测到 OpenCode）"
      fi
    fi

    # ZCode 只认 ~/.zcode/AGENTS.md；优先 symlink 到 OpenCode 副本。
    # 不允许建链时跳过，不落回副本，也不计失败；~/.zcode 不存在时视为未使用。
    zcode_dir="$HOME/.zcode"
    zcode_agents="$zcode_dir/AGENTS.md"
    if [[ ! -d "$zcode_dir" ]]; then
      say "全局 AGENTS.md(ZCode): 未检测到 ~/.zcode，跳过（未安装/未使用）"
    elif zcode_link_matches "$zcode_agents" "$opencode_agents"; then
      say "全局 AGENTS.md(ZCode) 已链接 -> $opencode_agents"
    elif [[ -L "$zcode_agents" ]]; then
      echo "WARN: 全局 AGENTS.md(ZCode) 已链接到其他目标（$(readlink "$zcode_agents" 2>/dev/null || true)），保留不动" >&2
    elif [[ -e "$zcode_agents" && ! -f "$zcode_agents" ]]; then
      echo "WARN: 全局 AGENTS.md(ZCode) 路径不是普通文件，跳过" >&2
    elif [[ -f "$zcode_agents" ]] && ! cmp -s "$opencode_agents" "$zcode_agents"; then
      echo "WARN: 全局 AGENTS.md(ZCode) 是普通文件且与 OpenCode 不同；保留本机文件，ZCode 同步跳过（如需共享，手工合并后删除该文件）" >&2
    elif [[ $PLAN -eq 1 ]]; then
      if [[ -f "$zcode_agents" ]]; then
        say "全局 AGENTS.md(ZCode) 计划替换为 symlink"
      else
        say "全局 AGENTS.md(ZCode) 计划建立 symlink（无权限时跳过）"
      fi
    elif [[ $VERIFY_ONLY -eq 1 ]]; then
      if [[ -f "$zcode_agents" ]]; then
        say "全局 AGENTS.md(ZCode) 是普通文件（与 OpenCode 一致），部署时将替换为 symlink"
      else
        say "全局 AGENTS.md(ZCode) 未建立链接；部署时尝试，无符号链接权限则跳过"
      fi
    elif [[ ! -f "$opencode_agents" ]]; then
      say "全局 AGENTS.md(ZCode): OpenCode 副本缺失，跳过"
    elif [[ -f "$zcode_agents" ]]; then
      tmp="$zcode_agents.tmp-$$"
      if ln -s "$opencode_agents" "$tmp" 2>/dev/null; then
        mv -f "$tmp" "$zcode_agents"
        echo "全局 AGENTS.md(ZCode) 已建立 symlink -> $opencode_agents"
      else
        rm -f "$tmp"
        echo "WARN: 全局 AGENTS.md(ZCode) 未建立：本机符号链接不可用，跳过 ZCode 全局规则同步（不落回副本）" >&2
      fi
    else
      if ln -s "$opencode_agents" "$zcode_agents" 2>/dev/null; then
        echo "全局 AGENTS.md(ZCode) 已建立 symlink -> $opencode_agents"
      else
        echo "WARN: 全局 AGENTS.md(ZCode) 未建立：本机符号链接不可用，跳过 ZCode 全局规则同步（不落回副本）" >&2
      fi
    fi
  fi
  timings+=("全局 AGENTS.md:$((SECONDS - start))")
fi

# 4. 依赖套餐检查（只提示，不阻断）
if [[ $SKIP_DEPS -eq 0 ]]; then
  start=$SECONDS
  py="$(command -v python3 || command -v python || true)"
  if [[ -z "$py" ]]; then
    echo "WARN: 未找到 Python，跳过依赖套餐检查" >&2
  else
    say "== 依赖套餐检查（standard，推荐项，不阻断）=="
    if ! "$py" -X utf8 "$REPO_ROOT/scripts/check-skill-deps.py" --profile standard; then
      echo "WARN: 依赖套餐检查有缺失项（推荐项，不阻断部署）" >&2
    fi
  fi
  timings+=("依赖套餐检查:$((SECONDS - start))")
fi

echo
echo "== 部署效率复盘 =="
echo "总耗时: $((SECONDS - total_start))s"
for t in "${timings[@]+"${timings[@]}"}"; do
  echo "  ${t%:*}: ${t##*:}s"
done
if [[ $failures -gt 0 ]]; then
  echo "失败/异常: ${failures} 项（见上方警告）"
else
  echo "失败/异常: 无"
fi
echo "可选反馈: 若某步明显变慢、需要二次补命令或输出难读，可把本段耗时与步骤反馈给仓库维护者，用于优化部署指南。"

[[ $failures -eq 0 ]] || exit 1
