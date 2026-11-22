<#
.SYNOPSIS
    只读诊断 Windows OpenSSH Server（sshd）的安装、服务、端口、防火墙、配置与免密文件状态。

.DESCRIPTION
    依次检查：sshd 二进制与可选功能、服务状态与启动类型、sshd -t 语法、sshd -T 生效配置、
    端口监听、对应防火墙规则、主机密钥、目标账号的授权公钥文件与 ACL、日志通道。

    全程只读，不修改配置、不启动或重启服务，普通权限即可运行。可选功能状态、`sshd -t`/`-T`、
    防火墙规则与管理员公钥文件的读取都要求管理员权限，非提权会话下这些项标记为 Unknown 而不是失败；
    存在 Fail 项时退出码为 1，否则为 0。

.PARAMETER UserName
    要检查免密公钥归属的账号名，默认当前登录用户。用于判断公钥应落在用户目录还是
    administrators_authorized_keys。

.PARAMETER Port
    期望的服务端口。省略时取 sshd -T 的生效值，取不到再退回 22。改过端口、怀疑规则与监听
    不一致时显式传入。

.PARAMETER IncludeEvents
    额外读取事件日志 OpenSSH/Operational 的最近记录，用于确认登录是否到达服务端。

.EXAMPLE
    pwsh -NoProfile -File ./Test-WindowsSshServer.ps1

    安装后或排障前的常规体检。

.EXAMPLE
    pwsh -NoProfile -File ./Test-WindowsSshServer.ps1 -Port 22022 -IncludeEvents

    已改成非默认端口并怀疑防火墙规则没跟上时使用。

.NOTES
    只读脚本，可在任何会话运行；需要管理员视角时才提权。
#>
[CmdletBinding()]
param(
    [string]$UserName = $env:USERNAME,
    [ValidateRange(0, 65535)]
    [int]$Port = 0,
    [switch]$IncludeEvents
)

$ErrorActionPreference = 'Continue'
$script:Checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Item,
        [ValidateSet('Pass', 'Warn', 'Fail', 'Info', 'Unknown')]
        [string]$Status,
        [string]$Detail = ''
    )
    $script:Checks.Add([pscustomobject]@{
            Item   = $Item
            Status = $Status
            Detail = $Detail
        })
}

function Get-SshdExe {
    # 与 Install 脚本保持一致：以服务 ImagePath 为准，避免命中 PATH 上残留的旧版本
    $service = Get-CimInstance Win32_Service -Filter "Name='sshd'" -ErrorAction SilentlyContinue
    if ($service -and $service.PathName) {
        $raw = $service.PathName.Trim()
        if ($raw.StartsWith('"')) {
            $end = $raw.IndexOf('"', 1)
            if ($end -gt 0) { $raw = $raw.Substring(1, $end - 1) }
        }
        else {
            $raw = ($raw -split '\s+')[0]
        }
        if (Test-Path -LiteralPath $raw) { return $raw }
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles 'OpenSSH\sshd.exe'),
        (Join-Path $env:ProgramFiles 'OpenSSH\OpenSSH-Win64\sshd.exe'),
        (Join-Path $env:SystemRoot 'System32\OpenSSH\sshd.exe')
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command sshd.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Path }
    return $null
}

function Format-AclSummary {
    param([string]$Path)
    try {
        $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
        $inherited = if ($acl.AreAccessRulesProtected) { 'no-inherit' } else { 'inherit' }
        $entries = $acl.Access | ForEach-Object {
            '{0}:{1}' -f $_.IdentityReference, $_.FileSystemRights
        }
        return "$inherited; $($entries -join ', ')"
    }
    catch {
        return "ACL 读取失败: $($_.Exception.Message)"
    }
}

function Test-IsAdministratorAccount {
    param([string]$Name)
    try {
        $members = Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop
    }
    catch {
        return $null
    }
    foreach ($m in $members) {
        $short = ($m.Name -split '\\')[-1]
        if ($short -eq $Name) { return $true }
    }
    return $false
}

