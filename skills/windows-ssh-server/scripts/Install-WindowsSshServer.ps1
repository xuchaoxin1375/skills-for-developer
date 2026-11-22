<#
.SYNOPSIS
    幂等部署 Windows OpenSSH Server：安装、服务自启、端口与防火墙、认证配置、默认 shell、管理员公钥。

.DESCRIPTION
    只做“确保”动作：缺什么补什么，已符合就跳过，重复执行安全。整个过程不重写 sshd_config，
    只在全局区（第一个 Match 块之前）增改需要的指令，改动前自动备份为 sshd_config.bak-<时间戳>。

    执行顺序：
    - 安装 OpenSSH Server（可选功能优先，失败可回退 MSI/zip）
    - 确保 sshd 服务存在、启动类型为 Automatic、处于运行状态
    - 在配置文件全局区确保 Port、PubkeyAuthentication、PasswordAuthentication
    - 同步入站防火墙规则的端口（规则端口改不了，不一致时删了重建）
    - 按需设置默认 shell 及其远程命令参数
    - 按需追加授权公钥，管理员账号自动写到 administrators_authorized_keys 并收紧 ACL
    - sshd -t 校验后重启服务，等待端口进入监听

    副作用：安装系统可选功能或运行外部安装包、创建/删除防火墙规则、修改 sshd_config 与注册表
    HKLM:\SOFTWARE\OpenSSH、重启 sshd 服务。支持 -WhatIf 预览。

.PARAMETER Port
    服务监听端口，默认 22。非 22 时同时改写配置与防火墙规则。

.PARAMETER DefaultShell
    默认 shell：keep 保持现状（默认），cmd、powershell（5.1）、pwsh（PowerShell 7）。
    选中的可执行文件必须已存在，否则登录会表现为密码错误。

.PARAMETER DisablePasswordAuthentication
    写入 PasswordAuthentication no，只允许公钥登录。默认不传，即确保密码认证可用，
    便于首次登录上传公钥。

.PARAMETER AddAuthorizedKey
    要追加的公钥内容，可传多行或多条。按 -AuthorizedKeyUser 是否属于本机管理员组
    自动选择文件，重复公钥不会重复写入。

.PARAMETER AuthorizedKeyUser
    公钥归属账号，默认当前用户。

.PARAMETER InstallSource
    auto（默认，可选功能优先，失败时若给了 -PackagePath 则回退）、capability、msi、zip。

.PARAMETER PackagePath
    msi 或 zip 安装包的路径；InstallSource 为 msi/zip 时必填。

.PARAMETER SkipFirewallRule
    不动防火墙规则，用于上层的统一策略已经放行端口的场景。

.EXAMPLE
    pwsh -NoProfile -File ./Install-WindowsSshServer.ps1 -Port 22 -DefaultShell pwsh

    常规部署：装服务端、放行 22、默认 shell 换成 PowerShell 7。

.EXAMPLE
    $key = Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub" -Raw
    pwsh -NoProfile -File ./Install-WindowsSshServer.ps1 -AddAuthorizedKey $key -DisablePasswordAuthentication

    配好公钥后关闭密码认证。

.EXAMPLE
    pwsh -NoProfile -File ./Install-WindowsSshServer.ps1 -InstallSource msi -PackagePath <path-to-openssh.msi>

    内网或长期服务版装不上可选功能时，走 MSI。

.NOTES
    需要管理员会话。不适用：只想当 SSH 客户端、或需要在 WSL 发行版内跑 sshd。
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 22,

    [ValidateSet('keep', 'cmd', 'powershell', 'pwsh')]
    [string]$DefaultShell = 'keep',

    [switch]$DisablePasswordAuthentication,

    [string[]]$AddAuthorizedKey,

    [string]$AuthorizedKeyUser = $env:USERNAME,

    [ValidateSet('auto', 'capability', 'msi', 'zip')]
    [string]$InstallSource = 'auto',

    [string]$PackagePath,

    [switch]$SkipFirewallRule
)

$ErrorActionPreference = 'Stop'
$script:ConfigPath = Join-Path $env:ProgramData 'ssh\sshd_config'
$script:RuleName = 'OpenSSH-Server-In-TCP'
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
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        [Console]::Error.WriteLine('需要管理员会话：请以“以管理员身份运行”的 PowerShell 重新执行。')
        exit 2
    }
}

