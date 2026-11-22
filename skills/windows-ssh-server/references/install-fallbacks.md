# 安装回退与卸载

in-box 可选功能（Feature on Demand）从 Windows Update 取包，在内网、被策略关掉更新或长期服务版（LTSC）上常常装不上。四条路线的取舍如下。

## 判定可选功能是否可用

```powershell
Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
Get-WindowsCapability -Online -Name 'OpenSSH.Client*'
```

`State : Installed` 表示已装；`NotPresent` 表示可装；命令本身报错多半是没提权。安装：

```powershell
Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
```

常见失败是 `0x800f0954` 一类错误码：Windows Update 或“可选功能”源被组策略、WSUS 或离线镜像限制。此时不要反复重试，直接换独立发行版。

装完先确认这份载荷自洽，再去配服务：

```powershell
$dir = Join-Path $env:SystemRoot 'System32\OpenSSH'
Get-ChildItem $dir -Filter 'ssh*.exe' | Select-Object Name, @{n = 'Version'; e = { $_.VersionInfo.ProductVersion }}
```

`sshd.exe` 与 `ssh.exe` 跨大版本（例如服务端 7.7、客户端 9.5）说明拿到了不完整的旧载荷：这种组合启动即崩（缺少 `BN_init` 等旧符号），重装同一份也不会好。另外 `Remove-WindowsCapability` 可能返回 `RestartNeeded=True`，旧二进制在重启前仍留在 `System32\OpenSSH` 并占用 PATH，此时按服务 ImagePath 判定真正在用的文件。

## 路线对比

| 路线 | 前提 | 优点 | 失败或代价 |
| --- | --- | --- | --- |
| 可选功能（in-box） | 能访问 Windows Update | 随系统更新，路径固定在 `%SystemRoot%\System32\OpenSSH` | 内网/LTSC 常失败；版本跟随系统，较旧 |
| Win32-OpenSSH MSI | 能下载 MSI | 一条命令、可选只装服务端、自带权限修复脚本 | 版本需自行更新；`Releases` 页有 `-Preview` 标签，生产选稳定版 |
| Win32-OpenSSH zip | 能下载 zip | 免安装、可控目录、适合离线拷贝 | 需手工注册服务与配 PATH |
| Scoop / 包管理器 | 已装包管理器 | 升级统一 | 与 in-box 版本共存时容易 PATH 命中错误的一份 |

同时存在多份 sshd 时，`Get-Command sshd -All` 与 `Get-Service sshd` 指向的对象可能不是同一套，配置也会读各自目录。装之前先确认没有第二份，装之后把不用的那份移除。

## MSI 安装

```cmd
msiexec /i <path-to-openssh.msi> ADDLOCAL=Server
```

只装服务端；`ADDLOCAL=Client` 只装客户端，省略参数两者都装。静默安装加 `/qn`，日志用 `/l*v <log>`。安装后仍需启动服务、设置自启、放行防火墙，与可选功能路线一致。

## zip 安装

```powershell
$target = Join-Path $env:ProgramFiles 'OpenSSH'
Expand-Archive -Path <path-to-OpenSSH-Win64.zip> -DestinationPath $target -Force
# 发行版 zip 内层还有一个 OpenSSH-Win64 目录，按实际层级定位注册脚本
& (Get-ChildItem $target -Filter 'install-sshd.ps1' -Recurse | Select-Object -First 1).FullName
```

`install-sshd.ps1` 注册 `sshd` 与 `ssh-agent` 服务并设置安装目录权限。之后同样需要启动服务、自启与防火墙。二进制目录应只让 SYSTEM 与 Administrators 可写，脚本会处理；手工拷贝时这一步要自己保证，否则 sshd 拒绝启动。

## 下载通道与校验

可选功能走 Windows Update，不受 GitHub 可达性影响；改用独立发行版时才需要下载 MSI/zip。国内网络下 GitHub 直连经常无响应，公开加速前缀也会随时返回 403 或极低速，固定写死一个前缀不可靠。

按实测顺序尝试，每个通道用有界超时先取前 2 MB 估速度：

```powershell
$asset = 'https://github.com/PowerShell/Win32-OpenSSH/releases/download/<tag>/<asset-file>'
foreach ($prefix in 'https://ghfast.top', 'https://ghproxy.net') {
    & curl.exe -s -o NUL --max-time 12 --range 0-2097151 -w "$prefix %{http_code} %{size_download} %{speed_download}`n" "$prefix/$asset"
}
```

判定与处理：

| 结果 | 处理 |
| --- | --- |
| `403` / `429` | 该前缀拒绝或限流，换下一个，不原样重试 |
| `000` 或 12 秒内几乎无字节 | 通道不可用，换前缀或走本机代理 |
| `302` | 需要跟随跳转，加 `-L` 再试 |
| `206` 且稳定几百 KB/s | 可用，转完整下载 |

公开前缀返回的文件必须校验后再用。GitHub API 的 release 元数据里有官方 digest，直连 `api.github.com` 通常可用：

```powershell
$rel = Invoke-RestMethod 'https://api.github.com/repos/PowerShell/Win32-OpenSSH/releases/latest'
$rel.assets | Select-Object name, size, digest
```

下载后比对 `Get-FileHash <file> -Algorithm SHA256` 与 API 给出的 `sha256:` 值；不一致就丢弃并换通道，不要“先装上再说”。

代理也是候选通道：本机代理客户端在监听但没有启用系统代理时，`curl.exe --proxy http://127.0.0.1:<port>` 可单独走代理，不必改动系统设置。代理端口与可用性按实际情况确认，不假设默认端口。

## 卸载与回滚

首选脚本入口，它按实际安装方式选卸载路径（MSI 产品、in-box 可选功能、zip 注册的服务），并幂等处理“已经不存在”的情况：

```powershell
pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1 -WhatIf    # 先看动作
pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1            # 卸程序与服务，保留配置与主机密钥
pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1 -PurgeData # 连配置、主机密钥、授权公钥一起清
```

默认保留 `%ProgramData%\ssh`：重装后主机指纹与已授权公钥都能沿用；只有 `-PurgeData` 才删除，删除后主机密钥会重新生成，客户端会提示 host key 变化，批量环境先确认这一点再删。`-KeepFirewallRule` 用于上层的统一放行策略。

手工卸载时的等价步骤：

- 可选功能：`Stop-Service sshd` → `Remove-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'` → 删防火墙规则。
- MSI：`msiexec /x <path-to-openssh.msi>`；不知道 ProductCode 时查 `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` 下 DisplayName 匹配 OpenSSH 的项。
- zip：`Stop-Service sshd` → `sc.exe delete sshd` → `sc.exe delete ssh-agent`，再删安装目录。

回滚时要一起清掉这些改动，只删程序会留下半个服务端：

| 位置 | 内容 |
| --- | --- |
| 服务 | `sshd`、`ssh-agent`（MSI/zip 路线还会留下服务注册） |
| 防火墙 | `OpenSSH-Server-In-TCP` 及自建的端口规则 |
| 配置与主机密钥 | `%ProgramData%\ssh\`（含 `administrators_authorized_keys`） |
| 注册表 | `HKLM:\SOFTWARE\OpenSSH` 的 `DefaultShell`、`DefaultShellCommandOption` |
| 用户侧 | `%USERPROFILE%\.ssh\authorized_keys` 中新增的行 |

脚本不动注册表里的 `DefaultShell`：它是 shell 偏好而不是服务端安装产物，卸载后保留无副作用，需要在其他 shell 场景复用时正好。要清除就手工删 `HKLM:\SOFTWARE\OpenSSH`。