if ($env:OS -ne 'Windows_NT') {
    Write-Error '本脚本仅适用于 Windows。'
    exit 2
}

$script:IsElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

$sshdExe = Get-SshdExe

# 二进制与来源
if (-not $sshdExe) {
    Add-Check 'sshd 二进制' Fail '未找到 sshd.exe；服务端未安装'
}
else {
    $all = Get-Command sshd.exe -All -ErrorAction SilentlyContinue
    $version = (Get-Item -LiteralPath $sshdExe).VersionInfo.ProductVersion
    Add-Check 'sshd 二进制' Pass "$sshdExe（版本 $version）"
    if ($all.Count -gt 1) {
        Add-Check 'sshd 来源唯一性' Warn ("存在 $($all.Count) 份 sshd：$((($all | ForEach-Object { $_.Path }) -join '; '))")
    }
    else {
        Add-Check 'sshd 来源唯一性' Pass 'PATH 中只有一份 sshd'
    }

    # 同目录内客户端与服务端版本差异过大时，服务端多半是老载荷配新 crypto 库
    $sshExe = Join-Path (Split-Path -Parent $sshdExe) 'ssh.exe'
    if (Test-Path -LiteralPath $sshExe) {
        $clientVersion = (Get-Item -LiteralPath $sshExe).VersionInfo.ProductVersion
        $serverMatch = [regex]::Match($version, '(\d+)\.(\d+)')
        $clientMatch = [regex]::Match($clientVersion, '(\d+)\.(\d+)')
        if ($serverMatch.Success -and $clientMatch.Success) {
            $serverMajor = [int]$serverMatch.Groups[1].Value
            $clientMajor = [int]$clientMatch.Groups[1].Value
            if ($serverMajor -lt $clientMajor) {
                Add-Check '版本一致性' Warn "sshd $version 与 ssh $clientVersion 不同代；混装会导致服务启动失败（如 BN_init 入口缺失），建议换独立发行版"
            }
            else {
                Add-Check '版本一致性' Pass "sshd $version / ssh $clientVersion"
            }
        }
    }
}

try {
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' -ErrorAction Stop
    Add-Check '可选功能' Pass (($cap | ForEach-Object { "$($_.Name)=$($_.State)" }) -join '; ')
}
catch {
    Add-Check '可选功能' Unknown "需要管理员权限或系统不支持查询: $($_.Exception.Message)"
}

# 服务
$svc = Get-Service sshd -ErrorAction SilentlyContinue
if (-not $svc) {
    Add-Check 'sshd 服务' Fail '服务不存在'
}
else {
    $major = switch ($svc.Status) { 'Running' { 'Pass' } default { 'Fail' } }
    Add-Check 'sshd 服务' $major "$($svc.Status) / StartType=$($svc.StartType)"
    if ($svc.StartType -ne 'Automatic') {
        Add-Check '服务自启' Warn "启动类型为 $($svc.StartType)，重启后不会自动运行"
    }
    else {
        Add-Check '服务自启' Pass 'Automatic'
    }
}

