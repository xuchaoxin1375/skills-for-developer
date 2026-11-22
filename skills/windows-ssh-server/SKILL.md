---
name: windows-ssh-server
description: >
  把 Windows 主机（Windows 10 1809+、Windows 11、Server 2019+）配置成 SSH 服务端，以及排查已配置却连不上、
  密码怎么输都不对、免密不生效、sshd 起不来、22 端口被占用等问题；覆盖 in-box OpenSSH Server 安装、
  服务自启、防火墙、密码与公钥认证、管理员 authorized_keys 与 ACL、默认 shell、非默认端口、日志与登录排障，
  WSL 发行版内跑 sshd 的差异按需读 references。
  只把 Windows 当 SSH 客户端、端口转发与内网穿透方案设计不在本 skill。
---

# Windows 作为 SSH 服务端

## 适用范围

需要让一台 Windows 主机接受 SSH 登录时加载：首次安装 OpenSSH Server、开机自启、放行防火墙、选择密码或公钥认证、给管理员配免密、换默认 shell、换端口，或登录失败要定位原因。产出是一台可验收的服务端：服务在跑且自启、目标端口在监听、防火墙放行同一端口、认证方式对目标账号真实生效。

不在本 skill：

- 只把 Windows 当客户端连 Linux 或其他主机：按常规客户端做法即可，不需要安装服务端。
- 端口转发、隧道、内网穿透的方案选型：本 skill 只涉及让 sshd 能被连上。
- 下载、代理、镜像与安装失败的链路问题，按 [network-access](../network-access/SKILL.md) 分诊。
- PowerShell 执行细节（编码、引号、退出码）按 [shell-pitfalls](../shell-pitfalls/SKILL.md)；
  改这两个脚本或新增脚本前读 [scripting-best-practices](../scripting-best-practices/SKILL.md)。
- 本机已有哪些运行时、包管理器与浏览器，按 [resource-inventory](../resource-inventory/SKILL.md)。

## 最短执行路径

1. **只读体检**：先跑诊断脚本，一次拿到服务、端口、防火墙、配置与日志状态，不要逐项手工探测。

   ```powershell
   pwsh -NoProfile -File ./scripts/Test-WindowsSshServer.ps1
   ```

2. **部署或修配置**（管理员会话）：脚本幂等，重复执行安全；`-DefaultShell pwsh` 可省略表示不改。可选功能装不上时改走独立发行版：`-InstallSource msi -PackagePath <msi>`（下载通道与校验见[安装回退](references/install-fallbacks.md)）。

   ```powershell
   pwsh -NoProfile -File ./scripts/Install-WindowsSshServer.ps1 -Port 22 -DefaultShell pwsh
   ```

3. **配免密**（可选）：`-AddAuthorizedKey` 按目标账号是否属于管理员组自动选文件并收紧 ACL。

   ```powershell
   $key = Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" -Raw
   pwsh -NoProfile -File ./scripts/Install-WindowsSshServer.ps1 -AddAuthorizedKey $key
   ```

4. **从另一台设备验收**：`ssh -vvv <user>@<host>` 看到认证通过并进入预期 shell；免密用
   `ssh -o BatchMode=yes <user>@<host> exit` 期望返回 0。

5. **失败**按下方决策表定位；服务端日志与前台调试细节见[排障](references/troubleshooting.md)。

两个脚本的职责：`Test-WindowsSshServer.ps1` 只读、任何权限可跑，用于体检和验收；
`Install-WindowsSshServer.ps1` 需要管理员，只做“确保”动作（缺什么补什么），不重写整份 `sshd_config`。
跳过脚本、手工配置时，按下面的事实逐项核对。

## Windows 上的位置与默认值

