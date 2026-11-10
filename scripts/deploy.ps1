#Requires -Version 5.1
<#
.SYNOPSIS
  一键部署：skill 链接、OpenCode 插件链接、全局 AGENTS.md 恢复与校验。

.DESCRIPTION
  串联 link-skills.ps1、link-plugins.ps1 与全局 AGENTS.md 同步，避免三步分开执行时漏步。
  AGENTS.md 只在目标缺失时复制；内容不一致只警告，不覆盖本机文件。
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

function Sync-GlobalAgents {
  $src = Join-Path $RepoRoot 'config\global-AGENTS.md'
  if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
    Write-Warning '缺少 config/global-AGENTS.md，跳过全局 AGENTS.md 同步'
    $script:Failures++
    return
  }
  $targets = @(
    @{ Name = 'OpenCode'; Path = (Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md') },
    @{ Name = 'ZCode'; Path = (Join-Path $env:USERPROFILE '.zcode\AGENTS.md') }
  )
  foreach ($t in $targets) {
    $dst = $t.Path
    if (Test-Path -LiteralPath $dst -PathType Leaf) {
      if (Test-FileEqual $src $dst) {
        Write-Step "全局 AGENTS.md($($t.Name)) 已与真源一致"
      } else {
        Write-Warning "全局 AGENTS.md($($t.Name)) 与本机不同；保留本机文件，请对比后合并通用条目（本机定制保留，不覆盖）"
      }
      continue
    }
    if ($Plan) {
      Write-Step "全局 AGENTS.md($($t.Name)) 计划复制 -> $dst"
      continue
    }
    if ($VerifyOnly) {
      Write-Warning "全局 AGENTS.md($($t.Name)) 缺失: $dst"
      $script:Failures++
      continue
    }
    if ($PSCmdlet.ShouldProcess($dst, '复制全局 AGENTS.md')) {
      New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
      Copy-Item -LiteralPath $src -Destination $dst
      Write-Host "全局 AGENTS.md($($t.Name)) 已恢复 -> $dst"
    }
  }
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
