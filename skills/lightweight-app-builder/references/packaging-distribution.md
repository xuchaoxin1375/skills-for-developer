# 打包、签名与分发

> 何时读本文件:阶段六,需要把做好的程序交到别人手上时。
>
> 交付的唯一标准:**对方按你给的一条命令或一次双击就能用起来,并且你能在多台设备上重复这个过程。**

## 目录

- 交付形态谱系(从轻到重)
- 打包命令与工具矩阵
- 交叉编译能力
- 产物命名与校验
- 签名与公证(不可跳过的部分)
- 分发渠道清单
- 应用商店(进阶)
- 自动更新
- CI 发布流水线(三平台矩阵)
- 一键安装脚本的设计规范(含完整 install.sh 骨架)
- 版本与发布规范
- 国内网络加速与镜像
- 发布清单

## 交付形态谱系(从轻到重)

**选择规则:从左往右,选第一个能满足"目标用户能独立完成安装"的形态。**用户不懂技术,就直接跳到安装包或包管理器,不要指望他配环境变量。

| 层级 | 交付物 | 用户操作 | 适用 | 成本 |
| --- | --- | --- | --- | --- |
| L0 | 一个脚本文件 | 拷过去,自己想办法跑 | 只有你自己/同环境同事 | 极低 |
| L1 | **一键安装脚本** | 复制一行 `curl ... \| bash` | 开发者、运维 | 低 |
| L2 | **单文件可执行程序** | 下载后双击或直接运行 | 普通用户,跨平台工具的甜点 | 中 |
| L3 | 平台安装包(`.msi`/`.dmg`/`.deb`/`.AppImage`) | 双击安装,可卸载 | 正式对外的桌面软件 | 中高 |
| L4 | 包管理器条目(Homebrew/Scoop/winget/apt/PyPI/npm) | `brew install xxx` | 面向开发者社区分发 | 中,但维护需持续 |
| L5 | 应用商店(Mac App Store / Microsoft Store) | 商店搜索安装 | 面向大众消费者 | 高,审核与年费 |

**推荐策略**:个人与小团队工具做到 **L2 + L4** 即可覆盖绝大多数场景;只有面向非技术终端用户销售时才上 L3/L5。

## 打包命令与工具矩阵

| 语言/栈 | 打包命令 | 产物 | 备注 |
| --- | --- | --- | --- |
| **Go** | `goreleaser release --clean`,或 `go build -trimpath -ldflags "-s -w"` | 全平台单文件二进制 + Homebrew 配方 + Scoop 清单 + `.deb`/`.rpm` + 校验和 | 一条 `goreleaser release` 搞定,CI 里跑最省心 |
| **Rust** | `cargo build --release`,配 `cargo-dist` 或 `cross` | 全平台二进制 + 安装脚本 + 安装包 | Tauri 项目直接用 `tauri build` |
| **Node/TS** | `bun build --compile --target=bun-linux-x64 ./cli.ts`(自带运行时);传统方案 `pkg`、`nexe` | 单文件 | `pkg`/`nexe` 社区维护度一般,单文件方案对原生模块支持有限,优先考虑 Bun 方案 |
| **Python(CLI)** | `pyinstaller --onefile app.py`;源码分发走 `pipx` | 单文件可执行文件或 pip 包 | PyInstaller 产物在 Windows 上有一定**杀软误报**概率;Nuitka 编译更慢但更像"真程序";产物**体积较大** |
| **Python(现代)** | **uv** + `uv tool install` | 隔离环境的命令行工具 | `uv` 同时是极快的包管理器与 Python 版本管理器,2025 年后新项目推荐 |
| **Python(桌面)** | `PyInstaller` + `briefcase` | 系统安装包 | 面向普通用户的桌面应用 |
| **Tauri** | `tauri build` + `tauri-action`(CI) | `.msi`/`.exe`(NSIS)、`.dmg`/`.app`、`.deb`/`.rpm`/`.AppImage` | v2 可同时产出 iOS/Android 包 |
| **Electron** | **Electron Forge**(官方维护)或 **electron-builder**(社区,下载量最大,内置自动更新) | 同上 | 二者选一,不要混用 |
| **容器化** | Docker + `docker buildx` | 多架构镜像 | 适合服务端;桌面工具用容器分发对普通用户不友好 |

