#!/usr/bin/env bash
# preflight.sh —— 开发环境体检脚本
#
# 用途:在动手写代码之前,检查本机是否具备对应技术栈的工具链,
#       并按选定的应用形态给出"缺什么、怎么装"的清单。
#
# 用法:
#   ./scripts/preflight.sh                      # 自动探测系统并检查通用工具
#   ./scripts/preflight.sh --form cli --lang python
#   ./scripts/preflight.sh --form gui --lang rust --strict
#   ./scripts/preflight.sh --mirror china       # 附带国内镜像配置提示
#   ./scripts/preflight.sh --json               # 机器可读输出,便于脚本消费
#
# 退出码:0 = 全部就绪;1 = 缺少必需工具;2 = 参数用法错误。
#
# 规范:通过 shellcheck 与 shfmt -i 2 -ci 检查。

set -Eeuo pipefail
IFS=$'\n\t'

# ---------- 可配置项 ----------
FORM="auto"        # cli | script | tui | gui | web | hybrid | auto
LANG_STACK="auto"  # python | go | rust | node | auto
MIRROR=""          # china | ""
STRICT=0           # 1 = 把"建议安装"也当作失败
JSON=0             # 1 = 输出 JSON

# ---------- 输出工具 ----------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'
  C_OK=$'\033[32m'
  C_WARN=$'\033[33m'
  C_ERR=$'\033[31m'
  C_DIM=$'\033[2m'
  C_BOLD=$'\033[1m'
else
  C_RESET="" C_OK="" C_WARN="" C_ERR="" C_DIM="" C_BOLD=""
fi

MISSING_REQUIRED=0
MISSING_OPTIONAL=0
JSON_ITEMS=""

# log:写往 stderr,保证 stdout 只输出结果(便于 --json 被管道消费)
log() { printf '%s\n' "$*" >&2; }

json_escape() {
  # 转义反斜杠、双引号与制表符,并裁掉过长内容(版本串可能很长)
  printf '%s' "${1:0:120}" |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' |
    tr '\n\t' '  '
}

record() {
  # record <status> <name> <detail> <hint>
  local status="$1" name="$2" detail="$3" hint="$4"
  if [ "$JSON" -eq 1 ]; then
    local item
    item=$(printf '{"status":"%s","name":"%s","detail":"%s","hint":"%s"}' \
      "$status" "$(json_escape "$name")" "$(json_escape "$detail")" "$(json_escape "$hint")")
    if [ -z "$JSON_ITEMS" ]; then
      JSON_ITEMS="$item"
    else
      JSON_ITEMS="${JSON_ITEMS},${item}"
    fi
    return 0
  fi
  case "$status" in
    ok) printf '  %s[OK]%s   %-18s %s\n' "$C_OK" "$C_RESET" "$name" "${C_DIM}${detail}${C_RESET}" ;;
    warn) printf '  %s[缺]%s  %-18s %s\n' "$C_WARN" "$C_RESET" "$name" "$hint" ;;
    err) printf '  %s[必需]%s %-18s %s\n' "$C_ERR" "$C_RESET" "$name" "$hint" ;;
    info) printf '  %s[..]%s   %-18s %s\n' "$C_DIM" "$C_RESET" "$name" "$detail" ;;
  esac
}

# check_tool <命令名> <是否必需 required|optional> <缺失时的安装提示>
check_tool() {
  local cmd="$1" required="$2" hint="$3" version=""
  if command -v "$cmd" >/dev/null 2>&1; then
    version="$("$cmd" --version 2>&1 | head -n 1 || true)"
    record ok "$cmd" "$version" ""
    return 0
  fi
  if [ "$required" = "required" ]; then
    record err "$cmd" "" "$hint"
    MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
  else
    record warn "$cmd" "" "$hint"
    MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
  fi
  return 0
}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------- 参数解析 ----------
while [ $# -gt 0 ]; do
  case "$1" in
    --form)
      [ $# -ge 2 ] || { log "错误:--form 需要一个取值"; exit 2; }
      FORM="$2"; shift 2 ;;
    --form=*) FORM="${1#*=}"; shift ;;
    --lang)
      [ $# -ge 2 ] || { log "错误:--lang 需要一个取值"; exit 2; }
      LANG_STACK="$2"; shift 2 ;;
    --lang=*) LANG_STACK="${1#*=}"; shift ;;
    --mirror)
      [ $# -ge 2 ] || { log "错误:--mirror 需要一个取值"; exit 2; }
      MIRROR="$2"; shift 2 ;;
    --mirror=*) MIRROR="${1#*=}"; shift ;;
    --strict) STRICT=1; shift ;;
    --json) JSON=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) log "错误:未知参数 '$1'(用 --help 查看用法)"; exit 2 ;;
  esac
done

case "$FORM" in
  cli | script | tui | gui | web | hybrid | auto) ;;
  *) log "错误:--form 取值无效:'$FORM'"; exit 2 ;;
esac
case "$LANG_STACK" in
  python | go | rust | node | auto) ;;
  *) log "错误:--lang 取值无效:'$LANG_STACK'"; exit 2 ;;
esac

# ---------- 系统探测 ----------
OS="unknown"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
case "$(uname -s 2>/dev/null || echo unknown)" in
  Linux) OS="linux" ;;
  Darwin) OS="macos" ;;
  MINGW* | MSYS* | CYGWIN*) OS="windows" ;;
esac

pkg_hint() {
  case "$OS" in
    macos) printf 'brew install %s' "$1" ;;
    linux) printf 'sudo apt install %s  (或对应发行版包管理器)' "$1" ;;
    windows) printf 'scoop install %s  (或 winget install %s)' "$1" "$1" ;;
    *) printf '请按 %s 官方文档安装' "$1" ;;
  esac
}