function Get-SshdExePath {
    # 以服务实际加载的二进制为准：PATH 上可能残留另一套（如待重启才移除的 in-box 版本）
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

function Install-SshdServer {
    $source = $InstallSource
    if ($source -eq 'auto') {
        if ($PackagePath) {
            $source = if ([IO.Path]::GetExtension($PackagePath) -match '^\.msi$') { 'msi' } else { 'zip' }
        }
        else {
            $source = 'capability'
        }
    }

    if ($source -eq 'capability') {
        Write-Step '通过可选功能安装 OpenSSH Server（需要能访问 Windows Update）'
        try {
            $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' -ErrorAction Stop
            if ($cap.State -eq 'Installed') {
                Add-Summary '安装可选功能' '已安装，跳过'
                return
            }
            if (-not $PSCmdlet.ShouldProcess('OpenSSH.Server~~~~0.0.1.0', '安装可选功能')) { return }
            $result = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction Stop
            Add-Summary '安装可选功能' "完成（RestartNeeded=$($result.RestartNeeded)）"
            return
        }
        catch {
            $msg = $_.Exception.Message
            if ($InstallSource -eq 'auto' -and $PackagePath) {
                Write-Warning "可选功能安装失败（$msg），改用 -PackagePath 指向的安装包"
                $source = if ([IO.Path]::GetExtension($PackagePath) -match '^\.msi$') { 'msi' } else { 'zip' }
            }
            else {
                throw "可选功能安装失败：$msg`n内网/长期服务版常见于此；改用 -InstallSource msi|zip 并提供 -PackagePath，或参考 references/install-fallbacks.md。"
            }
        }
    }

    if (-not $PackagePath) {
        throw "InstallSource=$source 需要同时提供 -PackagePath。"
    }
    if (-not (Test-Path -LiteralPath $PackagePath)) {
        throw "安装包不存在：$PackagePath"
    }

    if ($source -eq 'msi') {
        Write-Step "用 MSI 安装服务端：$PackagePath"
        if (-not $PSCmdlet.ShouldProcess($PackagePath, 'msiexec 安装 OpenSSH Server')) { return }
        $msiArgs = @('/i', (Resolve-Path -LiteralPath $PackagePath).Path, 'ADDLOCAL=Server', '/qn', '/norestart')
        $proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList $msiArgs -Wait -PassThru
        if ($proc.ExitCode -notin 0, 3010) {
            throw "msiexec 退出码 $($proc.ExitCode)，安装失败。"
        }
        Add-Summary '安装 MSI' "完成（退出码 $($proc.ExitCode)）"
        return
    }

    Write-Step "用 zip 安装：$PackagePath"
    $target = Join-Path $env:ProgramFiles 'OpenSSH'
    if (-not (Test-Path -LiteralPath $target)) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    }
    if (-not $PSCmdlet.ShouldProcess($PackagePath, "解压到 $target 并注册 sshd 服务")) { return }
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $target -Force
    $installer = Get-ChildItem -Path $target -Filter 'install-sshd.ps1' -Recurse |
        Select-Object -First 1
    if (-not $installer) {
        throw "解压后未找到 install-sshd.ps1：$target"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "install-sshd.ps1 退出码 $LASTEXITCODE。"
    }
    Add-Summary '安装 zip' "完成（$($installer.DirectoryName)）"
}

function Set-SshdGlobalDirective {
    param(
        [string]$Key,
        [string]$Value
    )
    $lines = [IO.File]::ReadAllLines($script:ConfigPath)
    $matchIndex = $lines.Count
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*Match\s') { $matchIndex = $i; break }
    }
    $head = if ($matchIndex -gt 0) { @($lines[0..($matchIndex - 1)]) } else { @() }
    $tail = if ($matchIndex -lt $lines.Count) { @($lines[$matchIndex..($lines.Count - 1)]) } else { @() }

    $pattern = '^\s*#?\s*' + [regex]::Escape($Key) + '(\s|$)'
    $kept = @($head | Where-Object { $_ -notmatch $pattern })

    $newLine = "$Key $Value"
    $alreadySet = @($head | Where-Object { $_ -match ('^\s*' + [regex]::Escape($Key) + '\s+' + [regex]::Escape($Value) + '\s*$') }).Count -gt 0
    if ($alreadySet -and $kept.Count -eq ($head.Count - 1)) {
        return
    }

    $merged = @($kept) + @($newLine)
    if ($tail.Count -gt 0) { $merged += @('') + $tail }
    [IO.File]::WriteAllLines($script:ConfigPath, $merged, (New-Object Text.UTF8Encoding($false)))
    Add-Summary "配置 $Key" $Value
}

