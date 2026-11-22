# 登录与服务排障

Windows 上 sshd 的失败大多不在网络，而在账号解析、默认 shell、公钥位置和配置块作用域。按“客户端日志 → 服务端日志 → 生效配置 → 端口与防火墙”的顺序收敛，比反复重装快。

## 日志在哪

默认只写事件日志，不落文件：

```powershell
Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 20 |
    Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-List
```

事件查看器里的路径是 `Applications and Services Logs > OpenSSH > Admin / Operational / Debug`。

需要可 grep 的文件日志时，在 `%ProgramData%\ssh\sshd_config` 的全局区（第一个 `Match` 之前）设置：

```sshd
SyslogFacility LOCAL0
LogLevel DEBUG3
```

重启服务后写入 `%ProgramData%\ssh\logs\`。10.x 起日志分两份：`sshd.log` 只记监听进程，认证与会话细节在 `sshd-session.log`；只 grep 前者会看不到任何一次登录。`DEBUG3` 只用于排障，定位完改回 `INFO`：日志会记录每次认证尝试的细节。

## 前台抓实时错误

事件日志不够用时，停掉服务、前台运行 sshd，再让客户端连一次：

```powershell
Stop-Service sshd
& "$env:SystemRoot\System32\OpenSSH\sshd.exe" -ddd
# 另开一个客户端会话重试，然后 Ctrl+C 退出前台进程
Start-Service sshd
```

`-ddd` 是调试级别；`-d` 只处理一次连接就退出。前台跑完必须把服务启回来，否则下次重启前一直不可用。

## 客户端日志怎么读

```powershell
ssh -vvv <user>@<host>
```

| 客户端输出 | 含义 |
| --- | --- |
| `Connection refused` | TCP 到达但没有监听：服务没起、端口不对，或被本地策略拦 |
| `Connection timed out` | 报文没到达：防火墙规则、网段、路由 |
| `Authentications that can continue: publickey,password` | 认证列表正常，问题在凭据或账号 |
| `Authentications that can continue: publickey` | 服务端关了密码认证 |
| `Permission denied (publickey,password)` | 连接已到服务端，被认证拒绝，转看服务端日志 |
| `Permission denied (publickey)` | 只提示公钥：公钥文件位置、ACL 或密钥算法不被接受 |
| `no matching host key type found` | 客户端过旧，不接受服务端的算法 |

## 服务端日志关键行

| 日志片段 | 原因与处置 |
| --- | --- |
| `not allowed because shell <path> does not exist` | `DefaultShell` 指向的 exe 不存在；改注册表或改回 `cmd.exe` |
| `Failed password for invalid user <name>` | 用户名解析失败：大小写、域前缀、账号不存在 |
| `Failed password for <name>` + 密码确实正确 | 密码是账户密码而非 PIN；账号禁用、过期、空密码同样落在这里 |
| `Bind to port <n> ... failed: Permission denied` | 端口被占用（多为 WSL 或另一份 sshd），换端口或停占用方 |
| `User <name> not allowed because shell <path> does not exist` | `DefaultShell` 指向的 exe 不存在或经过包管理器的 `current` 跳转目录；改成具体版本路径或系统 `powershell.exe` |
| `Accepted key ... found at ...` 之后客户端立刻断开 | 私钥带口令而客户端用 `BatchMode=yes`，无法提示输入口令；用无口令密钥或装载到 ssh-agent |
| `Accepted publickey for <name>` | 公钥认证成功；此后的问题在 shell 启动而非认证 |
| `Connection closed by authenticating user` | 客户端主动放弃：算法协商失败或多次认证失败 |
| `fatal: Timeout before authentication` | 客户端连上但不完成认证，常见于代理或端口探测 |

## 生效配置与账号状态

```powershell
sshd -t        # 语法检查，无输出即通过；需管理员，否则报 no hostkeys available
sshd -T | Select-String '^(port|passwordauthentication|pubkeyauthentication|authorizedkeysfile|allowusers|denyusers|allowgroups|denygroups|authenticationmethods|permitrootlogin|subsystem) '
Get-LocalUser <name> | Format-List Name, Enabled, PasswordExpired, PasswordRequired, LastLogon
```

`sshd -t` / `sshd -T` 都要读主机密钥，而主机密钥只授权给 SYSTEM 与 Administrators。普通会话执行会得到 `no hostkeys available -- exiting.`，这不代表配置有错，换管理员会话复核即可。

`sshd -T` 输出的是解析后的生效值，比读文件可靠；但它同样要求服务重启才反映新文件。

## 端口与占用

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 22,22022 |
    Select-Object LocalAddress, LocalPort, OwningProcess
netstat -ano | findstr ':22'
```