if [ "$JSON" -eq 0 ]; then
  log ""
  log "${C_BOLD}开发环境体检${C_RESET}  系统:${OS}/${ARCH}"
  log "${C_DIM}---------------------------------------------${C_RESET}"
fi

# ---------- 通用工具 ----------
if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[通用]${C_RESET}"; fi
check_tool git required "$(pkg_hint git)"
check_tool curl required "$(pkg_hint curl)"
check_tool make optional "$(pkg_hint make)"
check_tool shellcheck optional "$(pkg_hint shellcheck)"
check_tool shfmt optional "$(pkg_hint shfmt)"
check_tool actionlint optional "$(pkg_hint actionlint)"

# ---------- 按语言 ----------
if [ "$LANG_STACK" = "auto" ] || [ "$LANG_STACK" = "python" ]; then
  if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[Python]${C_RESET}"; fi
  check_tool python3 required "见 https://www.python.org 或用 uv 安装"
  check_tool uv optional "curl -LsSf https://astral.sh/uv/install.sh | sh"
  check_tool pipx optional "$(pkg_hint pipx)"
  check_tool ruff optional "uv tool install ruff  /  pipx install ruff"
  check_tool mypy optional "uv tool install mypy"
fi

if [ "$LANG_STACK" = "auto" ] || [ "$LANG_STACK" = "node" ]; then
  if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[Node / TypeScript]${C_RESET}"; fi
  check_tool node required "https://nodejs.org 或用 fnm/volta 管理版本"
  check_tool npm required "随 Node 一同安装"
  check_tool pnpm optional "corepack enable  /  npm i -g pnpm"
fi

if [ "$LANG_STACK" = "auto" ] || [ "$LANG_STACK" = "go" ]; then
  if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[Go]${C_RESET}"; fi
  check_tool go optional "https://go.dev/dl 或 $(pkg_hint golang)"
  check_tool goreleaser optional "$(pkg_hint goreleaser)"
fi

if [ "$LANG_STACK" = "auto" ] || [ "$LANG_STACK" = "rust" ]; then
  if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[Rust]${C_RESET}"; fi
  check_tool rustc optional "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
  check_tool cargo optional "随 rustup 一同安装"
fi

# ---------- 按形态 ----------
case "$FORM" in
  gui | hybrid)
    if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[桌面 GUI 专项]${C_RESET}"; fi
    if [ "$OS" = "linux" ]; then
      # Tauri 在 Linux 需要 WebKitGTK 与构建依赖
      check_tool pkg-config required "$(pkg_hint pkg-config)"
      if ! ldconfig -p 2>/dev/null | grep -q webkit2gtk; then
        record warn "webkit2gtk" "" "sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev"
        MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
      else
        record ok "webkit2gtk" "已检测到" ""
      fi
    fi
    if [ "$OS" = "macos" ]; then
      check_tool xcode-select required "xcode-select --install"
      record info "codesign / notarytool" "需要 Apple Developer 账号才能对外分发" "developer.apple.com"
    fi
    ;;
  web)
    if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[Web 专项]${C_RESET}"; fi
    check_tool docker optional "https://docs.docker.com/get-docker/"
    record info "本地端口" "本地 Web UI 应只绑定 127.0.0.1" "不要使用 0.0.0.0"
    ;;
  cli | script | tui)
    if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[命令行专项]${C_RESET}"; fi
    record info "换行符" "仓库需有 .gitattributes: * text=auto eol=lf" "否则 .sh 在 Windows 检出后不可执行"
    record info "编码" "Python 在 Windows 控制台需显式 UTF-8" "入口处重配 stdout 编码"
    ;;
esac

# ---------- 国内镜像提示 ----------
if [ "$MIRROR" = "china" ]; then
  if [ "$JSON" -eq 0 ]; then log "${C_BOLD}[国内镜像配置提示]${C_RESET}"; fi
  record info "npm" "npm config set registry https://registry.npmmirror.com" ""
  record info "PyPI" "pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple" ""
  record info "Go" "go env -w GOPROXY=https://goproxy.cn,direct" ""
  record info "Homebrew" "设置 HOMEBREW_API_DOMAIN 与 HOMEBREW_BOTTLE_DOMAIN 指向镜像" ""
  record info "GitHub 下载" "可用镜像代理包裹原链接,使用前需实测可用性" ""
fi

# ---------- 汇总 ----------
if [ "$JSON" -eq 1 ]; then
  printf '{"os":"%s","arch":"%s","form":"%s","lang":"%s","missing_required":%d,"missing_optional":%d,"items":[%s]}\n' \
    "$OS" "$ARCH" "$FORM" "$LANG_STACK" "$MISSING_REQUIRED" "$MISSING_OPTIONAL" "$JSON_ITEMS"
else
  log "${C_DIM}---------------------------------------------${C_RESET}"
  if [ "$MISSING_REQUIRED" -gt 0 ]; then
    log "${C_ERR}${C_BOLD}体检未通过${C_RESET}:缺少 ${MISSING_REQUIRED} 个必需工具(标记为 [必需])。"
    exit 1
  fi
  if [ "$STRICT" -eq 1 ] && [ "$MISSING_OPTIONAL" -gt 0 ]; then
    log "${C_WARN}${C_BOLD}严格模式未通过${C_RESET}:缺少 ${MISSING_OPTIONAL} 个建议工具。"
    exit 1
  fi
  log "${C_OK}${C_BOLD}体检通过${C_RESET}:必需工具齐备;建议工具缺失 ${MISSING_OPTIONAL} 个(不影响开工)。"
fi