function Sync-FirewallRule {
    $existing = Get-NetFirewallRule -Name $script:RuleName -ErrorAction SilentlyContinue
    if ($existing) {
        $ports = @($existing | Get-NetFirewallPortFilter | Select-Object -ExpandProperty LocalPort -Unique) -join ','
        if ($ports -match "(^|,)$Port(,|$)") {
            if ($existing.Enabled -ne 'True' -or $existing.Direction -ne 'Inbound' -or $existing.Action -ne 'Allow') {
                if ($PSCmdlet.ShouldProcess($script:RuleName, '修正为启用、入站、允许')) {
                    Set-NetFirewallRule -Name $script:RuleName -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop
                    Add-Summary '防火墙规则' "已修正为 Enabled/Inbound/Allow，端口 $ports"
                }
            }
            else {
                Add-Summary '防火墙规则' "已存在且匹配端口 $ports，跳过"
            }
            return
        }
        Write-Step "规则端口为 $ports，与目标端口 $Port 不一致，删除后重建"
        if (-not $PSCmdlet.ShouldProcess($script:RuleName, "删除规则并以端口 $Port 重建")) { return }
        Remove-NetFirewallRule -Name $script:RuleName -ErrorAction Stop
    }

    if (-not $PSCmdlet.ShouldProcess("TCP $Port 入站", '创建防火墙放行规则')) { return }
    New-NetFirewallRule -Name $script:RuleName -DisplayName 'OpenSSH Server (sshd)' `
        -Description 'Inbound SSH access to OpenSSH Server' `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort $Port -ErrorAction Stop | Out-Null
    Add-Summary '防火墙规则' "已创建，放行 TCP $Port"
}

