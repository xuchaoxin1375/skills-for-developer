# WSL 内跑 sshd

把 WSL 发行版当 Linux 服务器用，与“Windows 原生 sshd”是两套独立的服务、账号与端口。混用会得到两种典型故障：端口互相占用，或以为配了免密实际配在另一套上。

## 选哪一套

| 需求 | 选择 |
| --- | --- |
| 从别的机器登录 Windows 桌面、用 Windows 账号与路径 | 原生 Windows sshd（本 skill 主流程） |
| 需要 Linux 环境、systemd、apt 包、Linux 账号 | WSL 发行版内 sshd |
| 两者都要 | 用不同端口，各自独立配置 |

## 在发行版内装服务端

```bash
sudo apt update && sudo apt install -y openssh-server
sudo systemctl enable --now ssh
systemctl status ssh --no-pager
```

WSL2 默认没有 systemd，`systemctl` 会报 `System has not been booted with systemd`。启用方式是在 `/etc/wsl.conf` 写入：

```ini
[boot]
systemd=true
```

然后回到 Windows 执行 `wsl --shutdown`，重新进入发行版。没有 systemd 时用 `sudo service ssh start` 临时启动。

## 从 Windows 本机访问

WSL2 的 localhost 转发通常让 `ssh localhost -p <port>` 直接可用。端口不通时先在发行版内确认监听：

```bash
ss -tuln | grep ssh
```

## 从局域网其他机器访问

WSL2 在 NAT 模式下位于独立虚拟网段，Windows 不会自动把发行版的端口暴露到局域网。需要两步转发：

```powershell
# 管理员会话；目标 IP 是发行版当前地址（wsl hostname -I）
netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 `
    connectport=22 connectaddress=<wsl-ip>
New-NetFirewallRule -Name 'WSL-SSH-2222' -DisplayName 'WSL SSH 2222' `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 2222
```

```powershell
netsh interface portproxy show v4tov4      # 查看已有转发
netsh interface portproxy delete v4tov4 listenport=2222 listenaddress=0.0.0.0   # 撤销
```

发行版 IP 每次重启可能变化，转发目标要跟着改；长期使用更适合固定端口映射（`.wslconfig` 的 `networkingMode=mirrored` 或发行版内固定网络配置），并按[端口与防火墙](port-and-firewall.md)处理与原生 sshd 的端口冲突。

## 与原生 Windows sshd 的边界

- 账号体系独立：WSL 的 Linux 用户与 Windows 本地账号不是同一套，免密公钥也要各放一份。
- 配置位置独立：发行版内是 `/etc/ssh/sshd_config`，Windows 侧是 `%ProgramData%\ssh\sshd_config`。
- 日志独立：发行版内用 `journalctl -u ssh` 或 `/var/log/auth.log`，Windows 侧是事件日志 `OpenSSH/Operational`。
- 卸载或重置发行版会连带丢失其中的密钥与配置，Windows 侧不受影响。
