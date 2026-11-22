<#
.SYNOPSIS
    卸载 Windows OpenSSH Server：停用服务、按安装方式移除程序、清理防火墙规则，可选清除配置与主机密钥。

.DESCRIPTION
    按实际安装方式选择卸载路径：MSI 产品走 msiexec，in-box 可选功能走 Remove-WindowsCapability，
    zip 手工注册的服务用 sc delete 注销。执行顺序固定为：停服务 → 移程序 → 删防火墙规则 → 可选清数据。

    默认保留 %ProgramData%\ssh（sshd_config、主机密钥、administrators_authorized_keys），
    重新安装后可沿用同一主机指纹与授权公钥；只有显式 -PurgeData 才删除该目录，
    删除后主机密钥会重新生成，已记录旧指纹的客户端会提示 host key 变化。

    幂等：服务不存在、规则不存在、产品已卸载都按“已完成”处理。支持 -WhatIf 预览。

.PARAMETER PurgeData
    同时删除 %ProgramData%\ssh 下的配置、主机密钥与管理员授权公钥。不可撤销。

.PARAMETER KeepFirewallRule
    保留防火墙规则。上层统一策略或改用其他端口时使用。

.PARAMETER KeepConfigBackups
    -PurgeData 时保留 sshd_config.bak-* 备份，只删运行数据与密钥。

.EXAMPLE
    pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1 -WhatIf

    先看会做哪些动作，不动系统。

.EXAMPLE
    pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1

    只卸程序与服务，保留配置和主机密钥，便于以后重装。

.EXAMPLE
    pwsh -NoProfile -File ./Uninstall-WindowsSshServer.ps1 -PurgeData

    彻底清除：程序、服务、防火墙规则、配置与主机密钥。

.NOTES
    需要管理员会话。卸载 in-box 可选功能可能返回 RestartNeeded=True，旧二进制要重启后才消失。
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [switch]$PurgeData,
    [switch]$KeepFirewallRule,
    [switch]$KeepConfigBackups
)

$ErrorActionPreference = 'Stop'
$script:RuleName = 'OpenSSH-Server-In-TCP'
$script:DataDir = Join-Path $env:ProgramData 'ssh'
$script:Summary = New-Object System.Collections.Generic.List[object]

function Write-Step {
    param([string]$Message)
    Write-Host ('[{0:HH:mm:ss}] {1}' -f (Get-Date), $Message)
}

function Add-Summary {
    param([string]$Action, [string]$Result)
    $script:Summary.Add([pscustomobject]@{ Action = $Action; Result = $Result })
}

function Assert-Administrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        [Console]::Error.WriteLine('需要管理员会话：请以“以管理员身份运行”的 PowerShell 重新执行。')
        exit 2
    }
}

function Get-ServiceImagePath {
    param([string]$Name)
    $svc = Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if (-not $svc -or -not $svc.PathName) { return $null }
    $raw = $svc.PathName.Trim()
    if ($raw.StartsWith('"')) {
        $end = $raw.IndexOf('"', 1)
        if ($end -gt 0) { return $raw.Substring(1, $end - 1) }
    }
    return ($raw -split '\s+')[0]
}

function Find-MsiProduct {
    param([string]$Pattern)
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $roots) {
        Get-ChildItem $root -ErrorAction SilentlyContinue | ForEach-Object {
            $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
            if ($props.DisplayName -and $props.DisplayName -match $Pattern) {
                [pscustomobject]@{ DisplayName = $props.DisplayName; ProductCode = $_.PSChildName }
            }
        }
    }
}

if ($env:OS -ne 'Windows_NT') {
    Write-Error '本脚本仅适用于 Windows。'
    exit 2
}
Assert-Administrator

# 停服务
Write-Step '停用 sshd 服务'
$service = Get-Service sshd -ErrorAction SilentlyContinue
if (-not $service) {
    Add-Summary 'sshd 服务' '不存在，跳过'
}
else {
    if ($PSCmdlet.ShouldProcess('sshd', '停止并禁用服务')) {
        if ($service.Status -ne 'Stopped') {
            Stop-Service sshd -Force -ErrorAction SilentlyContinue
        }
        Set-Service sshd -StartupType Disabled -ErrorAction SilentlyContinue
        Add-Summary 'sshd 服务' '已停止并禁用'
    }
}

