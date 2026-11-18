#Requires -Version 5.1
<#
.SYNOPSIS
  一键部署：git submodule 检查、skill 链接、OpenCode 插件链接、全局 AGENTS.md 恢复与校验。

.DESCRIPTION
  串联 git submodule 检查、link-skills.ps1、link-plugins.ps1 与全局 AGENTS.md 同步，避免分开执行时漏步。
  未初始化的子模块默认自动拉取，失败只警告，不阻塞其他 skill。
  默认只链 Agents 通用目录；未选择 opencode 时自动跳过插件、全局 AGENTS.md 与 cli.json。
  选中 OpenCode 时，AGENTS.md 缺失才复制，内容不一致只警告；ZCode 仅在 ~/.zcode 存在时尝试
  symlink 到 OpenCode 副本，无符号链接权限时跳过（不复制、不计失败）。
  结束时打印各阶段耗时与效率复盘提示，便于发现部署流程劣化。

.PARAMETER RepoRoot
  仓库根目录，默认自动推导为脚本所在目录的上级。

.PARAMETER Harness
  目标 harness 列表，逗号分隔: opencode/codex/claude/agents/dsh/all。
  默认 agents，只链 Agents 通用目录；未选择 opencode 时自动跳过插件、全局 AGENTS.md 与 cli.json。

.PARAMETER Plan
  只预览，不修改任何文件。

.PARAMETER VerifyOnly
  只校验链接、插件运行态、子模块与 AGENTS.md 状态，不修改。

.PARAMETER Quiet
  隐藏逐项成功/进度行，保留警告、失败与汇总。

.PARAMETER SkipPlugins
  跳过 OpenCode 插件链接。

.PARAMETER SkipGlobalAgents
  跳过全局 AGENTS.md 恢复/校验。

.PARAMETER SkipDepCheck
  跳过依赖套餐检查。

.PARAMETER SkipSubmodules
  跳过 git submodule 的初始化与检查。

.PARAMETER ApplyRecommendedCli
.PARAMETER SkipRecommendedCli
.PARAMETER ApplyRecommendedSkills
.PARAMETER SkipRecommendedSkills
.PARAMETER ApplyThirdPartySkills
.PARAMETER SkipThirdPartySkills
.PARAMETER SyncThirdPartySkills
  原样转给 link-skills.ps1。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -Plan

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -Harness opencode

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -Harness all

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -ApplyRecommendedCli -ApplyRecommendedSkills -SkipThirdPartySkills

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -VerifyOnly
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [string]$Harness = 'agents',
  [switch]$Plan,
  [switch]$VerifyOnly,
  [switch]$Quiet,
  [switch]$SkipPlugins,
  [switch]$SkipGlobalAgents,
  [switch]$SkipDepCheck,
  [switch]$SkipSubmodules,
  [switch]$ApplyRecommendedCli,
  [switch]$SkipRecommendedCli,
  [switch]$ApplyRecommendedSkills,
  [switch]$SkipRecommendedSkills,
  [switch]$ApplyThirdPartySkills,
  [switch]$SkipThirdPartySkills,
  [switch]$SyncThirdPartySkills
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
  $base = $PSScriptRoot
  if ([string]::IsNullOrWhiteSpace($base)) { $base = Split-Path -Parent $MyInvocation.MyCommand.Path }
  $RepoRoot = (Resolve-Path (Join-Path $base '..')).Path
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step([string]$Message) { if (-not $Quiet) { Write-Host $Message } }

function Test-FileEqual([string]$Left, [string]$Right) {
  # 不用 Get-FileHash: 部分 5.1 环境的 PSModulePath 被其他版本污染, 自动加载会失败
  $a = [System.IO.File]::ReadAllBytes($Left)
  $b = [System.IO.File]::ReadAllBytes($Right)
  if ($a.Length -ne $b.Length) { return $false }
  for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }
  return $true
}

$script:Failures = 0
$script:Timings = @()
$total = [System.Diagnostics.Stopwatch]::StartNew()