function Set-DefaultShellSetting {
    $map = @{
        cmd        = @{ Path = Join-Path $env:SystemRoot 'System32\cmd.exe'; Option = '/c' }
        powershell = @{ Path = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'; Option = '-c' }
    }
    if ($DefaultShell -eq 'pwsh') {
        $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
        if (-not $pwsh) {
            throw '未找到 pwsh.exe：先安装 PowerShell 7，或改用 -DefaultShell powershell|cmd。'
        }
        $map['pwsh'] = @{ Path = $pwsh.Path; Option = '-c' }
    }

    $target = $map[$DefaultShell]
    if (-not (Test-Path -LiteralPath $target.Path)) {
        throw "默认 shell 不存在：$($target.Path)。按此路径设置会让所有登录表现为密码错误。"
    }

    # 包管理器的 current 目录多为 Junction，sshd 会报 “shell ... does not exist”，改记真实版本路径
    $parent = Get-Item -LiteralPath (Split-Path -Parent $target.Path) -Force -ErrorAction SilentlyContinue
    if ($parent -and $parent.LinkType -in 'Junction', 'SymbolicLink' -and $parent.Target) {
        $realPath = Join-Path ($parent.Target | Select-Object -First 1) (Split-Path -Leaf $target.Path)
        if (Test-Path -LiteralPath $realPath) {
            Write-Warning "默认 shell 的上级目录是链接（$($parent.FullName) -> $($parent.Target)），改用真实路径 $realPath；包管理器升级后会失效，届时重跑本脚本即可。"
            $target = @{ Path = $realPath; Option = $target.Option }
        }
    }

    if (-not $PSCmdlet.ShouldProcess("HKLM:\SOFTWARE\OpenSSH", "设置 DefaultShell=$($target.Path)")) { return }

    if (-not (Test-Path 'HKLM:\SOFTWARE\OpenSSH')) {
        New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
    }
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value $target.Path -PropertyType String -Force | Out-Null
    New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShellCommandOption -Value $target.Option -PropertyType String -Force | Out-Null
    Add-Summary '默认 shell' "$($target.Path)（远程命令参数 $($target.Option)）"
}

function Test-AdministratorAccount {
    param([string]$Name)
    $members = Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop
    foreach ($m in $members) {
        if ((($m.Name -split '\\')[-1]) -eq $Name) { return $true }
    }
    return $false
}

function Set-AdministratorsKeyAcl {
    param([string]$Path)
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRule($rule) }
    $adminSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $systemSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($adminSid, 'FullControl', 'Allow')))
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($systemSid, 'FullControl', 'Allow')))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Add-SshAuthorizedKey {
    param([string]$KeyText, [string]$UserName)

    $keyPattern = '(?:^|\s)(ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-[a-z0-9-]+|sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)\s+([A-Za-z0-9+/=]+)'
    $incoming = New-Object System.Collections.Generic.List[object]
    foreach ($line in ($KeyText -split "`r?`n")) {
        if ($line -match $keyPattern) {
            $incoming.Add([pscustomobject]@{ Line = $line.Trim(); Blob = $Matches[2] })
        }
    }
    if ($incoming.Count -eq 0) {
        throw 'AddAuthorizedKey 里没有识别到公钥（应形如 ssh-ed25519 AAAA... 或 ecdsa-sha2-nistp256 AAAA...）。'
    }

    $isAdmin = Test-AdministratorAccount -Name $UserName
    if ($isAdmin) {
        $keyFile = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
    }
    else {
        $keyFile = Join-Path $env:USERPROFILE '.ssh\authorized_keys'
    }

    $existingBlobs = @()
    if (Test-Path -LiteralPath $keyFile) {
        $existingBlobs = @(Get-Content -LiteralPath $keyFile | ForEach-Object {
                if ($_ -match $keyPattern) { $Matches[2] }
            })
    }

    $toAdd = @($incoming | Where-Object { $existingBlobs -notcontains $_.Blob } | ForEach-Object { $_.Line })
    if ($toAdd.Count -eq 0) {
        Add-Summary '授权公钥' '已存在相同公钥，跳过'
        if ($isAdmin) { Set-AdministratorsKeyAcl -Path $keyFile }
        return
    }

    if (-not $PSCmdlet.ShouldProcess($keyFile, "追加 $($toAdd.Count) 条公钥")) { return }
    $dir = Split-Path -Parent $keyFile
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $keyFile)) {
        New-Item -ItemType File -Path $keyFile -Force | Out-Null
    }
    [IO.File]::AppendAllLines($keyFile, [string[]]$toAdd, (New-Object Text.UTF8Encoding($false)))
    if ($isAdmin) {
        Set-AdministratorsKeyAcl -Path $keyFile
        Add-Summary '授权公钥' "$keyFile（管理员文件，ACL 已收紧）"
    }
    else {
        Add-Summary '授权公钥' "$keyFile"
    }
}