$effective = @()
if ($sshdExe) {
    $pathCmd = Get-Command sshd.exe -ErrorAction SilentlyContinue
    if ($pathCmd -and $pathCmd.Path -ne $sshdExe) {
        Add-Check 'PATH 与服务一致' Warn "PATH 命中 $($pathCmd.Path)，服务实际使用 $sshdExe；两套并存时命令与配置容易错位"
    }
    else {
        Add-Check 'PATH 与服务一致' Pass 'sshd 命令与服务指向同一文件'
    }

    $isElevated = $script:IsElevated

    $syntax = & $sshdExe -t 2>&1
    $syntaxText = (@($syntax) | Out-String).Trim()
    if ($LASTEXITCODE -eq 0) {
        Add-Check 'sshd -t 语法' Pass '通过'
    }
    elseif ($syntaxText -match 'no hostkeys') {
        Add-Check 'sshd -t 语法' Unknown "$syntaxText（主机密钥仅 SYSTEM/Administrators 可读，需提权复核）"
    }
    elseif (-not $syntaxText) {
        Add-Check 'sshd -t 语法' Unknown '无输出且非零退出：多为非管理员读不到主机密钥，或进程入口解析失败（如 BN_init）'
    }
    else {
        Add-Check 'sshd -t 语法' Fail $syntaxText
    }

    if (-not $isElevated) {
        Add-Check 'sshd -T 生效配置' Unknown '需要管理员权限（读取主机密钥）'
        $effective = @()
    }
    else {
        $effective = & $sshdExe -T 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $effective) {
            Add-Check 'sshd -T 生效配置' Warn '取不到生效配置（服务未启动或版本不支持 -T）'
            $effective = @()
        }
        else {
            $wanted = 'port', 'passwordauthentication', 'pubkeyauthentication', 'authorizedkeysfile',
            'allowusers', 'denyusers', 'allowgroups', 'denygroups', 'authenticationmethods', 'syslogfacility'
            $picked = $effective | Where-Object { $_ -match ('^(' + ($wanted -join '|') + ')\s') }
            Add-Check 'sshd -T 生效配置' Info ($picked -join ' | ')
            $pw = ($effective | Where-Object { $_ -match '^passwordauthentication\s' }) -replace '^\S+\s+', ''
            if ($pw -eq 'no') {
                Add-Check '密码认证' Warn '已关闭（只允许公钥）'
            }
        }
    }
}

# 端口
if ($Port -eq 0) {
    foreach ($line in $effective) {
        if ($line -match '^port\s+(\d+)') { $Port = [int]$Matches[1]; break }
    }
}
if ($Port -eq 0) { $Port = 22 }

$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if (-not $listener) {
    Add-Check "端口 $Port 监听" Fail '没有进程在监听'
}
else {
    $pids = $listener | Select-Object -ExpandProperty OwningProcess -Unique
    $names = foreach ($p in $pids) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) { $proc.ProcessName } else { "pid=$p" }
    }
    $status = if ($names -contains 'sshd') { 'Pass' } else { 'Warn' }
    Add-Check "端口 $Port 监听" $status "持有进程：$($names -join ',')"
}

# 防火墙
$rule = $null
$fwError = $null
try {
    $rule = Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction Stop
}
catch {
    $fwError = $_
}

if ($fwError) {
    if (-not $script:IsElevated) {
        Add-Check '防火墙规则' Unknown '需要管理员权限读取防火墙规则'
    }
    else {
        Add-Check '防火墙规则' Fail "查询失败或规则不存在：$($fwError.Exception.Message)"
    }
}
elseif (-not $rule) {
    Add-Check '防火墙规则' Fail "缺少 OpenSSH-Server-In-TCP；入站 TCP $Port 未放行"
}
else {
    $filters = $rule | Get-NetFirewallPortFilter
    $rulePorts = ($filters.LocalPort | Select-Object -Unique) -join ','
    $detail = "Enabled=$($rule.Enabled) Direction=$($rule.Direction) Action=$($rule.Action) Port=$rulePorts"
    if ($rule.Enabled -ne 'True' -or $rule.Direction -ne 'Inbound' -or $rule.Action -ne 'Allow') {
        Add-Check '防火墙规则' Fail $detail
    }
    elseif ($rulePorts -notmatch "(^|,)$Port(,|$)") {
        Add-Check '防火墙规则' Fail "$detail（规则端口与监听端口 $Port 不一致）"
    }
    else {
        Add-Check '防火墙规则' Pass $detail
    }
}

# 主机密钥
$hostKeys = Get-ChildItem -Path (Join-Path $env:ProgramData 'ssh') -Filter 'ssh_host_*' -ErrorAction SilentlyContinue
if ($hostKeys) {
    Add-Check '主机密钥' Pass (($hostKeys | ForEach-Object { $_.Name }) -join ', ')
}
else {
    Add-Check '主机密钥' Warn '未找到 ssh_host_*，首次启动服务时会生成'
}

