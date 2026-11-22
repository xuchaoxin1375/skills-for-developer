# 端口与防火墙

sshd 与防火墙规则各存一份端口，两者不同步时表现是“服务在监听，外部连不上”。改端口按下面的顺序一次改完。

## 改端口的完整步骤

```powershell
# 配置侧
$config = "$env:ProgramData\ssh\sshd_config"
Copy-Item $config "$config.bak-$(Get-Date -f yyyyMMddHHmmss)"
# 在第一个 Match 之前写 Port 22022，并注释掉原来的 Port 22
Restart-Service sshd

# 防火墙侧：规则的端口是固定值，改端口只能删了重建
Remove-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22022

# 核对
Get-NetTCPConnection -State Listen -LocalPort 22022 | Select-Object LocalAddress, OwningProcess
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' | Get-NetFirewallPortFilter
```

`Set-NetFirewallRule` 不能改端口，只改名称、启用状态等属性；端口在 `Get-NetFirewallPortFilter` 里，重建规则是唯一可靠做法。

客户端连非默认端口：`ssh -p 22022 <user>@<host>`。

`sshd_config` 里可以写多个 `Port` 行同时监听多个端口，但每行都要有对应防火墙放行。

## 规则存在但连不上

```powershell
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' |
    Select-Object Name, Enabled, Direction, Action, Profile
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' | Get-NetFirewallPortFilter
Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction
```

逐项确认：规则启用、方向入站、动作放行、端口等于实际监听端口、当前网络配置文件（Domain/Private/Public）的防火墙未整体阻止入站。系统把未知网络判成 Public 时，只对 Private 放行的规则不会生效。

## WSL2 抢占 22 端口

`networkingMode=mirror` 的 WSL 会把 Windows 的监听端口代理到发行版，sshd 启动时报：

```text
Bind to port 22 on 0.0.0.0 failed: Permission denied
Cannot bind any address.
```

判定：

```powershell
Get-Content "$env:USERPROFILE\.wslconfig" -ErrorAction SilentlyContinue
Get-NetTCPConnection -State Listen -LocalPort 22 | Select-Object LocalAddress, OwningProcess
Get-Process -Id (Get-NetTCPConnection -State Listen -LocalPort 22).OwningProcess
```

三种处置，按影响面从大到小：

| 做法 | 效果 | 代价 |
| --- | --- | --- |
| 改 sshd 端口 | 与 WSL 互不干扰，最省事 | 客户端要带 `-p`，防火墙规则同步改 |
| `.wslconfig` 改回 `networkingMode=nat` 后 `wsl --shutdown` | 22 端口归还 Windows | 失去 mirror 模式的主机名与端口共享能力，需重启 WSL |
| 停掉 WSL 内的 sshd 或相关服务 | 保留当前网络模式 | 每次 WSL 发行版启动都可能重新占用 |

先确认占用方确实是 WSL，再决定改哪一侧；把 Windows sshd 直接改成 22022 通常比改 WSL 网络模式代价低。

## 暴露到公网的取舍

Windows 没有与 fail2ban 等价的现成组件，面向公网时优先做减面而不是加拦截：

- 关闭密码认证，只留公钥；并确认管理员的 `administrators_authorized_keys` 已收紧。
- 用 `AllowUsers` / `AllowGroups` 限定可登录账号，账号名写小写。
- 在防火墙规则上限定 `-RemoteAddress` 到固定网段，比任何应用层规则都可靠。
- 需要临时运维时改端口只能减少扫描噪音，不构成安全边界。
