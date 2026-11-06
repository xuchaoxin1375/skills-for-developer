# 平台安装命令

命令中的 `<version>` 用实际版本替换；镜像地址是候选，使用前按当次网络核验，装不到就回退官方源。改 PATH、装全局包、动执行策略前先说明影响。

## Node 二进制镜像

MSI、ZIP、fnm、nvm-windows 默认都从 `nodejs.org/dist` 取包，可换国内镜像：

| 镜像 | 地址 | 适用 | 备注 |
| --- | --- | --- | --- |
| npmmirror | `https://npmmirror.com/mirrors/node/` | fnm、nvm-windows、手工下载 | 速度快；实测未提供 `SHASUMS256.txt` |
| 清华 TUNA | `https://mirrors.tuna.tsinghua.edu.cn/nodejs-release/` | MSI、ZIP、fnm | 完整镜像，提供 `SHASUMS256.txt` |
| 腾讯云 | `https://mirrors.cloud.tencent.com/nodejs-release/` | MSI、ZIP、fnm | 腾讯云内网或华南地区可优先 |
| 华为云 | `https://mirrors.huaweicloud.com/nodejs/` | 企业网络、华为云 | 站点策略会变；实测有安装包但缺校验文件 |

选择顺序：**先看是否提供校验文件，再看速度**。交给 fnm/nvm 直接下载时镜像只影响下载地址；手工装 MSI/ZIP 至少第一次用官方或 TUNA 的 `SHASUMS256.txt` 核对。

## Windows

### 官方安装器

```powershell
winget install --id OpenJS.NodeJS.LTS -e
# 或下载官方 MSI 后双击，安装路径避免中文、空格和过深目录
```

安装后**新开终端**，PATH 变更不会刷新到已打开的进程。

```powershell
node -v
npm -v
where.exe node
npm config get prefix
```

`npm config get prefix` 若指向 `C:\Program Files\nodejs`，`npm i -g` 会报 `EPERM`：

```powershell
npm config set prefix "$env:APPDATA\npm"
```

并把 `%APPDATA%\npm` 加回用户 PATH，重新打开终端。不要长期用管理员终端绕过。

卸载走“设置 → 应用 → 已安装的应用”；之后检查用户 PATH 是否残留 `C:\Program Files\nodejs`，全局工具在 `%APPDATA%\npm`，缓存目录为 `%LOCALAPPDATA%\npm-cache`。

### fnm

前置权限二选一：

- 设置 → 系统 → 开发者选项（Windows 10 在“更新和安全”下），启用**开发者模式**。
- `secpol.msc` → 本地策略 → 用户权限分配 → **创建符号链接** → 加入当前用户，重启。

```powershell
winget install --id Schniz.fnm -e
fnm --version
```

`$PROFILE` 不存在时先建目录与文件：

```powershell
$profileDir = Split-Path $PROFILE
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }
notepad $PROFILE
```

在 profile 中加入两行，顺序不能反：

```powershell
$env:FNM_NODE_DIST_MIRROR = "https://npmmirror.com/mirrors/node"
fnm env --use-on-cd | Out-String | Invoke-Expression
```

镜像也可写成用户级变量，新终端生效：

```powershell
[Environment]::SetEnvironmentVariable("FNM_NODE_DIST_MIRROR", "https://npmmirror.com/mirrors/node", "User")
```

```powershell
fnm install --lts
fnm default <version>
fnm list
```

项目锁定版本：`node -v > .node-version`，或写兼容 nvm 的 `.nvmrc`。用 Scoop 安装 fnm 时注意 `FNM_DIR` 可能位于 `current` 目录，升级会换掉版本目录，必要时改为稳定目录。

### nvm-windows

```powershell
nvm version                                                    # 先确认 v1 还是 v2
winget install --id AuthorSoftware.NVMWindows -e               # v2
winget install --id CoreyButler.NVMforWindows -e               # v1
```

镜像配置，v2：

```powershell
nvm config set node_mirror=https://npmmirror.com/mirrors/node
nvm config set npm_mirror=https://registry.npmmirror.com
nvm config get node_mirror
```

v1 使用独立命令，写入安装目录的 `settings.txt`：

```powershell
nvm node_mirror https://npmmirror.com/mirrors/node/
nvm npm_mirror https://npmmirror.com/mirrors/npm/
```

```powershell
nvm install lts
nvm use <version>
nvm list
```

nvm-windows 的默认版本就是最近一次 `nvm use` 切换到的版本，与 nvm-sh 的 `nvm alias default` 不同；v2 命名别名用 `nvm alias add <name> <version>`。`node_mirror` 只影响 Node 二进制，`npm_mirror` 不等于项目依赖使用的 registry。

### pnpm

```powershell
npm i -g pnpm
pnpm -v
where.exe pnpm.*
```

没有 Node 或要独立安装：

```powershell
Invoke-WebRequest https://get.pnpm.io/install.ps1 -UseBasicParsing | Invoke-Expression
```

独立脚本在 Windows 上可能被 Defender 拦截，装不上就回到 `npm i -g pnpm`。

## Linux / macOS

### fnm

```bash
brew install fnm                       # macOS
curl -fsSL https://fnm.vercel.app/install | bash   # Linux / macOS 脚本
```

shell 配置中加（以 bash/zsh 为例）：

```bash
export FNM_NODE_DIST_MIRROR="https://npmmirror.com/mirrors/node"
eval "$(fnm env --use-on-cd)"
```

```bash
fnm install --lts
fnm default <version>
fnm list
```

### 系统包管理器

`apt install nodejs`、`dnf install nodejs` 的版本常落后于当前 LTS，需要新版本时用 fnm、nvm-sh 或 NodeSource；`brew install node` 跟随最新 Current，需要 LTS 同样用 fnm。

### pnpm

```bash
npm i -g pnpm
# 或独立脚本
curl -fsSL https://get.pnpm.io/install.sh | sh -
```

## 校验安装包

```powershell
Get-FileHash .\node-<version>-x64.msi -Algorithm SHA256
Select-String -Path .\SHASUMS256.txt -Pattern 'node-<version>-x64.msi'
```

```bash
sha256sum -c --ignore-missing SHASUMS256.txt
```

哈希必须与官方 `SHASUMS256.txt` 一致；镜像目录缺校验文件时从官方取，校验失败就重新下载，不继续安装。ARM64 设备把文件名中的 `x64` 换成 `arm64`。

## 从 MSI 迁移到 fnm

1. 记录当前全局工具：`npm ls -g --depth=0`。
2. 通过“设置 → 应用 → 已安装的应用”卸载 MSI 版 Node。
3. 检查用户 PATH，移除 `C:\Program Files\nodejs` 残留。
4. 装 fnm、开启符号链接权限、写入 profile（见上文）。
5. `fnm install --lts` 后 `fnm default <version>`。
6. 重装需要的全局工具，如 `npm i -g pnpm`。
7. 新开终端，跑验收清单。

保留 MSI 时 fnm 会把它列为 `system` 条目，`node -v` 命中哪一套取决于 PATH 顺序；不打算长期共存就卸载系统版，减少“切换没生效”的歧义。
