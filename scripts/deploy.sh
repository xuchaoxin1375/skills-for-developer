#!/usr/bin/env bash
#
# 一键部署：skill 链接、OpenCode 插件链接、全局 AGENTS.md 恢复与校验。
# 串联 link-skills.sh、link-plugins.sh 与 AGENTS.md 同步，避免漏步；
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
#
# 以下开关原样转给 link-skills.sh：
#   --apply-recommended-cli / --skip-recommended-cli
#   --apply-recommended-skills / --skip-recommended-skills
#   --apply-third-party-skills / --skip-third-party-skills / --sync-third-party-skills
#
# 全局 AGENTS.md 只在目标缺失时复制；内容不一致只警告，不覆盖本机文件。
set -euo pipefail

PLAN=0
VERIFY_ONLY=0
QUIET=0
SKIP_PLUGINS=0
SKIP_AGENTS=0
SKIP_DEPS=0
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
    sed -n '2,27p' "$0"
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

failures=0
timings=()
total_start=$SECONDS

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
    for dst in "$HOME/.config/opencode/AGENTS.md" "$HOME/.zcode/AGENTS.md"; do
      if [[ -f "$dst" ]]; then
        if cmp -s "$src" "$dst"; then
          say "全局 AGENTS.md($dst) 已与真源一致"
        else
          echo "WARN: 全局 AGENTS.md($dst) 与本机不同；保留本机文件，请对比后手工合并（不覆盖）" >&2
        fi
      elif [[ $PLAN -eq 1 ]]; then
        say "全局 AGENTS.md($dst) 计划复制"
      elif [[ $VERIFY_ONLY -eq 1 ]]; then
        echo "WARN: 全局 AGENTS.md($dst) 缺失" >&2
        failures=$((failures + 1))
      else
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo "全局 AGENTS.md($dst) 已恢复"
      fi
    done
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
