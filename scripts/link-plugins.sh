#!/usr/bin/env bash
#
# 将本仓库 plugins/ 下的每个插件包通过 symlink 链接到 OpenCode 的 plugins 目录。
# Linux/macOS 用；Windows 请用 scripts/link-plugins.ps1（Junction）。
#
# 唯一真源: <repo>/plugins/<name>/（内含 package.json）。
# Harness 侧只放 symlink，不存实体：
#   - OpenCode: $HOME/.config/opencode/plugins
#
# OpenCode 会自动发现该目录下的插件包（与 .opencode/plugins/ 同一套布局），
# 因此本脚本不改 opencode.json，也不动该目录里其他来源的插件。
#
# 幂等，可反复执行。只管理仓库中存在的插件名，并顺手清理指向本仓库
# 但目标已不存在的悬空链接（重命名/删除插件的残留）。
#
# 用法：
#   scripts/link-plugins.sh                # 全量链接
#   scripts/link-plugins.sh --verify-only  # 只检查，不修改
#   scripts/link-plugins.sh --unlink       # 移除本仓库创建的链接（实体不受影响）
#   scripts/link-plugins.sh --include a,b  # 只处理部分插件
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PLUGINS_DIR="$REPO_ROOT/plugins"
BACKUP_ROOT="$HOME/.skills-migration-backup"
TARGET_DIR="$HOME/.config/opencode/plugins"

VERIFY_ONLY=0
UNLINK=0
INCLUDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=1; shift ;;
    --unlink) UNLINK=1; shift ;;
    --include) INCLUDE="${2:-}"; shift 2 ;;
    --include=*) INCLUDE="${1#--include=}"; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$PLUGINS_DIR" ]] || { echo "plugins 目录不存在: $PLUGINS_DIR" >&2; exit 1; }

# 收集含 package.json 的插件名
mapfile -t PLUGINS < <(for d in "$PLUGINS_DIR"/*/; do
  [[ -f "$d/package.json" ]] && basename "$d"
done)
for d in "$PLUGINS_DIR"/*/; do
  [[ -f "$d/package.json" ]] || echo "跳过 $(basename "$d")：缺少 package.json" >&2
done

if [[ -n "$INCLUDE" ]]; then
  IFS=',' read -ra WANT <<< "$INCLUDE"
  FILTERED=()
  for p in "${PLUGINS[@]}"; do
    for w in "${WANT[@]}"; do
      [[ "$p" == "$w" ]] && FILTERED+=("$p")
    done
  done
  PLUGINS=("${FILTERED[@]}")
fi
[[ ${#PLUGINS[@]} -gt 0 ]] || { echo "没有可处理的插件。" >&2; exit 1; }

normalize_path() {
  # 词法归一化：折叠 //、/./、/../，不要求路径存在（悬空链接的目标通常不存在）
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
  # 清理指向本仓库 plugins/ 但目标已不存在的悬空链接（重命名/删除插件的残留）。
  # 只处理指向本仓库 plugins/ 的符号链接；VerifyOnly 下只报告并计为异常。
  local p cur abs name w hit
  for p in "$TARGET_DIR"/*; do
    [[ -L "$p" ]] || continue
    cur="$(readlink "$p")"
    case "$cur" in
      /*) abs="$cur" ;;
      *) abs="$(dirname "$p")/$cur" ;;
    esac
    abs="$(normalize_path "$abs")"
    case "$abs" in
      "$PLUGINS_DIR"/*) ;;
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

echo "== $TARGET_DIR =="
if [[ ! -d "$TARGET_DIR" ]]; then
  if [[ $VERIFY_ONLY -eq 1 ]]; then
    echo "  缺失目录（VerifyOnly，不创建）: $TARGET_DIR" >&2
    failures=$((failures + 1))
  else
    mkdir -p "$TARGET_DIR"
    echo "  创建目录"
  fi
fi

for plugin in "${PLUGINS[@]}"; do
  link="$TARGET_DIR/$plugin"
  dest="$PLUGINS_DIR/$plugin"
  label="  [$plugin]"

  if [[ $UNLINK -eq 1 ]]; then
    if [[ ! -L "$link" ]]; then
      echo "$label 无链接，跳过"
      continue
    fi
    cur="$(readlink -f "$link")"
    if [[ "$cur" == "$(readlink -f "$dest")" ]]; then
      if [[ $VERIFY_ONLY -eq 1 ]]; then
        echo "$label 将被移除（VerifyOnly）"
        continue
      fi
      rm "$link"
      echo "$label 已移除"
    else
      echo "$label 是指向别处的链接（$cur），不动" >&2
    fi
    continue
  fi

  if [[ ! -e "$link" && ! -L "$link" ]]; then
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "$label 缺失（期望 -> $dest）" >&2
      failures=$((failures + 1))
      continue
    fi
    ln -s "$dest" "$link"
    echo "$label 已创建 -> $dest"
    continue
  fi

  if [[ -L "$link" && "$(readlink -f "$link")" == "$(readlink -f "$dest")" ]]; then
    echo "$label OK"
    [[ -f "$link/package.json" ]] || { echo "$label 链接存在但 package.json 不可读" >&2; failures=$((failures + 1)); }
    continue
  fi

  if [[ -L "$link" ]]; then
    cur="$(readlink -f "$link")"
    if [[ $VERIFY_ONLY -eq 1 ]]; then
      echo "$label 指向错误: $cur（期望 $dest）" >&2
      failures=$((failures + 1))
      continue
    fi
    rm "$link"
    ln -s "$dest" "$link"
    echo "$label 已纠正 -> $dest"
    continue
  fi

  # 走到这里: link 路径上是实体目录/文件, 备份到 plugins 目录之外再替换为 symlink
  if [[ $VERIFY_ONLY -eq 1 ]]; then
    echo "$label 是实体目录/文件，需备份后替换为链接" >&2
    failures=$((failures + 1))
    continue
  fi
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$BACKUP_ROOT/$stamp/opencode-plugins/$plugin"
  mkdir -p "$(dirname "$backup")"
  [[ -e "$backup" ]] && rm -rf "$backup"
  mv "$link" "$backup"
  ln -s "$dest" "$link"
  echo "$label 实体已备份到 $backup，链接已创建"
done

clean_stale_links

if [[ $VERIFY_ONLY -eq 1 ]]; then
  if [[ $failures -gt 0 ]]; then
    echo "校验发现 $failures 处异常，见上。" >&2
    exit 1
  fi
  echo "全部插件链接正常。"
fi