**实践建议**:发布流水线用 GoReleaser(支持 Go、Bun 构建以及 nFPM 生成 deb/rpm/apk)或 `cargo-dist` 这类专用工具,不要手写一堆 shell 拼装。工具会把校验和、签名、变更日志一并生成。

## 交叉编译能力

| 技术栈 | 能否在本机编出其他平台产物 | 说明 |
| --- | --- | --- |
| Go | 能 | 原生支持 `GOOS`/`GOARCH`,含 arm64 |
| Rust | 基本能 | 纯 Rust 依赖可用 `cross` 或 `cargo-zigbuild`,涉及 C 依赖就难 |
| Bun/Node | 能 | `--target` 指定平台 |
| Python | **不能** | PyInstaller 只能在目标平台上打包 |
| Tauri | 部分能 | Linux 与 Windows 可交叉,macOS 签名必须在 macOS 上做 |

**结论**:只要技术栈里有 Python 或 macOS 签名,就必须用 **GitHub Actions 三平台矩阵**(`macos-latest`、`ubuntu-latest`、`windows-latest`)来产出,不要幻想本机一条命令通吃。

## 产物命名与校验

命名规范固定为 `{名称}-{版本}-{系统}-{架构}.{后缀}`,例如 `mytool-1.2.0-windows-x64.zip`、`mytool-1.2.0-linux-arm64.tar.gz`;架构必须写明 `x64` 或 `arm64`,不要只写 `64位`。规则:

- 版本用语义化版本(SemVer):主版本.次版本.修订号,分别对应不兼容变更、新增功能、缺陷修复(详见"版本与发布规范")。
- 每次发布生成 `checksums.txt`,内含各产物的 SHA256 值,并随产物一同发布。
- 安装脚本下载产物后**必须先校验哈希再执行**,这一步永远不要省(`sha256sum -c checksums.txt`)。

## 签名与公证(不可跳过的部分)

**核心认知**:签名与公证是**平台绑定**的 —— 你无法在 Linux 上产出"签好名的 macOS 包"。CI 必须用三平台矩阵。

**macOS:一条不可拆的链**

代码签名 → 公证(notarization) → 装订票据(staple) → 才能静默自动更新。

| 步骤 | 命令要点 | 说明 |
| --- | --- | --- |
| 签名 | `codesign --options runtime --sign "Developer ID Application: <名字> (<TEAMID>)" MyApp.app` | `--options runtime` 启用**加固运行时(Hardened Runtime)**,是公证的前置条件 |
| 验证签名 | `codesign --verify --deep --strict --verbose=2 MyApp.app` | 打包后自检 |
| Gatekeeper 自检 | `spctl --assess --type execute -vv MyApp.app` | 期望输出 `accepted` 与 `source=Developer ID` |
| 打 zip | `ditto -c -k --keepParent MyApp.app MyApp.zip` | **不要用 Finder 的"压缩"**,会丢失资源叉与符号链接 |
| 提交公证 | `xcrun notarytool submit MyApp.zip --apple-id <邮箱> --team-id <TEAMID> --password <应用专用密码> --wait` | 成功返回 `status: Accepted` |
| 装订票据 | `xcrun stapler staple MyApp.app` | 把公证结果附到应用本体,离线也能通过校验 |

关键占位符解释:

| 占位符 | 含义 | 从哪拿 |
| --- | --- | --- |
| `Developer ID Application` | 证书类型,**用于 App Store 之外分发**;`Apple Development` 只能本机调试 | Apple Developer 账号(个人 99 美元/年) |
| `<TEAMID>` | 团队标识,10 位字符 | developer.apple.com 的 Membership 页 |
| `--options runtime` | 启用加固运行时 | 固定写法 |
| 应用专用密码 | 不是 Apple ID 登录密码 | appleid.apple.com 生成 |