监听存在但外部连不上，问题在防火墙规则端口与实际端口不一致，见[端口与防火墙](port-and-firewall.md)。

## 逐步最小化验证

1. 服务端自测：在本机 `ssh <user>@localhost`，绕过防火墙与网段问题。
2. 自测通过、外部失败：查防火墙规则端口与网段限制。
3. 自测也失败：`sshd -T` 看认证配置，再看服务端日志的拒绝原因。
4. 密码能过、公钥不过：按[公钥与 ACL](pubkey-acl.md) 核对文件位置与权限。

## 服务启动失败

先在服务事件日志里看具体错误，再看二进制本身：

```powershell
Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = (Get-Date).AddMinutes(-15) } |
    Where-Object Message -match 'sshd|OpenSSH' | Select-Object TimeCreated, Id, Message | Format-List
(Get-CimInstance Win32_Service -Filter "Name='sshd'").PathName    # 服务实际加载的二进制
```

| 事件 | 含义 |
| --- | --- |
| `7009` + `7000`「服务没有及时响应启动或控制请求」 | 进程启动后立即退出，真正的错误在前一步 |
| 弹窗「无法找到入口：无法定位程序输入点 `BN_init`」 | sshd 与同目录 crypto 库/客户端不同代，多为 in-box 半新半旧载荷；换独立发行版 |
| 无事件、`sc query` 显示 STOPPED | 二进制路径不存在或权限不足；核对服务 ImagePath |

判定版本是否混装：

```powershell
$dir = Split-Path (Get-CimInstance Win32_Service -Filter "Name='sshd'").PathName.Trim('"')
Get-ChildItem $dir -Filter 'ssh*.exe' |
    Select-Object Name, @{n = 'Version'; e = { $_.VersionInfo.ProductVersion }}
```

`sshd.exe` 与 `ssh.exe` 跨大版本（例如 7.7 对 9.5）就属于混装，调配置没有意义。

## 二进制来源被抢占

`Get-Command sshd` 返回的路径可能不是服务在用的那一份：卸载 in-box 版本后若提示 `RestartNeeded=True`，旧文件在重启前仍留在 `System32\OpenSSH` 并排在 PATH 前面。表现是命令行验证全部正常、服务却起着另一份二进制，或者反过来。

统一按服务 ImagePath 判定，不要按 PATH：

```powershell
(Get-CimInstance Win32_Service -Filter "Name='sshd'").PathName
& (Get-CimInstance Win32_Service -Filter "Name='sshd'").PathName.Trim('"') -V   # 不可用时看文件版本
```

两套并存时先重启，把待移除的那套清掉，再核对 PATH 顺序。

## 常见误配清单

- 全局指令写在 `Match` 块之后，实际只对管理员生效。
- `AllowUsers` 写了 `Cxxu` 这类大写账号名，规则不匹配。
- 同时存在可选功能版与 Scoop/Win32-OpenSSH 版 `sshd`，PATH 命中的是另一份，配置也读另一份 `sshd_config`。
- 改完 `sshd_config` 没重启服务，`sshd -T` 与客户端都还是旧行为。
- 把 `~/.ssh/authorized_keys` 当管理员账号的免密文件。
- 在 Windows 配置里抄了 `StrictModes no`、`PrintMotd no` 之类不存在的指令，以为能解决权限问题。
