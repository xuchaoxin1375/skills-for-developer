# 公钥与 ACL

Windows 把公钥文件按“账号是否属于本机管理员组”分成两个位置，两者互不生效。先判归属，再写文件，最后核对 ACL。

## 判断归属

```powershell
Get-LocalGroupMember -SID S-1-5-32-544 | Select-Object Name, ObjectClass
```

`S-1-5-32-544` 是本机 Administrators 组的固定 SID，不受系统语言影响；用组名匹配在非英文系统上会失败。域账号可能以 `DOMAIN\user` 形式出现，按名称尾部比较用户名。

## 两条路径

| 目标账号 | 文件 | ACL 要求 |
| --- | --- | --- |
| 普通用户 | `%USERPROFILE%\.ssh\authorized_keys` | 仅该用户与 SYSTEM/Administrators 可写 |
| 管理员组成员 | `%ProgramData%\ssh\administrators_authorized_keys` | 关闭继承后只保留 Administrators 与 SYSTEM 完全控制 |

管理员文件是全局一份，不是每个管理员一份；多个管理员的公钥都追加到同一文件。

## 设置管理员公钥

```powershell
$keyFile = "$env:ProgramData\ssh\administrators_authorized_keys"
New-Item -ItemType File -Path $keyFile -Force | Out-Null
Add-Content -Path $keyFile -Value '<ssh-ed25519 AAAA... user@client>' -Encoding utf8
icacls.exe $keyFile /inheritance:r /grant '*S-1-5-32-544:F' /grant 'SYSTEM:F'
Restart-Service sshd
```

`/grant` 用带 `*` 前缀的 SID 而不是组名，避免本地化组名不一致。已经在英文系统上操作也可以用 `Administrators`。

等价的 PowerShell ACL 写法（不需要本地化名称，也不依赖 `icacls` 输出解析）：

```powershell
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('S-1-5-32-544','FullControl','Allow')))
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('S-1-5-18','FullControl','Allow')))
Set-Acl -Path $keyFile -AclObject $acl
```

`S-1-5-18` 是 SYSTEM。权限过宽时 sshd 拒绝使用该文件，日志表现为公钥认证被忽略。

## 写入公钥的内容要求

- 一行一个公钥，行内是 `类型 数据 [注释]`；整份文件不写 BOM。
- 用 `Get-Content -Raw` 读客户端 `.pub` 后原样写入，不要把它当 PowerShell 对象再格式化。
- 重复追加不会“更保险”，同一公钥只需一行；重复行不影响认证，但会让文件难以维护。
- 用 `scp` 上传时目标必须是完整路径，`~` 在远端不一定展开到预期目录。

## 验证

```powershell
sshd -T | Select-String 'authorizedkeysfile'
Get-Acl "$env:ProgramData\ssh\administrators_authorized_keys" | Format-List
ssh -o BatchMode=yes <user>@<host> exit; $LASTEXITCODE
```

`sshd -T` 在管理员会话下可能显示 `__PROGRAMDATA__/ssh/administrators_authorized_keys`，这是 `Match Group administrators` 生效的正常结果，不是配置错误。

## 权限修复脚本

Win32-OpenSSH 的 MSI/zip 发行版自带 `FixHostFilePermissions.ps1` 与 `FixUserFilePermissions.ps1`，用于把主机密钥和用户目录权限修回预期值。可选功能（in-box）版本不提供这两个脚本，权限问题按上面的 `icacls` 与 `Set-Acl` 手工处理。

## 常见失败对照

| 现象 | 原因 |
| --- | --- |
| 管理员配了 `~/.ssh/authorized_keys` 仍要密码 | 归属走管理员文件，写错位置 |
| `administrators_authorized_keys` 里有 key 但不生效 | ACL 继承了普通用户可写权限，sshd 拒绝使用 |
| 普通用户免密正常，管理员不正常 | 只处理了用户级文件；两个位置是独立的两套 |
| 所有账号免密失效 | 全局指令被追加到 `Match` 块之后，或 `AuthorizedKeysFile` 被改成绝对路径 |
| 换机器后免密失效 | 客户端私钥是新生成的，公钥需重新上传；主机密钥变化另会触发 known_hosts 告警 |
| 服务端日志显示 `Accepted key`，客户端仍 `Permission denied` | 私钥带口令且客户端用了 `BatchMode=yes`：服务端已认可公钥，客户端无法签名后主动断开 |