function Invoke-Phase([string]$Name, [scriptblock]$Action) {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  & $Action
  $sw.Stop()
  $script:Timings += [pscustomobject]@{ Step = $Name; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
}

function Test-OpenCodePresent {
  # 只看命令或已有配置文件，不把链接脚本刚创建的 skills\ 目录当成 OpenCode 已安装。
  if (Get-Command opencode -ErrorAction SilentlyContinue) { return $true }
  $dir = Join-Path $env:USERPROFILE '.config\opencode'
  foreach ($name in @('AGENTS.md', 'opencode.json', 'auth.json', 'cli.json')) {
    if (Test-Path -LiteralPath (Join-Path $dir $name) -PathType Leaf) { return $true }
  }
  return $false
}

function Test-HarnessSelected([string]$Name) {
  # 本次 -Harness 是否包含指定 harness；all 覆盖全部。
  $items = @($Harness -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
  if ($items -contains 'all') { return $true }
  return $items -contains $Name
}

function Get-UninitializedSubmodules {
  # 返回未初始化子模块的相对路径；git 不可用或当前不是 git 工作区时返回空。
  $gitCommand = Get-Command git -ErrorAction SilentlyContinue
  if (-not $gitCommand) { return @() }
  $insideWorkTree = & git -C $RepoRoot rev-parse --is-inside-work-tree 2>$null
  if ($LASTEXITCODE -ne 0 -or $insideWorkTree -ne 'true') { return @() }
  $lines = @(& git -C $RepoRoot submodule status 2>$null)
  if ($LASTEXITCODE -ne 0) { return @() }
  $paths = foreach ($line in $lines) {
    if ($line -match '^-') {
      $parts = $line.Substring(1).Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
      if ($parts.Count -ge 2) { $parts[1].Replace('\', '/') }
    }
  }
  return @($paths)
}

function Sync-Submodules {
  # codex-model-config 是 git submodule；zip/部分包不含内容时只提示，不阻塞其他 skill。
  $uninitialized = @(Get-UninitializedSubmodules)
  if ($uninitialized.Count -eq 0) {
    $missingSkill = $false
    foreach ($dir in @(Get-ChildItem (Join-Path $RepoRoot 'skills') -Directory -ErrorAction SilentlyContinue)) {
      if (-not (Test-Path (Join-Path $dir.FullName 'SKILL.md') -PathType Leaf)) {
        $missingSkill = $true
        break
      }
    }
    if ($missingSkill -and (Test-Path -LiteralPath (Join-Path $RepoRoot '.gitmodules') -PathType Leaf)) {
      if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Warning '未找到 git，无法初始化子模块（codex-model-config 可能缺失）'
      } elseif (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) {
        Write-Warning '当前目录不是 git 工作区，无法初始化子模块（codex-model-config 可能缺失）；需要该 skill 时用 git clone --recurse-submodules 重新获取'
      }
    }
    return
  }
  $names = $uninitialized -join ' '
  if ($Plan) {
    Write-Step "计划初始化子模块（$($uninitialized.Count) 个）: $names"
    return
  }
  if ($VerifyOnly) {
    Write-Warning "子模块未初始化（$($uninitialized.Count) 个）: $names"
    Write-Host "  运行 scripts\deploy.ps1 或 git -C `"$RepoRoot`" submodule update --init --depth 1 修复；不阻塞其他 skill。"
    return
  }
  Write-Step "== 初始化子模块（$($uninitialized.Count) 个）: $names =="
  $previousPrompt = $env:GIT_TERMINAL_PROMPT
  $env:GIT_TERMINAL_PROMPT = '0'
  try {
    & git -C $RepoRoot submodule update --init --depth 1
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "子模块初始化失败，继续部署其他 skill；可稍后手动运行: git -C `"$RepoRoot`" submodule update --init --depth 1"
    } else {
      Write-Step '子模块已初始化'
    }
  } finally {
    if ($null -eq $previousPrompt) {
      Remove-Item Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
    } else {
      $env:GIT_TERMINAL_PROMPT = $previousPrompt
    }
  }
}

function Get-AgentsLinkTarget([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  if (-not $item -or [string]::IsNullOrEmpty($item.LinkType)) { return $null }
  $target = @($item.Target)[0]
  if ([string]::IsNullOrWhiteSpace($target)) { return $null }
  if (-not [System.IO.Path]::IsPathRooted($target)) {
    $target = Join-Path (Split-Path -Parent $Path) $target
  }
  return [System.IO.Path]::GetFullPath($target)
}

function Sync-ZCodeAgentsLink([string]$OpenCodeAgents) {
  # ZCode 只认 ~/.zcode/AGENTS.md；优先 symlink 到 OpenCode 副本，不另存副本。
  # 本机不允许创建符号链接（常见于 Windows 权限）时跳过，不计失败，也不落回副本。
  $zcodeDir = Join-Path $env:USERPROFILE '.zcode'
  $zcodeAgents = Join-Path $zcodeDir 'AGENTS.md'
  if (-not (Test-Path -LiteralPath $zcodeDir -PathType Container)) {
    Write-Step '全局 AGENTS.md(ZCode): 未检测到 ~/.zcode，跳过（未安装/未使用）'
    return
  }
  if (-not (Test-Path -LiteralPath $OpenCodeAgents -PathType Leaf)) {
    if ($Plan) {
      Write-Step '全局 AGENTS.md(ZCode) 计划在 OpenCode 副本就绪后建立 symlink（无权限时跳过）'
    } else {
      Write-Step '全局 AGENTS.md(ZCode): OpenCode 副本缺失，跳过'
    }
    return
  }
  $target = [System.IO.Path]::GetFullPath($OpenCodeAgents)
  $current = Get-AgentsLinkTarget $zcodeAgents
  if ($null -ne $current) {
    if ($current -ieq $target) {
      Write-Step "全局 AGENTS.md(ZCode) 已链接 -> $target"
    } else {
      Write-Warning "全局 AGENTS.md(ZCode) 已链接到其他目标（$current），保留不动"
    }
    return
  }
  if (Test-Path -LiteralPath $zcodeAgents -PathType Container) {
    Write-Warning '全局 AGENTS.md(ZCode) 路径是目录，跳过'
    return
  }
  $regular = Test-Path -LiteralPath $zcodeAgents -PathType Leaf
  if ($regular -and -not (Test-FileEqual $OpenCodeAgents $zcodeAgents)) {
    Write-Warning '全局 AGENTS.md(ZCode) 是普通文件且与 OpenCode 副本不同；保留本机文件，跳过 ZCode 同步（如需共享，手工合并后删除该文件）'
    return
  }
  if ($Plan) {
    if ($regular) { Write-Step "全局 AGENTS.md(ZCode) 计划替换为 symlink -> $target" }
    else { Write-Step "全局 AGENTS.md(ZCode) 计划建立 symlink -> $target（无权限时跳过）" }
    return
  }
  if ($VerifyOnly) {
    if ($regular) { Write-Step '全局 AGENTS.md(ZCode) 是普通文件（与 OpenCode 一致），部署时将替换为 symlink' }
    else { Write-Step '全局 AGENTS.md(ZCode) 未建立链接；部署时尝试，无符号链接权限则跳过' }
    return
  }
  $tmp = Join-Path $zcodeDir ("AGENTS.md.tmp-" + [guid]::NewGuid().ToString('N'))
  try {
    New-Item -ItemType SymbolicLink -Path $tmp -Target $target -ErrorAction Stop | Out-Null
    Move-Item -LiteralPath $tmp -Destination $zcodeAgents -Force -ErrorAction Stop
    Write-Host "全局 AGENTS.md(ZCode) 已建立 symlink -> $target"
  } catch {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    Write-Host '全局 AGENTS.md(ZCode) 未建立：本机符号链接不可用或创建失败，跳过 ZCode 全局规则同步（不落回副本）'
  }
}

function Sync-GlobalAgents {
  $src = Join-Path $RepoRoot 'config\global-AGENTS.md'
  if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
    Write-Warning '缺少 config/global-AGENTS.md，跳过全局 AGENTS.md 同步'
    $script:Failures++
    return
  }
  $opencodeAgents = Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md'
  $opencodeWasPresent = Test-OpenCodePresent
  if (Test-Path -LiteralPath $opencodeAgents -PathType Leaf) {
    if (Test-FileEqual $src $opencodeAgents) {
      Write-Step '全局 AGENTS.md(OpenCode) 已与真源一致'
    } else {
      $cmp = @(Compare-Object -ReferenceObject @(Get-Content -LiteralPath $src -Encoding UTF8) -DifferenceObject @(Get-Content -LiteralPath $opencodeAgents -Encoding UTF8))
      $truthOnly = @($cmp | Where-Object { $_.SideIndicator -eq '<=' }).Count
      $localOnly = @($cmp | Where-Object { $_.SideIndicator -eq '=>' }).Count
      Write-Warning "全局 AGENTS.md(OpenCode) 与真源不同（真源独有 $truthOnly 行，本机独有 $localOnly 行）；保留本机文件，按真源对齐通用条目，本机定制留在末尾「个性化规则补充」"
    }
  } elseif ($Plan) {
    if ($opencodeWasPresent) {
      Write-Step "全局 AGENTS.md(OpenCode) 计划复制 -> $opencodeAgents"
    } else {
      Write-Step "全局 AGENTS.md(OpenCode): 未检测到 OpenCode，计划预置副本 -> $opencodeAgents"
    }
  } elseif ($VerifyOnly) {
    if ($opencodeWasPresent) {
      Write-Warning "全局 AGENTS.md(OpenCode) 缺失: $opencodeAgents"
      $script:Failures++
    } else {
      Write-Step '全局 AGENTS.md(OpenCode): 未检测到 OpenCode，跳过（需要时运行 scripts\deploy.ps1 预置）'
    }
  } elseif ($PSCmdlet.ShouldProcess($opencodeAgents, '复制全局 AGENTS.md')) {
    New-Item -ItemType Directory -Force -Path (Split-Path $opencodeAgents) | Out-Null
    Copy-Item -LiteralPath $src -Destination $opencodeAgents
    if ($opencodeWasPresent) {
      Write-Host "全局 AGENTS.md(OpenCode) 已恢复 -> $opencodeAgents"
    } else {
      Write-Host "全局 AGENTS.md(OpenCode) 已预置（未检测到 OpenCode） -> $opencodeAgents"
    }
  }
  Sync-ZCodeAgentsLink $opencodeAgents
}

function Invoke-DepCheck {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) {
    Write-Warning '未找到 Python，跳过依赖套餐检查'
    return
  }
  Write-Step '== 依赖套餐检查（standard，推荐项，不阻断）=='
  & python -X utf8 (Join-Path $RepoRoot 'scripts\check-skill-deps.py') --profile standard
  if (-not $?) { Write-Warning '依赖套餐检查有缺失项（推荐项，不阻断部署）' }
}

# 0. git submodule（未初始化时自动拉取；失败只警告）
if (-not $SkipSubmodules) {
  Invoke-Phase '子模块' { Sync-Submodules }
}

# 1. skill 链接
Invoke-Phase 'skill 链接' {
  $skillArgs = @{ Harness = $Harness }
  if ($Plan) { $skillArgs['Plan'] = $true }
  if ($VerifyOnly) { $skillArgs['VerifyOnly'] = $true }
  if ($Quiet) { $skillArgs['Quiet'] = $true }
  if ($ApplyRecommendedCli) { $skillArgs['ApplyRecommendedCli'] = $true }
  if ($SkipRecommendedCli) { $skillArgs['SkipRecommendedCli'] = $true }
  if ($ApplyRecommendedSkills) { $skillArgs['ApplyRecommendedSkills'] = $true }
  if ($SkipRecommendedSkills) { $skillArgs['SkipRecommendedSkills'] = $true }
  if ($ApplyThirdPartySkills) { $skillArgs['ApplyThirdPartySkills'] = $true }
  if ($SkipThirdPartySkills) { $skillArgs['SkipThirdPartySkills'] = $true }
  if ($SyncThirdPartySkills) { $skillArgs['SyncThirdPartySkills'] = $true }
  & (Join-Path $RepoRoot 'scripts\link-skills.ps1') @skillArgs
  if (-not $?) { $script:Failures++ }
}

# 2. OpenCode 插件链接
if (-not $SkipPlugins) {
  if (-not (Test-HarnessSelected 'opencode')) {
    Write-Step "跳过 OpenCode 插件：本次 -Harness $Harness 未选择 opencode（需要时加 -Harness opencode 或 all）"
  } else {
    Invoke-Phase '插件链接' {
      $pluginArgs = @{}
      if ($VerifyOnly) { $pluginArgs['VerifyOnly'] = $true }
      if ($Quiet) { $pluginArgs['Quiet'] = $true }
      if ($Plan) { $pluginArgs['WhatIf'] = $true }
      & (Join-Path $RepoRoot 'scripts\link-plugins.ps1') @pluginArgs
      if (-not $?) { $script:Failures++ }
    }
  }
}

# 3. 全局 AGENTS.md
if (-not $SkipGlobalAgents) {
  if (-not (Test-HarnessSelected 'opencode')) {
    Write-Step "跳过全局 AGENTS.md：本次 -Harness $Harness 未选择 opencode（需要时加 -Harness opencode 或 all）"
  } else {
    Invoke-Phase '全局 AGENTS.md' { Sync-GlobalAgents }
  }
}

# 4. 依赖套餐检查（只提示，不阻断）
if (-not $SkipDepCheck) {
  Invoke-Phase '依赖套餐检查' { Invoke-DepCheck }
}

$total.Stop()

Write-Host ''
Write-Host '== 部署效率复盘 =='
Write-Host ('总耗时: {0:N1}s' -f $total.Elapsed.TotalSeconds)
foreach ($t in $script:Timings) {
  Write-Host ('  {0}: {1:N1}s' -f $t.Step, $t.Seconds)
}
if ($script:Failures -gt 0) {
  Write-Host "失败/异常: $($script:Failures) 项（见上方警告）"
} else {
  Write-Host '失败/异常: 无'
}
Write-Host '可选反馈: 若某步明显变慢、需要二次补命令或输出难读，可把本段耗时与步骤反馈给仓库维护者，用于优化部署指南。'

if ($script:Failures -gt 0) { exit 1 }