**未公证的后果**(必须提前告知用户):macOS 会弹"无法打开,因为无法验证开发者",或在 Dock 里跳一下就消失。绕过方式是右键 → 打开,或在"系统设置 → 隐私与安全性"里点"仍要打开",但**普通用户不会做**,所以别指望写文档解决。

**Windows**

| 事项 | 说明 |
| --- | --- |
| **Authenticode 签名** | 需要代码签名证书。2023 年后 CA 要求私钥存放在硬件 token 或云 HSM 中,CI 里通常走云签名服务(如 Azure Trusted Signing) |
| **SmartScreen** | 即使签了名,新软件仍可能因"信誉不足"被警告,需要累积下载量;未签名则几乎必被拦 |
| **安装包格式** | `.msi`(企业部署友好)或 NSIS `.exe`(Tauri/electron-builder 默认,体验更好) |
| **无签名的现实做法** | 提供 SHA256 校验和 + 图文说明"更多信息 → 仍要运行";面向企业用户时提前告知需要 IT 加白名单。证书是真实成本,第一阶段不签名可以,但须写进决策记录并主动告知风险 |

**Linux**

一般**不需要签名**,但要注意:`.deb`/`.rpm` 需要正确的依赖声明(如 Tauri 依赖 `webkit2gtk`、`libayatana-appindicator3`);`AppImage` 免安装但需要 `FUSE`(新系统上可能要 `--appimage-extract-and-run`);Flatpak/Snap 走各自商店,沙箱权限需显式声明。

## 分发渠道清单

| 渠道 | 平台 | 用户命令 | 维护成本 |
| --- | --- | --- | --- |
| **GitHub Releases** | 全平台 | 手动下载 | 低,是所有渠道的基础 |
| **Homebrew Tap(自建仓库)** | macOS/Linux | `brew install <user>/tap/<formula>` | 低,GoReleaser 可自动生成 |
| **Scoop Bucket(自建)** | Windows | `scoop bucket add <name> <url>` 后 `scoop install <app>` | 低,自动生成清单 |
| **apt / dnf 仓库** | Debian/Fedora 系 | `apt install <app>` | 中,要维护仓库与 GPG 签名 |
| **PyPI** | 跨平台 Python | `pipx install <pkg>` / `uv tool install <pkg>` | 低 |
| **npm** | 跨平台 Node | `npm i -g <pkg>` | 低,记得 `files` 字段控制包内容 |
| **crates.io** | Rust | `cargo install <crate>` | 低 |
| **Go** | 跨平台 | `go install 模块路径@版本` | 极低,打好 tag 就能装 |
| **Docker Hub / GHCR** | 服务端 | `docker run <image>` | 低 |

**建议组合**:面向开发者 → GitHub Releases + Homebrew Tap + Scoop Bucket(三者 GoReleaser 都能自动生成);面向普通用户 → 官网下载页 + 平台安装包 + 清晰的"被拦截怎么办"说明。包管理器安装是开发者工具口碑的分水岭:"一条命令装好"远胜"去网页下载解压改 PATH"。

## 应用商店(进阶)

官方商店渠道维护成本高,有真实用户量再进,一次只进一个:Homebrew Cask(GUI 应用,`brew install --cask <app>`,需向官方 casks 仓库提 PR);winget(`winget install <Publisher.App>`,需向 `microsoft/winget-pkgs` 提 PR 并等审核);Flathub(`flatpak install flathub <app-id>`,需 AppStream 元数据与已签名构建);Snap Store(`snap install <app>`,沙箱权限需显式声明)。

## 自动更新