$imagePath = Get-ServiceImagePath -Name 'sshd'

# 移程序
Write-Step '按安装方式移除程序'
$msi = @(Find-MsiProduct -Pattern '^OpenSSH') | Select-Object -First 1
if ($msi) {
    if ($PSCmdlet.ShouldProcess($msi.DisplayName, 'msiexec 卸载')) {
        $proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/x', $msi.ProductCode, '/qn', '/norestart') -Wait -PassThru
        if ($proc.ExitCode -in 0, 3010) {
            Add-Summary 'MSI 卸载' "$($msi.DisplayName)（退出码 $($proc.ExitCode)）"
        }
        else {
            Add-Summary 'MSI 卸载' "失败：$($msi.DisplayName) 退出码 $($proc.ExitCode)；未继续尝试其他卸载路径"
        }
    }
}
else {
    $capability = $null
    try {
        $capability = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' -ErrorAction Stop |
            Where-Object State -eq 'Installed' | Select-Object -First 1
    }
    catch {
        Write-Verbose "可选功能查询失败：$($_.Exception.Message)"
    }

    if ($capability) {
        if ($PSCmdlet.ShouldProcess($capability.Name, '移除可选功能')) {
            $result = Remove-WindowsCapability -Online -Name $capability.Name -ErrorAction Stop
            Add-Summary '可选功能' "已移除（RestartNeeded=$($result.RestartNeeded)）"
        }
    }
    elseif ($service) {
        if ($PSCmdlet.ShouldProcess('sshd', '删除服务注册')) {
            sc.exe delete sshd | Out-Null
            sc.exe delete ssh-agent | Out-Null
            Add-Summary '服务注册' '已用 sc delete 删除 sshd 与 ssh-agent'
        }
    }
    else {
        Add-Summary '程序' '未发现 MSI 产品、可选功能或服务注册'
    }
}

if ($imagePath) {
    Add-Summary '原二进制' $imagePath
}

# 防火墙
if (-not $KeepFirewallRule) {
    Write-Step '清理防火墙规则'
    $rule = Get-NetFirewallRule -Name $script:RuleName -ErrorAction SilentlyContinue
    if (-not $rule) {
        Add-Summary '防火墙规则' '不存在，跳过'
    }
    elseif ($PSCmdlet.ShouldProcess($script:RuleName, '删除防火墙规则')) {
        Remove-NetFirewallRule -Name $script:RuleName -ErrorAction Stop
        Add-Summary '防火墙规则' '已删除'
    }
}
else {
    Add-Summary '防火墙规则' '按 -KeepFirewallRule 保留'
}

# 数据
Write-Step '处理配置与主机密钥'
if (-not (Test-Path -LiteralPath $script:DataDir)) {
    Add-Summary '数据目录' "$($script:DataDir) 不存在，跳过"
}
elseif (-not $PurgeData) {
    Add-Summary '数据目录' "保留 $($script:DataDir)（含主机密钥与授权公钥；彻底清除用 -PurgeData）"
}
elseif ($PSCmdlet.ShouldProcess($script:DataDir, '删除配置、主机密钥与授权公钥')) {
    if ($KeepConfigBackups) {
        Get-ChildItem -Path $script:DataDir -Filter 'sshd_config.bak-*' -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item $_.FullName (Join-Path $env:TEMP $_.Name) -Force }
        Add-Summary '配置备份' "已复制到 $env:TEMP"
    }
    Remove-Item -LiteralPath $script:DataDir -Recurse -Force -ErrorAction Stop
    Add-Summary '数据目录' "已删除 $($script:DataDir)"
}

Write-Output ''
$script:Summary | Format-Table -AutoSize -Wrap

if ($WhatIfPreference) {
    Write-Output ''
    Write-Output 'WhatIf 模式：只列出将要执行的动作，未做任何修改。'
    exit 0
}

Write-Output ''
Write-Output '如需确认是否还有残留：Get-Service sshd,ssh-agent -ErrorAction SilentlyContinue；'
Write-Output ('检查 ' + $script:DataDir + ' 与 System32\OpenSSH 下的 sshd.exe 是否已消失；卸载可选功能后旧文件通常要重启才移除。')
exit 0
