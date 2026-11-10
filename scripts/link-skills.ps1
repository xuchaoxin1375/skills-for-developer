#Requires -Version 5.1
<#
.SYNOPSIS
  [Windows 专用] 将本仓库 skills/ 下的每个 skill 通过 Junction 链接到各 harness 的 skills 目录。
  Linux/macOS 请用 scripts/link-skills.sh（symlink）。

.DESCRIPTION
  唯一真源: <repo>/skills/<name>/ (内含 SKILL.md)。
  Harness 侧只放 Junction, 不存实体:
    - OpenCode : $env:USERPROFILE\.config\opencode\skills
    - Codex    : $env:USERPROFILE\.codex\skills
    - Claude   : $env:USERPROFILE\.claude\skills
    - Agents 通用: $env:DSH_AGENTS_HOME\skills (默认 $env:USERPROFILE\.agents\skills)
    - DeepSeek Harness (dsh): $env:DSH_HOME\skills (默认 $env:USERPROFILE\.dsh\skills)

  第三方 skill 登记在 config/third-party-skills.txt, 实体不入本仓库,
  由 scripts/third-party-skills.py 安装到 $env:THIRD_PARTY_SKILLS_HOME
  (默认 $env:USERPROFILE\.local\share\skills-for-developer\third-party),
  并在各 harness 目录建链接。

  幂等, 可反复执行。只管理仓库中存在的 skill 名, 并顺手清理指向本仓库
  但目标已不存在的悬空链接 (重命名/删除 skill 的残留);
  不会动 harness 自带内容 (如 Codex 的 .system/、AGENTS.md)。

.PARAMETER RepoRoot
  仓库根目录, 默认自动推导为脚本所在目录的上级。

.PARAMETER Include
  只处理指定的 skill 名 (默认处理 skills/ 下全部含 SKILL.md 的目录)。

.PARAMETER Unlink
  移除本仓库创建的 Junction (仅移除指向本仓库的链接, 实体目录不动)。

.PARAMETER VerifyOnly
  只检查链接状态与全局 AGENTS.md 是否漂移, 不做任何修改;
  悬空链接 (目标已不存在) 也计为异常。
  有异常时以非零退出码返回 (AGENTS 缺失计异常, 内容不一致只警告; 允许本机定制)。

.PARAMETER Plan
  只打印部署计划, 不修改链接、配置或依赖。

.PARAMETER ApplyRecommendedCli
  直接应用仓库推荐的 opencode cli.json (config/opencode/cli.json),
  不询问。原文件先备份为同目录 cli.json.bak-<时间戳>。

.PARAMETER SkipRecommendedCli
  跳过推荐 cli.json 的询问与应用。

.PARAMETER ApplyRecommendedSkills
  直接安装推荐 skill (config/recommended-skills.txt) 的依赖，不询问。

.PARAMETER SkipRecommendedSkills
  跳过推荐 skill 的依赖与命令安装（含 VerifyOnly 中的对应检查)。

.PARAMETER ApplyThirdPartySkills
  安装/更新 config/third-party-skills.txt 中登记的第三方 skill，不询问。

.PARAMETER SkipThirdPartySkills
  跳过第三方 skill 的安装与校验。

.PARAMETER SyncThirdPartySkills
  同步第三方 skill：安装缺失，并在名单 ref 变化时更新；保留 preserve 文件。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -ApplyRecommendedCli

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Plan
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Include doc-rewrite-review,htmlmini
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -SyncThirdPartySkills
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [string[]]$Include,
  [switch]$Unlink,
  [switch]$VerifyOnly,
  [switch]$Plan,
  [switch]$Quiet,
  [switch]$ApplyRecommendedCli,
  [switch]$SkipRecommendedCli,
  [switch]$ApplyRecommendedSkills,
  [switch]$SkipRecommendedSkills,
  [switch]$ApplyThirdPartySkills,
  [switch]$SkipThirdPartySkills,
  [switch]$SyncThirdPartySkills
)

$ErrorActionPreference = 'Stop'

# -Quiet 只隐藏逐项成功/进度行，警告、失败和最终汇总照常输出。
function Write-Step([string]$Message) { if (-not $Quiet) { Write-Host $Message } }

function Test-FileEqual([string]$Left, [string]$Right) {
  # 不用 Get-FileHash: 部分 5.1 环境的 PSModulePath 被其他版本污染, 自动加载会失败
  $a = [System.IO.File]::ReadAllBytes($Left)
  $b = [System.IO.File]::ReadAllBytes($Right)
  if ($a.Length -ne $b.Length) { return $false }
  for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }
  return $true
}