| 方案 | 说明 |
| --- | --- |
| Tauri `plugin-updater` | 需要一个静态 JSON 清单 + 签名密钥对(`tauri signer generate`),清单可托管在 GitHub Releases |
| Electron `electron-updater` | 支持 GitHub、S3、通用 HTTP 源;**macOS 必须已签名才能静默更新**(Squirrel.Mac 的硬性要求) |
| CLI 自更新 | 提供 `mytool self-update` 子命令,检查最新版本并替换自身;Windows 上替换正在运行的可执行文件需要先改名再写入 |
| 包管理器 | 交给用户 `brew upgrade` / `scoop update`,自己只需保证配方更新 |
| 最低要求 | 即使不做自动更新,也要有 `mytool --version` 与**启动时的新版本提示**(不强制打断) |

更新机制三条硬规则:**更新通道必须可关闭**;**更新源地址可配置**,便于在国内换成镜像;**更新失败不能破坏现有版本**(下载到临时文件、校验、原子替换,失败保留旧版)。

## CI 发布流水线(三平台矩阵)

```yaml
name: Release
on:
  push:
    tags: ["v*"]
permissions:
  contents: write          # 需要写权限才能创建 Release 并上传产物
jobs:
  release:
    strategy:
      fail-fast: false     # 一个平台失败不要连带取消其他平台
      matrix:
        include:
          - os: macos-latest      # Apple Silicon
            target: aarch64-apple-darwin
          - os: macos-13          # Intel
            target: x86_64-apple-darwin
          - os: windows-latest
            target: x86_64-pc-windows-msvc
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      # 之后:装工具链 → 构建 → 签名 → 上传到 Release
```

字段解释:

| 字段 | 含义 |
| --- | --- |
| `on.push.tags` + `permissions` | 只有 `v*` 标签触发发布,并显式声明最小写权限 |
| `strategy.matrix.include` + `runs-on` | 逐个列出"系统 + 目标三元组",运行时以 `${{ matrix.os }}` 代入 |
| `fail-fast: false` | 单平台失败不连带取消其余平台,一次拿到能用的产物 |
| `macos-latest` / `macos-13` | 前者 Apple Silicon,后者 Intel;双架构 Mac 两个都跑 |

**密钥管理**:签名证书、公证凭据、Token 一律放 GitHub Secrets,**绝不入库**;在日志中确保不会打印出来。

## 一键安装脚本的设计规范

用户明确要求"可自动化、可脚本化、能在多台设备复用",所以安装脚本要按产品标准来写,而不是随手糊一个。

**参数设计(必须支持)**

| 参数 | 作用 | 默认值 |
| --- | --- | --- |
| `--version <ver>` | 安装指定版本,支持 `latest` | `latest` |
| `--prefix <dir>` | 安装目录 | 用户可写目录(见下) |
| `--platform <os>` / `--arch <arch>` | 手动覆盖自动探测结果 | 自动探测 |
| `--mirror <url>` | 指定下载镜像(国内网络关键) | 官方源 |
| `--dry-run` | 只打印将要做什么,不实际写入 | 关闭 |
| `--force` | 覆盖已存在安装 | 关闭 |
| `--uninstall` | 干净卸载 | 关闭 |
| `-h` / `--help` | 用法与示例 | — |

**安装目录的选择**

| 系统 | 推荐目录 | 理由 |
| --- | --- | --- |
| macOS / Linux | `$HOME/.local/bin` | 属于 XDG 惯例,**无需 sudo**,用户有写权限 |
| Linux(全机安装) | `/usr/local/bin` | 需要 sudo,应作为可选项而非默认 |
| Windows | `%LOCALAPPDATA%\Programs\<app>` | 无需管理员权限,符合微软对每用户安装的指引 |

安装完成后必须**检查该目录是否在 `PATH` 中**,不在则打印精确的追加指令(区分 bash/zsh/fish/PowerShell),而不是让用户自己猜。

**脚本骨架**