function Wait-SshdListening {
    param([int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($conn) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# 主流程
if ($env:OS -ne 'Windows_NT') {
    Write-Error '本脚本仅适用于 Windows。'
    exit 2
}
Assert-Administrator

Write-Step '检查 sshd 是否已安装'
$sshdExe = Get-SshdExePath
if (-not $sshdExe) {
    Install-SshdServer
    $sshdExe = Get-SshdExePath
    if (-not $sshdExe) {
        throw '安装后仍未找到 sshd.exe；查 references/install-fallbacks.md。'
    }
}
else {
    Add-Summary '安装' "已存在：$sshdExe"
}

$service = Get-Service sshd -ErrorAction SilentlyContinue
if (-not $service) {
    throw 'sshd 服务不存在：安装包已就位但服务未注册。zip 安装需先运行 install-sshd.ps1。'
}

Write-Step '确保配置文件存在'
if (-not (Test-Path -LiteralPath $script:ConfigPath)) {
    $startError = $null
    try { Start-Service sshd -ErrorAction Stop }
    catch { $startError = $_.Exception.Message }
    if (-not (Test-Path -LiteralPath $script:ConfigPath)) {
        $version = (Get-Item -LiteralPath $sshdExe).VersionInfo.ProductVersion
        throw @"
服务未能启动，且没有生成 $($script:ConfigPath)。
sshd 版本：$version
服务错误：$startError
按以下顺序排查：
- 可选功能版本的 sshd 与同目录 ssh.exe 不同代（如 sshd 7.7 配 ssh 9.5）时，会因缺少 BN_init 等旧符号启动失败；改用 -InstallSource msi -PackagePath <msi> 换独立发行版。
- 端口被 WSL 或其他 sshd 占用：改 -Port。
- 手工前台运行 sshd -d -e 看完整报错。
"@
    }
    Add-Summary '配置文件' '首次启动时生成'
}

Write-Step '确保服务启动类型与运行状态'
if ($service.StartType -ne 'Automatic') {
    if ($PSCmdlet.ShouldProcess('sshd', '设置启动类型为 Automatic')) {
        Set-Service -Name sshd -StartupType Automatic -ErrorAction Stop
        Add-Summary '服务启动类型' 'Automatic'
    }
}
else {
    Add-Summary '服务启动类型' '已是 Automatic'
}
$service.Refresh()
if ($service.Status -ne 'Running') {
    if ($PSCmdlet.ShouldProcess('sshd', '启动服务')) {
        Start-Service sshd -ErrorAction Stop
        Add-Summary '服务状态' '已启动'
    }
}
else {
    Add-Summary '服务状态' '已在运行'
}

Write-Step '同步 sshd_config 全局指令'
$backup = "$($script:ConfigPath).bak-$(Get-Date -f yyyyMMddHHmmss)"
if ($PSCmdlet.ShouldProcess($script:ConfigPath, '备份并增改全局指令')) {
    Copy-Item -LiteralPath $script:ConfigPath -Destination $backup -Force
    Add-Summary '配置备份' $backup
    if ($Port -ne 22) {
        Set-SshdGlobalDirective -Key 'Port' -Value $Port
    }
    Set-SshdGlobalDirective -Key 'PubkeyAuthentication' -Value 'yes'
    $passwordValue = if ($DisablePasswordAuthentication) { 'no' } else { 'yes' }
    Set-SshdGlobalDirective -Key 'PasswordAuthentication' -Value $passwordValue
}

if (-not $SkipFirewallRule) {
    Write-Step "同步防火墙规则端口 $Port"
    Sync-FirewallRule
}
else {
    Add-Summary '防火墙规则' '按 -SkipFirewallRule 跳过'
}

if ($DefaultShell -ne 'keep') {
    Write-Step "设置默认 shell：$DefaultShell"
    Set-DefaultShellSetting
}
else {
    Add-Summary '默认 shell' '保持现状'
}

if ($AddAuthorizedKey) {
    Write-Step "为 $AuthorizedKeyUser 追加授权公钥"
    Add-SshAuthorizedKey -KeyText ($AddAuthorizedKey -join "`n") -UserName $AuthorizedKeyUser
}

Write-Step '校验配置并重启服务'
if ($PSCmdlet.ShouldProcess('sshd', '校验配置并重启服务')) {
    $test = $null
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $test = & $sshdExe -t 2>&1
        if ($LASTEXITCODE -eq 0) { break }
        # 首次启动可能仍在生成主机密钥；sshd -t 读不到密钥时会直接退出
        Start-Sleep -Seconds 2
    }
    $testText = (@($test) | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -and $testText) {
        Copy-Item -LiteralPath $backup -Destination $script:ConfigPath -Force
        throw "sshd -t 校验失败，已回滚配置：$testText"
    }
    if ($LASTEXITCODE -ne 0 -and -not $testText) {
        Add-Summary 'sshd -t' '无输出且非零退出（多为主机密钥暂不可读），以服务启动结果为准'
    }
    else {
        Add-Summary 'sshd -t' '通过'
    }
    Restart-Service sshd -ErrorAction Stop
    if (-not (Wait-SshdListening -TimeoutSeconds 15)) {
        throw "服务已重启但端口 $Port 未进入监听；用 sshd -d -e 查看绑定错误（常见为端口被 WSL 或其他 sshd 占用）。"
    }
    Add-Summary '服务重启' "端口 $Port 已在监听"
}

Write-Output ''
$script:Summary | Format-Table -AutoSize -Wrap

if ($WhatIfPreference) {
    Write-Output ''
    Write-Output 'WhatIf 模式：只列出将要执行的动作，未做任何修改。'
    exit 0
}

Write-Output ''
Write-Output ("下一步：ssh -o BatchMode=yes $AuthorizedKeyUser@<host> exit  验证免密；")
Write-Output ("        或 ssh $AuthorizedKeyUser@<host> -p $Port 验证密码登录；")
Write-Output '        再跑 Test-WindowsSshServer.ps1 复核。'
exit 0