# 授权公钥
$isAdmin = Test-IsAdministratorAccount -Name $UserName
if ($isAdmin -eq $null) {
    Add-Check '账号归属' Unknown "无法读取本机管理员组成员，按普通用户处理"
}
elseif ($isAdmin) {
    Add-Check '账号归属' Info "$UserName 属于本机管理员组，公钥应放在 administrators_authorized_keys"
}
else {
    Add-Check '账号归属' Info "$UserName 不是本机管理员，公钥应放在用户目录 .ssh\authorized_keys"
}

$adminKeyFile = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
if ($isAdmin) {
    if (Test-Path -LiteralPath $adminKeyFile) {
        try {
            $lines = (Get-Content -LiteralPath $adminKeyFile -ErrorAction Stop | Where-Object { $_ -match '\S' }).Count
            Add-Check '管理员公钥文件' Pass "$adminKeyFile（$lines 行）; $(Format-AclSummary -Path $adminKeyFile)"
        }
        catch {
            Add-Check '管理员公钥文件' Unknown "$adminKeyFile 存在，但当前会话无权读取（仅 SYSTEM/Administrators），需提权复核"
        }
    }
    else {
        Add-Check '管理员公钥文件' Warn "$adminKeyFile 不存在，管理员暂时只能用密码登录"
    }
}

$userKeyFile = Join-Path $env:USERPROFILE '.ssh\authorized_keys'
if (Test-Path -LiteralPath $userKeyFile) {
    $lines = (Get-Content -LiteralPath $userKeyFile | Where-Object { $_ -match '\S' }).Count
    Add-Check '用户公钥文件' Info "$userKeyFile（$lines 行）; $(Format-AclSummary -Path $userKeyFile)"
}
else {
    Add-Check '用户公钥文件' Info "$userKeyFile 不存在"
}

# 默认 shell
$shellValue = (Get-ItemProperty 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -ErrorAction SilentlyContinue).DefaultShell
if (-not $shellValue) {
    Add-Check '默认 shell' Info '未设置，使用 cmd.exe'
}
elseif (Test-Path -LiteralPath $shellValue) {
    Add-Check '默认 shell' Pass $shellValue
}
else {
    Add-Check '默认 shell' Fail "$shellValue 不存在；登录会表现为密码错误，日志写 not allowed because shell does not exist"
}

# 日志
$logDir = Join-Path $env:ProgramData 'ssh\logs'
$logFiles = @(Get-ChildItem -Path $logDir -Filter '*.log' -ErrorAction SilentlyContinue)
if ($logFiles.Count -gt 0) {
    Add-Check '文件日志' Pass (($logFiles | ForEach-Object { "$($_.Name)($($_.Length)B)" }) -join ', ')
}
else {
    Add-Check '文件日志' Info '未启用 SyslogFacility LOCAL0，日志只写事件日志'
}
$eventLog = Get-WinEvent -ListLog 'OpenSSH/Operational' -ErrorAction SilentlyContinue
if ($eventLog) {
    Add-Check '事件日志' Pass "OpenSSH/Operational 可读（$($eventLog.RecordCount) 条）"
}
else {
    Add-Check '事件日志' Warn 'OpenSSH/Operational 不存在，服务可能从未启动'
}

$script:Checks | Format-Table -AutoSize -Wrap

if ($IncludeEvents -and $eventLog) {
    Write-Output ''
    Write-Output '最近 OpenSSH/Operational 事件：'
    Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 10 -ErrorAction SilentlyContinue |
        Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-List
}

$failed = @($script:Checks | Where-Object Status -eq 'Fail').Count
$warned = @($script:Checks | Where-Object Status -eq 'Warn').Count
Write-Output ''
Write-Output ("结果：Fail {0} 项，Warn {1} 项，共 {2} 项检查。" -f $failed, $warned, $script:Checks.Count)

if ($failed -gt 0) { exit 1 }
exit 0