```bash
#!/usr/bin/env bash
# install.sh —— mytool 一键安装脚本
# 用法:
#   curl -fsSL https://example.com/install.sh | bash -s -- --version 1.2.0
#   curl -fsSL https://example.com/install.sh | bash -s -- --dry-run --mirror https://gh-proxy.com
set -Eeuo pipefail
IFS=$'\n\t'

REPO="yourname/mytool"
VERSION="latest"
PREFIX=""
MIRROR=""
DRY_RUN=0
FORCE=0

log() { printf '%s\n' "$*" >&2; }
die() { log "错误:$*"; exit 1; }
run() { if [ "$DRY_RUN" -eq 1 ]; then log "[dry-run] $*"; else eval "$@"; fi; }

# 参数解析:支持 --key value 与 --key=value 两种写法
while [ $# -gt 0 ]; do
  case "$1" in
    --version)  VERSION="${2:-}"; shift 2 ;;
    --version=*) VERSION="${1#*=}"; shift ;;
    --prefix)   PREFIX="${2:-}"; shift 2 ;;
    --prefix=*) PREFIX="${1#*=}"; shift ;;
    --mirror)   MIRROR="${2:-}"; shift 2 ;;
    --mirror=*) MIRROR="${1#*=}"; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --force)    FORCE=1; shift ;;
    -h|--help)  sed -n '2,6p' "$0"; exit 0 ;;
    *) die "未知参数:$1(用 --help 查看用法)" ;;
  esac
done

detect_platform() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$os" in
    linux)  OS=linux ;;
    darwin) OS=darwin ;;
    msys*|mingw*|cygwin*) OS=windows ;;
    *) die "不支持的系统:$os" ;;
  esac
  case "$arch" in
    x86_64|amd64) ARCH=x86_64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) die "不支持的架构:$arch" ;;
  esac
}

resolve_version() {
  [ "$VERSION" = "latest" ] || return 0
  VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep -m1 '"tag_name"' | cut -d'"' -f4)"
  [ -n "$VERSION" ] || die "无法获取最新版本号"
}

download_url() {
  local base="https://github.com/${REPO}/releases/download/${VERSION}"
  if [ -n "$MIRROR" ]; then base="${MIRROR%/}/${base#https://}"; fi
  printf '%s/%s' "$base" "mytool_${VERSION}_${OS}_${ARCH}.tar.gz"
}

main() {
  detect_platform
  resolve_version
  PREFIX="${PREFIX:-$HOME/.local}"
  local url dest="$PREFIX/bin"
  url="$(download_url)"
  log "平台:${OS}/${ARCH}  版本:${VERSION}"
  log "下载地址:${url}"
  log "安装到:${dest}"

  [ -d "$dest" ] || run "mkdir -p '$dest'"
  if [ -e "$dest/mytool" ] && [ "$FORCE" -eq 0 ]; then
    die "已存在安装,加 --force 覆盖"
  fi
  local tmp; tmp="$(mktemp -d)"
  run "curl -fL --retry 3 --connect-timeout 15 -o '$tmp/pkg.tar.gz' '$url'"
  run "tar -xzf '$tmp/pkg.tar.gz' -C '$tmp'"
  run "install -m 0755 '$tmp/mytool' '$dest/mytool'"
  run "rm -rf '$tmp'"

  case ":$PATH:" in
    *":$dest:"*) log "完成。直接运行:mytool --help" ;;
    *) log "完成。但 $dest 不在 PATH 中,请追加到你的 shell 配置:"
       log "  bash/zsh: export PATH=\"$dest:\$PATH\""
       log "  fish:     fish_add_path $dest" ;;
  esac
}

main "$@"
```

**脚本写作纪律**:

- 安全习惯:变量展开加引号(`"$dest"`),`mktemp -d` 代替固定临时名,网络调用带 `--retry`、`--connect-timeout`、`-f`。
- 关键步骤前打印"将要做什么",失败时给**可执行的下一步建议**;发布前用 shellcheck 与 shfmt 检查。
- 关于 `curl | bash` 的安全性争议:更稳妥的做法是让用户先下载再执行,或提供 `--dry-run` 与校验和验证。文档里应给出校验方式(`sha256sum -c checksums.txt`)。

**Windows 侧对应脚本**

不要只提供 `.sh`。给 PowerShell 版本 `install.ps1`,并注意:

- PowerShell 写法:用 `powershell -ExecutionPolicy Bypass -File install.ps1` 执行,路径用 `$env:LOCALAPPDATA` 展开,PATH 用 `[Environment]::SetEnvironmentVariable(..., "User")` 写用户级变量并提示重开终端。
- `.ps1` 文件保存为 **UTF-8 with BOM**,否则 Windows PowerShell 5.1 会把中文字符串解析成乱码。

**卸载必须干净**:卸载脚本列出所有写入位置并逐一清理 —— 可执行文件所在目录(如 `~/.local/bin`);配置目录(Windows `%APPDATA%`、macOS `~/Library/Application Support`、Linux `~/.config`);缓存与日志目录;定时任务、开机自启项、Shell 补全注册、PATH 修改记录。**不做静默修改**:凡改动用户 PATH 或注册系统服务,先打印将要做的变更,并支持 `--dry-run`。

## 版本与发布规范

| 项 | 约定 |
| --- | --- |
| **版本号** | 语义化版本 `主.次.修订`(`MAJOR.MINOR.PATCH`):破坏性变更升主版本,新增功能升次版本,修 bug 升修订号 |
| 0.x 阶段 | 表示接口尚不稳定,允许在次版本里做破坏性变更 |
| **Git 标签** | `v1.2.0` 形式,与发布产物一一对应 |
| **变更日志** | 维护 `CHANGELOG.md`,按版本分组,写"用户能感知的变化"而不是 commit 标题 |
| 提交信息 | 采用 Conventional Commits(`feat:` / `fix:` / `docs:` / `chore:`),可自动生成变更日志 |
| 产物完整性 | 见"产物命名与校验":每次发布附 `checksums.txt`(SHA256) |
| 预发布 | 用 `v1.3.0-rc.1` 走测试通道,不覆盖 `latest` 指针 |

## 国内网络加速与镜像

| 目标 | 做法 |
| --- | --- |
| GitHub Release 下载慢 | 配置当前可用的镜像代理包裹原链接(镜像代理示例见上文 install.sh 用法注释);**镜像可用性会变化,引用前务必实测**,且生产环境不应长期依赖第三方镜像 |
| 自建分发 | 把产物同步到国内可达的对象存储(阿里云 OSS、腾讯云 COS、七牛),自建下载页,这是**最可靠**的做法 |
| npm | `npm config set registry https://registry.npmmirror.com` |
| PyPI | `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| Homebrew | 设置 `HOMEBREW_API_DOMAIN`、`HOMEBREW_BOTTLE_DOMAIN` 指向中科大或清华镜像 |
| Go 模块 | `go env -w GOPROXY=https://goproxy.cn,direct` |
| Cargo | 在 `~/.cargo/config.toml` 配置 `rsproxy.cn` 或中科大源 |
| Docker | 配置可用的 registry mirror;公共镜像加速地址变动频繁,以当前实测为准 |

代理场景分平台说明:`*nix` 用 `export https_proxy=http://127.0.0.1:7890`,Windows PowerShell 用 `$env:https_proxy="http://127.0.0.1:7890"`,并提醒 Git 与终端可能需要分别设置。把以上配置写进项目 README 的"国内环境"一节,并让安装脚本支持 `--mirror`。

**给用户的诚实建议**:镜像只是权宜之计。如果这个工具会被多人长期使用,请把安装脚本的 `--mirror` 参数和你自己托管的下载源写进 README,而不是让每个人各自想办法。

## 发布清单

发布前逐项打勾,任何一项未通过都不发版(质量门禁的依据见上文各节):

- 三个平台的产物都构建成功,且都能启动。
- `--version` 输出与发布的 tag 一致。
- 安装脚本在新装系统(或干净容器)上从零跑通。
- 卸载脚本执行后无残留文件。
- `checksums.txt` 生成并随产物一同发布。
- `README.md` 的安装命令已同步为新版本。
- 变更日志写清新增、修复、破坏性变更三类。
- 自动更新从旧版本升级到新版本实测通过。
- 标签打在正确的提交上,且与产物内嵌版本号一致。