| 项目 | 位置或默认值 |
| --- | --- |
| 服务名 | `sshd`（显示名 `OpenSSH SSH Server`）；`ssh-agent` 默认 Disabled，只有客户端用密钥登录才需要 |
| 服务端二进制 | 可选功能在 `%SystemRoot%\System32\OpenSSH\`；MSI/zip 在 `%ProgramFiles%\OpenSSH\` |
| 配置文件 | `%ProgramData%\ssh\sshd_config`，首次启动服务时生成；改动后必须重启服务 |
| 主机密钥 | `%ProgramData%\ssh\ssh_host_*`，首次启动时生成 |
| 管理员公钥 | `%ProgramData%\ssh\administrators_authorized_keys`（ACL 需收紧） |
| 普通用户公钥 | `%USERPROFILE%\.ssh\authorized_keys` |
| 默认 shell | 注册表 `HKLM:\SOFTWARE\OpenSSH` 值 `DefaultShell`；未设置时为 `cmd.exe` |
| 日志 | 默认写入事件日志 `OpenSSH/Operational`；`SyslogFacility LOCAL0` 才写文件到 `%ProgramData%\ssh\logs\`（10.x 有 `sshd.log` 与 `sshd-session.log` 两份） |
| 防火墙规则 | 安装时创建 `OpenSSH-Server-In-TCP`，端口写死在规则里 |

## 会改变结论的 Windows 事实

- **认证只有 `password` 和 `publickey`**。`AuthenticationMethods` 只能组合这两者；没有 keyboard-interactive，也就没有 PAM、OTP、短信二次验证。
- **密码是 Windows 账户密码**，不是 PIN、指纹或 Windows Hello。Entra ID（Azure AD）账户不支持公钥认证；域账号的用户名格式见排障参考。
- **管理员的公钥放错文件是最常见的“免密不生效”**。`sshd_config` 末尾默认带 `Match Group administrators` 块，把管理员的 `AuthorizedKeysFile` 指向 `administrators_authorized_keys`；写进 `~/.ssh/authorized_keys` 对管理员账号无效。
- **追加指令要插到第一个 `Match` 之前**。默认配置末尾的 `Match` 块会吞掉其后所有行，把它们变成“只对管理员生效”。这正是“改完配置只有一半账号受影响”的根因。
- **`DefaultShell` 指向的 exe 必须存在，且不要落在包管理器的 `current` 跳转目录**（如 `...\scoop\apps\powershell\current\pwsh.exe`）。这两种情况客户端都表现为“密码怎么输都不对”，只有服务端日志写着 `not allowed because shell ... does not exist`；写具体版本路径或系统自带 `powershell.exe`，版本路径在包升级后失效，届时重跑部署脚本。
- **照抄 Linux 的 `sshd_config` 会踩空**。Windows 版不支持 `StrictModes`、`PrintMotd`、`PrintLastLog`、`PidFile`、`AcceptEnv`、`PermitUserEnvironment`、`X11Forwarding`、`HostbasedAuthentication`、`KerberosAuthentication`、`KbdInteractiveAuthentication`、`PermitTunnel` 等指令；写进去可能启动失败或静默无效。用 `sshd -T` 看实际生效值，不要只看文件里写了什么。
- **`AllowUsers` / `DenyUsers` 的账号名必须小写**，域账号写成 `user?domain*` 形式，不是 Linux 的 `@` 写法。
- **改 `Port` 要同时改防火墙规则**，规则里的端口是固定值；只改 `sshd_config` 会得到“服务在监听但外部连不上”。
- **WSL2 的 `networkingMode=mirror` 会抢占 22 端口**，表现为 `Bind to port 22 on 0.0.0.0 failed: Permission denied`；改用其他端口或调整 WSL 网络模式的取舍见[端口与防火墙](references/port-and-firewall.md)。
- **解析 sshd 一律按服务 ImagePath**。`Get-Command sshd` 可能命中 PATH 上残留的另一套（例如待重启才移除的 in-box 文件），命令行验证与实际服务的二进制不是同一份时，结论全部失真。
- **in-box 服务端可能是“半新半旧”载荷**。同目录客户端已更新到 9.5、`sshd.exe` 仍是 7.7 时，服务启动会因缺少 `BN_init` 等旧符号失败（弹窗“无法找到入口”，服务日志 `7009` 超时等待）。先比版本，别调配置。
- **`Remove-WindowsCapability` 可能返回 `RestartNeeded=True`**，旧二进制在重启前仍留在 `System32\OpenSSH` 并占住 PATH。
- **`sshd -t` / `sshd -T` 需要管理员**。主机密钥仅 SYSTEM 与 Administrators 可读，非提权执行会得到 `no hostkeys available`，这不是配置错误。
- **10.x 的会话日志单独一份**：`sshd.log` 只记监听进程，认证与会话细节在 `sshd-session.log`。
- **`sshd -T` 才是生效配置**，服务启动时才读文件；改完不重启服务，`-T` 与客户端看到的都还是旧行为。

## 排障决策表

| 现象 | 先查 | 处置 |
| --- | --- | --- |
| 客户端超时或连接被拒 | 服务状态、端口监听、防火墙规则端口 | 服务未启动先启动；监听端口与规则端口不一致就统一到实际端口 |
| 连上后反复要密码、`Permission denied` | 服务端日志、`sshd -T` 的认证项 | 密码不是 PIN；确认 `PasswordAuthentication`、`AllowUsers` 未排除该账号；确认默认 shell 路径存在 |
| 免密不生效但密码能登 | 账号是否在管理员组、公钥落在哪个文件、该文件 ACL | 管理员改写到 `administrators_authorized_keys` 并收紧 ACL |
| sshd 启动后立刻停止 | `sshd -t` 语法、服务事件日志、二进制版本 | 语法错误、端口被占用、主机密钥 ACL 异常；弹窗“无法找到入口 `BN_init`”说明 sshd 与同目录 ssh 版本不同代，换独立发行版 |
| 服务端已 `Accepted key` 但客户端 `Permission denied` | 私钥是否带口令、是否用了 `BatchMode=yes` | 带口令私钥在 BatchMode 下无法提示输入，客户端会放弃签名；改用无口令密钥或 ssh-agent |
| 日志里看不到认证细节 | 是否只看了 `sshd.log` | 10.x 的会话日志在 `sshd-session.log`；也可临时开 `LogLevel DEBUG3` |
| 登录成功但立刻断开 | 注册表 `DefaultShell` 指向的 exe | 改成实际存在的 `powershell.exe` 或 `pwsh.exe` 绝对路径 |
| 只有管理员能登、普通用户一律拒绝 | 配置中 `Match` 块的位置 | 把全局指令移到第一个 `Match` 之前 |
| 域账号密码正确仍被拒 | 用户名格式与大小写 | 用 `host\user` 或 `user@host`；配置里用 `user?domain*` |

具体命令、日志字段与事件日志查询见[排障](references/troubleshooting.md)。

## 免密认证的正确做法

按账号是否属于本机管理员组分流，两条路径不能混用：

| 目标账号 | 公钥文件 | 附加要求 |
| --- | --- | --- |
| 普通用户 | `%USERPROFILE%\.ssh\authorized_keys` | 该用户能读写自己的文件即可 |
| 本机管理员组成员 | `%ProgramData%\ssh\administrators_authorized_keys` | `icacls /inheritance:r` 后只授予 Administrators 与 SYSTEM 完全控制 |

用 `-AddAuthorizedKey` 时脚本会自动判定归属、去重并设置 ACL；手工操作、权限修复脚本与常见失败形态见[公钥与 ACL](references/pubkey-acl.md)。

## 验收清单

- [ ] `Get-Service sshd` 为 Running，StartType 为 Automatic。
- [ ] 目标端口在 `Get-NetTCPConnection -State Listen` 中由 `sshd` 进程持有。
- [ ] 存在已启用的入站规则，且 `LocalPort` 等于实际端口。
- [ ] `sshd -t` 无输出；`sshd -T` 的 `port`、`passwordauthentication`、`pubkeyauthentication` 与预期一致。
- [ ] 另一台设备 `ssh -vvv <user>@<host>` 能完成认证并进入预期 shell。
- [ ] 配了免密时，`ssh -o BatchMode=yes <user>@<host> exit` 返回 0。
- [ ] 事件日志 `OpenSSH/Operational` 能看到本次登录，或 `%ProgramData%\ssh\logs\` 下的日志有记录。
- [ ] 已记录回滚入口：`sshd_config` 备份路径、防火墙规则名、改过的注册表值。

## 按需读取

| 条件 | 入口 |
| --- | --- |
| 认证失败、密码总不对、服务起不来、要定位日志 | [排障](references/troubleshooting.md) |
| 配免密、管理员公钥、ACL 与权限修复 | [公钥与 ACL](references/pubkey-acl.md) |
| 改端口、防火墙规则同步、WSL 抢占 22 | [端口与防火墙](references/port-and-firewall.md) |
| 用 WSL 发行版当服务端，而不是原生 Windows | [WSL 内跑 sshd](references/wsl-sshd.md) |
| 可选功能装不上（无 Windows Update、内网、离线）或要卸载回滚 | [安装回退与卸载](references/install-fallbacks.md) |
| 跑 `Test-WindowsSshServer.ps1` 想先知道检查项与退出码含义 | 脚本自身 `Get-Help ./scripts/Test-WindowsSshServer.ps1 -Full` |

## 依据与维护

- [Get started with OpenSSH Server for Windows](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)：可选功能名、安装后启动与防火墙核对。
- [OpenSSH Server configuration for Windows](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_server_configuration)：Windows 专有配置项、不支持的指令清单、`administrators_authorized_keys` 的 ACL 要求、默认 shell 注册表。
- [Key-Based Authentication in OpenSSH for Windows](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)：普通用户与管理员两条公钥路径、SID 形式的 ACL 写法。
- [Win32-OpenSSH Releases](https://github.com/PowerShell/Win32-OpenSSH/releases)：可选功能不可用时的独立发行版；注意区分稳定版与 `-Preview` 标签。

2026-11-22 按上述文档与 Windows 10 19044 实测核对。维护时同步更新 README 索引行并跑仓库校验脚本。
