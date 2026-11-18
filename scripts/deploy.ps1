#Requires -Version 5.1
<#
.SYNOPSIS
  一键部署：skill 链接、OpenCode 插件链接、全局 AGENTS.md 恢复与校验。

.DESCRIPTION
  串联 link-skills.ps1、link-plugins.ps1 与全局 AGENTS.md 同步，避免三步分开执行时漏步。
  OpenCode 的 AGENTS.md 缺失时复制，内容不一致只警告；ZCode 仅在 ~/.zcode 存在时尝试
  symlink 到 OpenCode 副本，无符号链接权限时跳过（不复制、不计失败）。
  结束时打印各阶段耗时与效率复盘提示，便于发现部署流程劣化。

.PARAMETER RepoRoot
  仓库根目录，默认自动推导为脚本所在目录的上级。

.PARAMETER Plan
  只预览，不修改任何文件。

.PARAMETER VerifyOnly
  只校验链接、插件运行态与 AGENTS.md 状态，不修改。

.PARAMETER Quiet
  隐藏逐项成功/进度行，保留警告、失败与汇总。

.PARAMETER SkipPlugins
  跳过 OpenCode 插件链接。

.PARAMETER SkipGlobalAgents
  跳过全局 AGENTS.md 恢复/校验。

.PARAMETER SkipDepCheck
  跳过依赖套餐检查。

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
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -ApplyRecommendedCli -ApplyRecommendedSkills -SkipThirdPartySkills

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1 -VerifyOnly
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [switch]$Plan,
  [switch]$VerifyOnly,
  [switch]$Quiet,
  [switch]$SkipPlugins,
  [switch]$SkipGlobalAgents,
  [switch]$SkipDepCheck,
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
    Write-Step "全局 AGENTS.md(OpenCode) 计划复制 -> $opencodeAgents"
  } elseif ($VerifyOnly) {
    Write-Warning "全局 AGENTS.md(OpenCode) 缺失: $opencodeAgents"
    $script:Failures++
  } elseif ($PSCmdlet.ShouldProcess($opencodeAgents, '复制全局 AGENTS.md')) {
    New-Item -ItemType Directory -Force -Path (Split-Path $opencodeAgents) | Out-Null
    Copy-Item -LiteralPath $src -Destination $opencodeAgents
    Write-Host "全局 AGENTS.md(OpenCode) 已恢复 -> $opencodeAgents"
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

# 1. skill 链接
Invoke-Phase 'skill 链接' {
  $skillArgs = @{}
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
  Invoke-Phase '插件链接' {
    $pluginArgs = @{}
    if ($VerifyOnly) { $pluginArgs['VerifyOnly'] = $true }
    if ($Quiet) { $pluginArgs['Quiet'] = $true }
    if ($Plan) { $pluginArgs['WhatIf'] = $true }
    & (Join-Path $RepoRoot 'scripts\link-plugins.ps1') @pluginArgs
    if (-not $?) { $script:Failures++ }
  }
}

# 3. 全局 AGENTS.md
if (-not $SkipGlobalAgents) {
  Invoke-Phase '全局 AGENTS.md' { Sync-GlobalAgents }
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