# -File 调用时逗号分隔值会作为单个字符串传入；统一拆成名字数组。
if ($Include) {
  $Include = @($Include | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

# 默认 UTF-8：5.1 控制台默认 GBK，直接输出中文会被采集侧按 UTF-8 解错；
# 脚本内设为 UTF-8（仅影响本进程），pwsh 7 下同样无害。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
  $base = $PSScriptRoot
  if ([string]::IsNullOrWhiteSpace($base)) { $base = Split-Path -Parent $MyInvocation.MyCommand.Path }
  $RepoRoot = (Resolve-Path (Join-Path $base '..')).Path
}

$skillsDir = Join-Path $RepoRoot 'skills'
if (-not (Test-Path $skillsDir -PathType Container)) {
  Write-Error "skills 目录不存在: $skillsDir"
  exit 1
}

$dshHome = if (-not [string]::IsNullOrWhiteSpace($env:DSH_HOME)) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
$agentsHome = if (-not [string]::IsNullOrWhiteSpace($env:DSH_AGENTS_HOME)) { $env:DSH_AGENTS_HOME } else { Join-Path $env:USERPROFILE '.agents' }

$targets = @(
  (Join-Path $env:USERPROFILE '.config\opencode\skills'),
  (Join-Path $env:USERPROFILE '.codex\skills'),
  (Join-Path $env:USERPROFILE '.claude\skills'),
  (Join-Path $agentsHome 'skills'),
  (Join-Path $dshHome 'skills')
)

$skills = Get-ChildItem -Path $skillsDir -Directory | Where-Object {
  Test-Path (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
}
if ($Include -and $Include.Count -gt 0) {
  $skills = $skills | Where-Object { $Include -contains $_.Name }
}
$upstreamSelected = $false
$upstreamConfigFile = Join-Path $RepoRoot 'config\upstream-skills.json'
if (-not $SkipThirdPartySkills -and -not $Unlink -and (Test-Path -LiteralPath $upstreamConfigFile -PathType Leaf)) {
  $upstreamConfigData = Get-Content -LiteralPath $upstreamConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach ($repository in $upstreamConfigData.repositories) {
    foreach ($name in $repository.skills.PSObject.Properties.Name) {
      if (-not $Include -or $Include -contains $name) { $upstreamSelected = $true }
    }
  }
}
if ((-not $skills -or $skills.Count -eq 0) -and -not $upstreamSelected) {
  Write-Error '没有可处理的 skill (skills/ 下需要有含 SKILL.md 的子目录)。'
  exit 1
}
$skills = @($skills | Where-Object { $null -ne $_ })

foreach ($s in (Get-ChildItem -Path $skillsDir -Directory)) {
  if (-not (Test-Path (Join-Path $s.FullName 'SKILL.md') -PathType Leaf)) {
    Write-Warning "跳过 $($s.Name): 缺少 SKILL.md"
  }
}

function Get-LinkTarget([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  if ($null -eq $item) { return $null }
  # Junction / Symlink 都会带 LinkType; 普通目录则 LinkType 为空
  if ([string]::IsNullOrEmpty($item.LinkType)) { return $null }
  return $item.Target
}

function Remove-StaleRepoLinks([string]$TargetDir) {
  # 清理指向本仓库 skills\ 但目标已不存在的 Junction/Symlink:
  # skill 重命名或删除后, 旧链接不在“仓库现有 skill”名单里, 正常循环不会碰到。
  # 只处理指向本仓库 skills\ 的链接, 不动指向别处的内容与实体目录。
  # VerifyOnly 下只报告并计为异常; -Include 时只清理名单内的名字。
  if (-not (Test-Path -LiteralPath $TargetDir -PathType Container)) { return }
  $skillsRoot = (Resolve-Path -LiteralPath $skillsDir).Path.TrimEnd('\')
  foreach ($entry in (Get-ChildItem -LiteralPath $TargetDir -Force -ErrorAction SilentlyContinue)) {
    $targets = Get-LinkTarget $entry.FullName
    if ($null -eq $targets) { continue }
    $owned = $false
    $alive = $false
    foreach ($t in @($targets)) {
      if ([string]::IsNullOrWhiteSpace($t)) { continue }
      $clean = $t.TrimEnd('\')
      if (-not [System.IO.Path]::IsPathRooted($clean)) {
        $clean = [System.IO.Path]::GetFullPath((Join-Path $TargetDir $clean))
      }
      if ($clean -ieq $skillsRoot -or $clean.StartsWith($skillsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        $owned = $true
        if (Test-Path -LiteralPath $t) { $alive = $true }
      }
    }
    if (-not $owned -or $alive) { continue }
    if ($Include -and $Include.Count -gt 0 -and -not ($Include -contains $entry.Name)) { continue }
    if ($VerifyOnly) {
      Write-Warning "  [$($entry.Name)] 悬空链接 (目标已不存在), 重跑链接脚本清理"
      $script:failures++
      continue
    }
    if ($PSCmdlet.ShouldProcess($entry.FullName, '清理悬空链接')) {
      Remove-Item -LiteralPath $entry.FullName -Force
      Write-Step "  [$($entry.Name)] 悬空链接已清理 (目标不存在)"
    }
  }
}

$failures = 0

# -Plan 只预览，不创建目录、不改链接。
if (-not $Plan) {
foreach ($targetDir in $targets) {
  Write-Step "== $targetDir =="
  if (-not (Test-Path $targetDir -PathType Container)) {
    if ($VerifyOnly) {
      Write-Warning "  缺失目录 (VerifyOnly, 不创建): $targetDir"
      $failures++
      continue
    }
    if ($PSCmdlet.ShouldProcess($targetDir, '创建 harness skills 目录')) {
      New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
      Write-Step '  创建目录'
    }
  }

  foreach ($skill in $skills) {
    $link = Join-Path $targetDir $skill.Name
    $dest = $skill.FullName
    $label = "  [$($skill.Name)]"

    if ($Unlink) {
      $cur = Get-LinkTarget $link
      if ($null -eq $cur) {
        Write-Step "$label 无链接, 跳过"
        continue
      }
      # 只有指向本仓库的才删, 防止误删用户手工链到别处的内容
      if ($cur -contains $dest -or $cur -eq $dest) {
        if ($VerifyOnly) {
          Write-Step "$label 将被移除 (VerifyOnly)"
          continue
        }
        if ($PSCmdlet.ShouldProcess($link, "移除 Junction -> $dest")) {
          Remove-Item -LiteralPath $link -Force
          Write-Step "$label 已移除"
        }
      } else {
        Write-Warning "$label 是指向别处的链接 ($cur), 不动"
      }
      continue
    }

    if (-not (Test-Path -LiteralPath $link)) {
      if ($VerifyOnly) {
        Write-Warning "$label 缺失 (期望 -> $dest)"
        $failures++
        continue
      }
      if ($PSCmdlet.ShouldProcess($link, "创建 Junction -> $dest")) {
        New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
        Write-Step "$label 已创建 -> $dest"
      }
      continue
    }

    $cur = Get-LinkTarget $link
    if ($null -ne $cur -and ($cur -eq $dest -or $cur -contains $dest)) {
      Write-Step "$label OK"
      # 顺手验证 SKILL.md 可读
      if (-not (Test-Path (Join-Path $link 'SKILL.md') -PathType Leaf)) {
        Write-Warning "$label 链接存在但 SKILL.md 不可读"
        $failures++
      }
      continue
    }

    if ($null -ne $cur) {
      # 是链接但指错地方
      if ($VerifyOnly) {
        Write-Warning "$label 指向错误: $cur (期望 $dest)"
        $failures++
        continue
      }
      if ($PSCmdlet.ShouldProcess($link, "纠正链接 $cur -> $dest")) {
        Remove-Item -LiteralPath $link -Force
        New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
        Write-Step "$label 已纠正 -> $dest"
      }
      continue
    }

    # 走到这里: link 路径上是实体目录/文件, 备份到 skills 目录之外的
    # ~/.skills-migration-backup/<时间戳>/<harness>/ 下, 避免备份留在原地被 harness 误扫为重复 skill
    if ($VerifyOnly) {
      Write-Warning "$label 是实体目录/文件, 需备份后替换为 Junction"
      $failures++
      continue
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $harness = 'other'
    if ($targetDir -match 'opencode') { $harness = 'opencode' }
    elseif ($targetDir -match '\.codex') { $harness = 'codex' }
    elseif ($targetDir -match '\.claude') { $harness = 'claude' }
    elseif ($targetDir -match '\.agents') { $harness = 'agents' }
    elseif ($targetDir -match '\.dsh') { $harness = 'dsh' }
    $backup = Join-Path (Join-Path (Join-Path (Join-Path $env:USERPROFILE '.skills-migration-backup') $stamp) $harness) $skill.Name
    if ($PSCmdlet.ShouldProcess($link, "备份实体到 $backup 并创建 Junction -> $dest")) {
      New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
      Move-Item -LiteralPath $link -Destination $backup -Force
      New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
      Write-Step "$label 实体已备份到 $backup, 链接已创建"
    }
  }

  Remove-StaleRepoLinks $targetDir
}
}

# --- 推荐 skill（需依赖/命令安装，名单见 config/recommended-skills.txt） ---

function Get-RecommendedSkills {
  # 返回推荐名单与 -Include 交集后的 skill 名数组；
  # 名单中有但仓库无目录的不返回（由 check-skills.py 报错）。
  $listFile = Join-Path $RepoRoot 'config\recommended-skills.txt'
  if (-not (Test-Path -LiteralPath $listFile -PathType Leaf)) { return @() }
  $out = @()
  foreach ($raw in (Get-Content -LiteralPath $listFile -Encoding UTF8)) {
    $name = ($raw -split '#', 2)[0].Trim()
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    if ($Include -and $Include.Count -gt 0 -and -not ($Include -contains $name)) { continue }
    if (Test-Path (Join-Path $skillsDir $name) -PathType Container) { $out += $name }
  }
  return $out
}

function Get-SkillCommandName([string]$Skill) {
  # 有 CLI 入口的 skill 在此登记命令名；无命令入口返回空
  switch ($Skill) { 'htmlmini' { return 'htmlmini' } }
  return ''
}

function Get-SkillCommandEntry([string]$Skill) {
  # 命令包装的入口脚本绝对路径；无则返回空
  switch ($Skill) { 'htmlmini' { return (Join-Path $skillsDir 'htmlmini\src\cli.js') } }
  return ''
}

function Install-RecommendedSkillDeps([string]$Skill) {
  # 含 package.json 则跑包管理器安装（优先 pnpm）；返回是否成功
  $dir = Join-Path $skillsDir $Skill
  if (-not (Test-Path (Join-Path $dir 'package.json') -PathType Leaf)) { return $true }
  Write-Host "  [$Skill] 安装依赖…"
  $pm = $null
  if (Get-Command pnpm -ErrorAction SilentlyContinue) { $pm = 'pnpm' }
  elseif (Get-Command npm -ErrorAction SilentlyContinue) { $pm = 'npm' }
  if ($null -eq $pm) {
    Write-Warning "  [$Skill] 未找到 pnpm/npm，跳过依赖安装"
    return $false
  }
  try {
    Push-Location -LiteralPath $dir
    & $pm install
    if ($LASTEXITCODE -ne 0) { throw "$pm install 退出码 $LASTEXITCODE" }
    return $true
  } catch {
    Write-Warning "  [$Skill] 依赖安装失败，跳过：$_"
    return $false
  } finally {
    Pop-Location
  }
}

function Get-CommandBinDir {
  return (Join-Path $env:USERPROFILE '.local\bin')
}

function Test-CommandReady([string]$Command) {
  # 命令就绪: 当前进程能找到, 或 bin 目录已在用户 PATH (新开终端生效, 本次进程未必继承)
  if (Get-Command $Command -ErrorAction SilentlyContinue) { return $true }
  $binDir = (Get-CommandBinDir).TrimEnd('\')
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if ([string]::IsNullOrEmpty($userPath)) { return $false }
  return [bool](($userPath -split ';') | Where-Object { $_ -ne '' -and $_.TrimEnd('\') -ieq $binDir })
}

function Ensure-BinInUserPath([string]$BinDir) {
  # 用户 PATH 缺该目录则追加（用户级，无需管理员；新开终端生效）
  $cur = [Environment]::GetEnvironmentVariable('Path', 'User')
  if ([string]::IsNullOrEmpty($cur)) { $cur = '' }
  $hit = ($cur -split ';') | Where-Object { $_.TrimEnd('\') -ieq $BinDir.TrimEnd('\') -and $_ -ne '' }
  if ($hit) { return }
  if ($PSCmdlet.ShouldProcess('用户 PATH', "追加 $BinDir")) {
    [Environment]::SetEnvironmentVariable('Path', ($cur.TrimEnd(';') + ';' + $BinDir), 'User')
    if (($env:Path -split ';') -notcontains $BinDir) { $env:Path += ';' + $BinDir }
    Write-Host "  已把 $BinDir 加入用户 PATH（新开终端生效）。"
  }
}

function Install-SkillCommand([string]$Skill) {
  # 默认把 CLI 装成 <binDir>\<cmd>.cmd 包装（幂等）；入口路径含非 ASCII 时跳过
  #（cmd 对 shim 编码敏感，报出来比写坏 shim 好）
  $cmd = Get-SkillCommandName $Skill
  $entry = Get-SkillCommandEntry $Skill
  if ([string]::IsNullOrWhiteSpace($cmd) -or [string]::IsNullOrWhiteSpace($entry)) { return }
  if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    Write-Warning "  [$Skill] 入口不存在，跳过命令安装: $entry"
    return
  }
  if ($entry -match '[^\x00-\x7F]') {
    Write-Warning "  [$Skill] 入口路径含非 ASCII，跳过命令安装: $entry"
    return
  }
  $binDir = Get-CommandBinDir
  New-Item -ItemType Directory -Force -Path $binDir | Out-Null
  $shim = Join-Path $binDir "$cmd.cmd"
  $body = "@node `"$entry`" %*"
  $isOurs = (Test-Path -LiteralPath $shim -PathType Leaf) -and `
    ((Get-Content -LiteralPath $shim -Raw -Encoding UTF8 -ErrorAction SilentlyContinue) -match [regex]::Escape($entry))
  if ($isOurs) {
    Write-Host "  [$Skill] 命令已就绪: $shim"
  } elseif ($PSCmdlet.ShouldProcess($shim, "安装 $cmd 命令")) {
    Set-Content -LiteralPath $shim -Value $body -Encoding ASCII
    Write-Host "  [$Skill] 命令已安装: $shim"
  }
  Ensure-BinInUserPath $binDir
}

function Remove-SkillCommand([string]$Skill) {
  # 只删本仓库安装的包装（内容含真源入口路径），不动他人命令
  $cmd = Get-SkillCommandName $Skill
  $entry = Get-SkillCommandEntry $Skill
  if ([string]::IsNullOrWhiteSpace($cmd)) { return }
  $shim = Join-Path (Get-CommandBinDir) "$cmd.cmd"
  $isOurs = (Test-Path -LiteralPath $shim -PathType Leaf) -and `
    ((Get-Content -LiteralPath $shim -Raw -Encoding UTF8 -ErrorAction SilentlyContinue) -match [regex]::Escape($entry))
  if ($isOurs) {
    if ($PSCmdlet.ShouldProcess($shim, "移除 $cmd 命令")) {
      Remove-Item -LiteralPath $shim -Force
      Write-Host "  [$Skill] 命令已移除: $shim"
    }
  } else {
    Write-Host "  [$Skill] 命令不存在或非本仓库安装，不动: $shim"
  }
}

# --- 第三方 skill（名单见 config/third-party-skills.txt；实体不入本仓库） ---

function Get-ThirdPartySkillNames {
  # 返回名单与 -Include 交集后的名称；实体由 third-party-skills.py 管理。
  $listFile = Join-Path $RepoRoot 'config\third-party-skills.txt'
  if (-not (Test-Path -LiteralPath $listFile -PathType Leaf)) { return @() }
  $out = @()
  foreach ($raw in (Get-Content -LiteralPath $listFile -Encoding UTF8)) {
    $line = ($raw -split '#', 2)[0].Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $name = ($line -split '\|')[0].Trim()
    if ([string]::IsNullOrWhiteSpace($name)) { continue }
    if ($Include -and $Include.Count -gt 0 -and -not ($Include -contains $name)) { continue }
    $out += $name
  }
  return $out
}

function Get-PythonCommand {
  foreach ($exe in @('python', 'python3')) {
    $cmd = Get-Command $exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $cmd) { return $cmd.Source }
  }
  return $null
}

function Get-ThirdPartyArgs([string]$Action, [string[]]$Names) {
  $script = Join-Path $RepoRoot 'scripts\third-party-skills.py'
  $pyArgs = @('-X', 'utf8', $script, $Action)
  foreach ($n in @($Names)) {
    if (-not [string]::IsNullOrWhiteSpace($n)) { $pyArgs += @('--name', $n) }
  }
  return $pyArgs
}

function Get-PlanLinkCounts {
  $create = 0; $replace = 0; $ok = 0; $missingDirs = 0
  foreach ($targetDir in $targets) {
    if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) { $missingDirs++ }
    foreach ($skill in @($skills)) {
      $link = Join-Path $targetDir $skill.Name
      $dest = $skill.FullName
      if (-not (Test-Path -LiteralPath $link)) { $create++; continue }
      $cur = Get-LinkTarget $link
      if ($null -ne $cur -and ($cur -eq $dest -or $cur -contains $dest)) { $ok++ }
      else { $replace++ }
    }
  }
  return [pscustomobject]@{ Create = $create; Replace = $replace; Ok = $ok; MissingDirs = $missingDirs }
}

function Get-PlanCliState {
  $repoCli = Join-Path (Join-Path (Join-Path $RepoRoot 'config') 'opencode') 'cli.json'
  if (-not (Test-Path -LiteralPath $repoCli -PathType Leaf)) { return 'absent' }
  $dstCli = Join-Path (Join-Path $env:USERPROFILE '.config\opencode') 'cli.json'
  if (-not (Test-Path -LiteralPath $dstCli -PathType Leaf)) { return 'missing' }
  if (Test-FileEqual $repoCli $dstCli) { return 'same' }
  return 'different'
}

function Get-PlanRecState([string]$Skill) {
  $dir = Join-Path $skillsDir $Skill
  $needDeps = (Test-Path (Join-Path $dir 'package.json') -PathType Leaf) -and `
    -not (Test-Path (Join-Path $dir 'node_modules') -PathType Container)
  $needCmd = $false
  $cmd = Get-SkillCommandName $Skill
  $entry = Get-SkillCommandEntry $Skill
  if (-not [string]::IsNullOrWhiteSpace($cmd) -and -not [string]::IsNullOrWhiteSpace($entry)) {
    $shim = Join-Path (Get-CommandBinDir) "$cmd.cmd"
    $isOurs = (Test-Path -LiteralPath $shim -PathType Leaf) -and `
      ((Get-Content -LiteralPath $shim -Raw -Encoding UTF8 -ErrorAction SilentlyContinue) -match [regex]::Escape($entry))
    $onPath = Test-CommandReady $cmd
    if (-not ($isOurs -and $onPath)) { $needCmd = $true }
  }
  return [pscustomobject]@{ Skill = $Skill; NeedDeps = $needDeps; NeedCmd = $needCmd }
}

function Get-ThirdPartyField([string]$Name, [string]$Field) {
  $listFile = Join-Path $RepoRoot 'config\third-party-skills.txt'
  if (-not (Test-Path -LiteralPath $listFile -PathType Leaf)) { return '' }
  foreach ($raw in (Get-Content -LiteralPath $listFile -Encoding UTF8)) {
    $line = ($raw -split '#', 2)[0].Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $parts = $line -split '\|'
    if ($parts.Count -lt 6) { continue }
    if ($parts[0].Trim() -ne $Name) { continue }
    switch ($Field) {
      'repo' { return $parts[1].Trim() }
      'kind' { return $parts[2].Trim() }
      'ref' { return $parts[3].Trim() }
    }
  }
  return ''
}

function Get-PlanTpState([string]$Name) {
  $tpHome = if (-not [string]::IsNullOrWhiteSpace($env:THIRD_PARTY_SKILLS_HOME)) {
    $env:THIRD_PARTY_SKILLS_HOME
  } else {
    Join-Path $env:USERPROFILE '.local\share\skills-for-developer\third-party'
  }
  if (Test-Path (Join-Path $tpHome $Name) -PathType Container) { return '已安装' }
  return '未安装'
}

function Show-DeployPlan {
  $counts = Get-PlanLinkCounts
  Write-Host '== 部署计划（只预览，不修改）=='
  Write-Host "  链接: $(@($skills).Count) 个 skill -> $($targets.Count) 个目录；新建 $($counts.Create)，修正/替换 $($counts.Replace)，已就绪 $($counts.Ok)；缺目录 $($counts.MissingDirs)"
  switch (Get-PlanCliState) {
    'same' { Write-Host '  cli.json: 已是最新（跳过）' }
    'missing' { Write-Host '  cli.json: 目标不存在（交互默认应用，-ApplyRecommendedCli 可直接应用）' }
    'different' { Write-Host '  cli.json: 与真源不同（交互默认保留，覆盖前备份）' }
    'absent' { Write-Host '  cli.json: 仓库没有推荐文件（跳过）' }
  }
  foreach ($s in @(Get-RecommendedSkills)) {
    $st = Get-PlanRecState $s
    $state = @()
    if ($st.NeedDeps) { $state += '依赖未安装' }
    if ($st.NeedCmd) { $state += '命令未安装' }
    if ($state.Count -eq 0) { $state = @('已就绪') }
    Write-Host "  推荐 skill [$s]: $($state -join ' ')"
  }
  foreach ($n in @(Get-ThirdPartySkillNames)) {
    $repo = Get-ThirdPartyField $n 'repo'
    $ref = Get-ThirdPartyField $n 'ref'
    Write-Host "  第三方 [$n]: $(Get-PlanTpState $n) 来源 $repo@$ref（默认不装）"
  }
  if (Test-Path (Join-Path $RepoRoot 'config\upstream-skills.json') -PathType Leaf) {
    Write-Host '  上游 clone 链接: 由 link-upstream-skills.py 检查/修正'
  }
  Write-Host '  本脚本未自动处理（scripts/deploy.ps1 会串起来）: 全局 AGENTS.md 合并、OpenCode 插件链接、依赖套餐检查'
}

function Show-DeploySummary {
  Write-Host '== 完成 =='
  Write-Host "- skill 链接: 已处理 $(@($skills).Count) 个 -> $($targets.Count) 个目录"
  if ($SkipRecommendedCli) {
    Write-Host '- cli.json: 已跳过（-SkipRecommendedCli）'
  } else {
    switch (Get-PlanCliState) {
      'same' { Write-Host '- cli.json: 已就绪' }
      'absent' { Write-Host '- cli.json: 仓库没有推荐文件' }
      default { Write-Host '- cli.json: 未应用（可重跑并确认，或用 -ApplyRecommendedCli）' }
    }
  }
  if ($SkipRecommendedSkills) {
    Write-Host '- 推荐 skill: 已跳过（-SkipRecommendedSkills）'
  } else {
    foreach ($s in @(Get-RecommendedSkills)) {
      $st = Get-PlanRecState $s
      $state = @()
      if ($st.NeedDeps) { $state += '依赖未安装' }
      if ($st.NeedCmd) { $state += '命令未安装' }
      if ($state.Count -eq 0) { Write-Host "- 推荐 skill [$s]: 已就绪" }
      else { Write-Host "- 推荐 skill [$s]: $($state -join ' ')" }
    }
  }
  if ($SkipThirdPartySkills) {
    Write-Host '- 第三方 skill: 已跳过（-SkipThirdPartySkills）'
  } else {
    foreach ($n in @(Get-ThirdPartySkillNames)) {
      Write-Host "- 第三方 [$n]: $(Get-PlanTpState $n)"
    }
  }
  Write-Host '- 本脚本未处理（scripts/deploy.ps1 会串起来）: 全局 AGENTS.md 合并、OpenCode 插件链接、依赖套餐检查'
  Write-Host '  依赖检查: python -X utf8 scripts/check-skill-deps.py --profile standard'
}

if ($Plan) {
  Show-DeployPlan
  exit 0
}

if (-not $Unlink -and -not $VerifyOnly) {
  # 推荐 cli.json: 缺失或与真源不一致时, 交互终端下询问是否应用;
  # 非交互环境默认跳过 (用 -ApplyRecommendedCli 显式应用)。
  $repoCli = Join-Path (Join-Path (Join-Path $RepoRoot 'config') 'opencode') 'cli.json'
  if (Test-Path -LiteralPath $repoCli -PathType Leaf) {
    $dstDir = Join-Path $env:USERPROFILE '.config\opencode'
    $dstCli = Join-Path $dstDir 'cli.json'
    $inSync = (Test-Path -LiteralPath $dstCli -PathType Leaf) -and (Test-FileEqual $repoCli $dstCli)
    if ($inSync) {
      Write-Host '推荐 cli.json 已是最新。'
    } elseif ($SkipRecommendedCli) {
      Write-Host '已跳过推荐 cli.json (-SkipRecommendedCli)。'
    } else {
      $doApply = $false
      if ($ApplyRecommendedCli) {
        $doApply = $true
      } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        if (-not (Test-Path -LiteralPath $dstCli -PathType Leaf)) {
          $ans = Read-Host '推荐 cli.json 不存在, 是否应用? [Y/n]'
          $doApply = $ans -match '^([yY]([eE][sS])?)?$'
        } else {
          $ans = Read-Host '推荐 cli.json 与当前配置不同 (覆盖前备份), 是否应用? [y/N]'
          $doApply = $ans -match '^(y|Y|yes|YES)$'
        }
      } else {
        Write-Host '非交互环境, 跳过推荐 cli.json (用 -ApplyRecommendedCli 应用)。'
      }
      if ($doApply -and $PSCmdlet.ShouldProcess($dstCli, '应用推荐 cli.json')) {
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        if (Test-Path -LiteralPath $dstCli -PathType Leaf) {
          $bak = "$dstCli.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
          Copy-Item -LiteralPath $dstCli -Destination $bak -Force
          Write-Host "原 cli.json 已备份到 $bak"
        }
        Copy-Item -LiteralPath $repoCli -Destination $dstCli -Force
        Write-Host '推荐 cli.json 已应用。'
      }
    }
  }

  # 推荐 skill（需依赖/命令）：只对未就绪项询问，依赖与命令合并确认；
  # 非交互默认跳过依赖，命令仍默认安装
  $recSkills = @(Get-RecommendedSkills)
  if ($recSkills.Count -gt 0) {
    if ($SkipRecommendedSkills) {
      Write-Host "已跳过推荐 skill 部署（-SkipRecommendedSkills）：$($recSkills -join ', ')"
    } else {
      $recPlan = @()
      $needAny = $false
      $needDepsAny = $false
      $actions = @()
      foreach ($s in $recSkills) {
        $st = Get-PlanRecState $s
        $recPlan += [pscustomobject]@{ Skill = $s; State = $st }
        if ($st.NeedDeps -or $st.NeedCmd) {
          $needAny = $true
          if ($st.NeedDeps) {
            $needDepsAny = $true
            if ($actions -notcontains '依赖') { $actions += '依赖' }
          }
          if ($st.NeedCmd -and $actions -notcontains '命令') { $actions += '命令' }
        }
      }
      if (-not $needAny) {
        Write-Host "推荐 skill 已就绪：$($recSkills -join ', ')"
      } else {
        $hint = if ($needDepsAny) { '（依赖安装会联网）' } else { '' }
        Write-Host "== 推荐 skill（需依赖/命令）：$($recSkills -join ', ') =="
        $mode = 'skip'
        if ($ApplyRecommendedSkills) {
          $mode = 'all'
        } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
          $ans = Read-Host "安装/创建推荐 skill 的$($actions -join '+')$hint？[Y/n]"
          if ($ans -match '^([yY]([eE][sS])?)?$') { $mode = 'all' }
        } else {
          Write-Host '非交互环境，跳过依赖安装（用 -ApplyRecommendedSkills 执行）；命令仍默认安装。'
          $mode = 'cmd'
        }
        if ($mode -eq 'skip') {
          Write-Host '已跳过推荐 skill（依赖与命令均未改动）。'
        } else {
          foreach ($item in $recPlan) {
            $s = $item.Skill
            $st = $item.State
            if ($mode -eq 'all' -and $st.NeedDeps) {
              if (-not (Install-RecommendedSkillDeps $s)) {
                Write-Warning "  [$s] 依赖安装未完成，命令照常安装"
              }
            }
            if ($st.NeedCmd) {
              Install-SkillCommand $s
            }
          }
        }
      }
    }
  }

  # 第三方 skill：实体不入库，交互默认 No；非交互默认跳过。
  $tpNames = @(Get-ThirdPartySkillNames)
  if ($tpNames.Count -gt 0) {
    if ($SkipThirdPartySkills) {
      Write-Host "已跳过第三方 skill（-SkipThirdPartySkills）：$($tpNames -join ', ')"
    } elseif ($SyncThirdPartySkills) {
      Write-Host "== 第三方 skill 同步：$($tpNames -join ', ') =="
      $py = Get-PythonCommand
      if ($null -eq $py) {
        Write-Warning '未找到 Python，跳过第三方 skill 同步（需要 Python 3.6+）。'
      } else {
        $tpArgs = @(Get-ThirdPartyArgs 'sync' $tpNames)
        & $py @tpArgs
        if ($LASTEXITCODE -ne 0) { Write-Warning "第三方 skill 同步失败（退出码 $LASTEXITCODE）。" }
      }
    } else {
      $doTp = $false
      if ($ApplyThirdPartySkills) {
        $doTp = $true
      } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $tpDetail = @()
        foreach ($n in $tpNames) {
          $repo = Get-ThirdPartyField $n 'repo'
          $ref = Get-ThirdPartyField $n 'ref'
          $tpDetail += "$n（$(Get-PlanTpState $n)，$repo@$ref）"
        }
        $ans = Read-Host "是否安装/更新第三方 skill（$($tpDetail -join ', ')；来自上游，默认 No）？[y/N]"
        $doTp = $ans -match '^(y|Y|yes|YES)$'
      } else {
        Write-Host '非交互环境，跳过第三方 skill（用 -ApplyThirdPartySkills 或 -SyncThirdPartySkills）。'
      }
      if ($doTp) {
        Write-Host "== 第三方 skill：$($tpNames -join ', ') =="
        $py = Get-PythonCommand
        if ($null -eq $py) {
          Write-Warning '未找到 Python，跳过第三方 skill 安装（需要 Python 3.6+）。'
        } else {
          $tpArgs = @(Get-ThirdPartyArgs 'install' $tpNames)
          & $py @tpArgs
          if ($LASTEXITCODE -ne 0) { Write-Warning "第三方 skill 安装失败（退出码 $LASTEXITCODE）。" }
        }
      }
    }
  }
}

if ($Unlink) {
  # --unlink 时同步移除本仓库安装的命令；依赖目录（node_modules）保留
  if ($VerifyOnly) {
    foreach ($s in @(Get-RecommendedSkills)) { Write-Host "  [$s] 命令将被移除 (VerifyOnly)" }
  } else {
    foreach ($s in @(Get-RecommendedSkills)) { Remove-SkillCommand $s }
    Write-Host '注：推荐 skill 的依赖目录（如 node_modules）已保留，按需手工删除。'
  }
  if (@(Get-ThirdPartySkillNames).Count -gt 0) {
    Write-Host '注：第三方 skill 不在 -Unlink 范围；卸载用 python -X utf8 scripts/third-party-skills.py uninstall --name <name>'
  }
}

if ($VerifyOnly) {
  $repoAgents = Join-Path (Join-Path $RepoRoot 'config') 'global-AGENTS.md'
  if (Test-Path -LiteralPath $repoAgents -PathType Leaf) {
    # 每个消费全局 AGENTS.md 的 harness 一个目标路径, 与 README「全局 AGENTS.md 同步与合并」保持一致
    $agentsTargets = @(
      @{ Name = 'OpenCode'; Path = Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md' }
      @{ Name = 'ZCode'; Path = Join-Path $env:USERPROFILE '.zcode\AGENTS.md' }
    )
    foreach ($t in $agentsTargets) {
      if (-not (Test-Path -LiteralPath $t.Path -PathType Leaf)) {
        Write-Warning "全局 AGENTS.md($($t.Name)) 缺失 (期望按 README 从 config/global-AGENTS.md 恢复)"
        $failures++
      } elseif (-not (Test-FileEqual $repoAgents $t.Path)) {
        Write-Warning "全局 AGENTS.md($($t.Name)) 与真源存在差异（允许本机定制；确认通用条目一致即可）"
      } else {
        Write-Host "全局 AGENTS.md($($t.Name)) 与真源一致。"
      }
    }
  }

  if (-not $SkipRecommendedSkills) {
    foreach ($s in @(Get-RecommendedSkills)) {
      if ((Test-Path (Join-Path $skillsDir "$s\package.json") -PathType Leaf) -and `
          -not (Test-Path (Join-Path $skillsDir "$s\node_modules") -PathType Container)) {
        Write-Warning "推荐 skill [$s] 依赖未安装（缺 node_modules，用 -ApplyRecommendedSkills 部署）"
        $failures++
      }
      $cmd = Get-SkillCommandName $s
      $entry = Get-SkillCommandEntry $s
      if (-not [string]::IsNullOrWhiteSpace($cmd)) {
        $shim = Join-Path (Get-CommandBinDir) "$cmd.cmd"
        $isOurs = (Test-Path -LiteralPath $shim -PathType Leaf) -and `
          ((Get-Content -LiteralPath $shim -Raw -Encoding UTF8 -ErrorAction SilentlyContinue) -match [regex]::Escape($entry))
        $onPath = Test-CommandReady $cmd
        if ($isOurs -and $onPath) {
          Write-Step "推荐 skill [$s] 命令 OK：$cmd"
        } else {
          Write-Warning "推荐 skill [$s] 命令缺失（期望 $shim 可用，重跑链接脚本安装）"
          $failures++
        }
      }
    }
  }

  if (-not $SkipThirdPartySkills) {
    $tpNames = @(Get-ThirdPartySkillNames)
    if ($tpNames.Count -gt 0) {
      $py = Get-PythonCommand
      if ($null -eq $py) {
        Write-Host '未找到 Python，跳过第三方 skill 校验。'
      } else {
        $tpArgs = @(Get-ThirdPartyArgs 'verify' $tpNames)
        & $py @tpArgs
        if ($LASTEXITCODE -ne 0) {
          Write-Warning '第三方 skill 校验失败（运行 -SyncThirdPartySkills，或用 status 查看细节）。'
          $failures++
        }
      }
    }
  }
}

if (-not $Unlink -and -not $SkipThirdPartySkills) {
  $upstreamConfig = Join-Path $RepoRoot 'config\upstream-skills.json'
  if (Test-Path -LiteralPath $upstreamConfig -PathType Leaf) {
    $py = Get-PythonCommand
    if ($null -eq $py) {
      Write-Warning 'Python missing; upstream clone links were NOT checked.'
      $failures++
    } elseif ($VerifyOnly -or $PSCmdlet.ShouldProcess($upstreamConfig, 'Link selected upstream skills (no network)')) {
      $upstreamArgs = @('-X', 'utf8', (Join-Path $RepoRoot 'scripts\link-upstream-skills.py'), '--repo-root', $RepoRoot)
      if ($VerifyOnly) { $upstreamArgs += '--verify-only' }
      foreach ($name in @($Include)) {
        if (-not [string]::IsNullOrWhiteSpace($name)) { $upstreamArgs += @('--include', $name) }
      }
      & $py @upstreamArgs
      if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Upstream clone link check failed; see docs/upstream-skills.md.'
        $failures++
        if (-not $VerifyOnly) { exit 1 }
      }
    }
  }
}

if ($VerifyOnly) {
  if ($failures -gt 0) {
    Write-Warning "校验发现 $failures 处异常, 见上。"
    exit 1
  }
  Write-Host '全部链接正常。'
}

if (-not $VerifyOnly -and -not $Unlink) {
  # 推荐工具：只检测并提示，不自动安装；缺失不阻断部署
  $basicTools = @(
    @{ Label = 'git'; Commands = @('git'); Install = 'winget install Git.Git' }
    @{ Label = 'ripgrep（rg）'; Commands = @('rg'); Install = 'winget install BurntSushi.ripgrep.MSVC' }
    @{ Label = 'fd'; Commands = @('fd', 'fdfind'); Install = 'winget install sharkdp.fd' }
    @{ Label = 'Scrapling'; Commands = @('scrapling'); Install = 'uv tool install "scrapling[fetchers]"（再运行 scrapling install）' }
    @{ Label = 'Playwright'; Commands = @('playwright'); Install = 'python -m pip install playwright; python -m playwright install chromium' }
  )
  foreach ($tool in $basicTools) {
    $located = $null
    foreach ($command in $tool.Commands) {
      $found = Get-Command $command -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($found) {
        $located = $found
        break
      }
    }
    if ($located) {
      Write-Step "推荐工具 $($tool.Label) 可用：$($located.Source)"
    } else {
      Write-Step "建议安装 $($tool.Label)（推荐，缺失不阻断）：$($tool.Install)"
    }
  }
  Show-DeploySummary
}
