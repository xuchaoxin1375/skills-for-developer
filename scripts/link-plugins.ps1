#Requires -Version 5.1
<#
.SYNOPSIS
  [Windows 专用] 将本仓库 plugins/ 下的每个插件包通过 Junction 链接到 OpenCode 的 plugins 目录。
  Linux/macOS 请用 scripts/link-plugins.sh（symlink）。

.DESCRIPTION
  唯一真源: <repo>/plugins/<name>/ (内含 package.json)。
  Harness 侧只放 Junction, 不存实体:
    - OpenCode: $env:USERPROFILE\.config\opencode\plugins

  OpenCode 会自动发现该目录下的插件包（与 .opencode/plugins/ 同一套布局），
  因此本脚本不改 opencode.json，也不动该目录里其他来源的插件。

  幂等, 可反复执行。只管理仓库中存在的插件名, 并顺手清理指向本仓库
  但目标已不存在的悬空链接 (重命名/删除插件的残留)。

.PARAMETER RepoRoot
  仓库根目录, 默认自动推导为脚本所在目录的上级。

.PARAMETER Include
  只处理指定的插件名 (默认处理 plugins/ 下全部含 package.json 的目录)。

.PARAMETER Unlink
  移除本仓库创建的 Junction (仅移除指向本仓库的链接, 实体目录不动)。

.PARAMETER VerifyOnly
  只检查链接状态, 不做任何修改; 悬空链接 (目标已不存在) 也计为异常。
  有异常时以非零退出码返回。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -VerifyOnly
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [string[]]$Include,
  [switch]$Unlink,
  [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'

# 默认 UTF-8：5.1 控制台默认 GBK，直接输出中文会被采集侧按 UTF-8 解错。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
  $base = $PSScriptRoot
  if ([string]::IsNullOrWhiteSpace($base)) { $base = Split-Path -Parent $MyInvocation.MyCommand.Path }
  $RepoRoot = (Resolve-Path (Join-Path $base '..')).Path
}

$pluginsDir = Join-Path $RepoRoot 'plugins'
if (-not (Test-Path $pluginsDir -PathType Container)) {
  Write-Error "plugins 目录不存在: $pluginsDir"
  exit 1
}

$targetDir = Join-Path $env:USERPROFILE '.config\opencode\plugins'

$plugins = Get-ChildItem -Path $pluginsDir -Directory | Where-Object {
  Test-Path (Join-Path $_.FullName 'package.json') -PathType Leaf
}
if ($Include -and $Include.Count -gt 0) {
  $plugins = $plugins | Where-Object { $Include -contains $_.Name }
}
if (-not $plugins -or $plugins.Count -eq 0) {
  Write-Error '没有可处理的插件 (plugins/ 下需要有含 package.json 的子目录)。'
  exit 1
}

foreach ($p in (Get-ChildItem -Path $pluginsDir -Directory)) {
  if (-not (Test-Path (Join-Path $p.FullName 'package.json') -PathType Leaf)) {
    Write-Warning "跳过 $($p.Name): 缺少 package.json"
  }
}

function Get-LinkTarget([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  if ($null -eq $item) { return $null }
  # Junction / Symlink 都会带 LinkType; 普通目录则 LinkType 为空
  if ([string]::IsNullOrEmpty($item.LinkType)) { return $null }
  return $item.Target
}

function Remove-StalePluginLinks {
  # 清理指向本仓库 plugins\ 但目标已不存在的 Junction/Symlink
  # (重命名/删除插件的残留)。VerifyOnly 下只报告并计为异常。
  if (-not (Test-Path -LiteralPath $targetDir -PathType Container)) { return }
  $pluginsRoot = (Resolve-Path -LiteralPath $pluginsDir).Path.TrimEnd('\')
  foreach ($entry in (Get-ChildItem -LiteralPath $targetDir -Force -ErrorAction SilentlyContinue)) {
    $targets = Get-LinkTarget $entry.FullName
    if ($null -eq $targets) { continue }
    $owned = $false
    $alive = $false
    foreach ($t in @($targets)) {
      if ([string]::IsNullOrWhiteSpace($t)) { continue }
      $clean = $t.TrimEnd('\')
      if (-not [System.IO.Path]::IsPathRooted($clean)) {
        $clean = [System.IO.Path]::GetFullPath((Join-Path $targetDir $clean))
      }
      if ($clean -ieq $pluginsRoot -or $clean.StartsWith($pluginsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
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
      Write-Host "  [$($entry.Name)] 悬空链接已清理 (目标不存在)"
    }
  }
}

$failures = 0

Write-Host "== $targetDir =="
if (-not (Test-Path $targetDir -PathType Container)) {
  if ($VerifyOnly) {
    Write-Warning "  缺失目录 (VerifyOnly, 不创建): $targetDir"
    $failures++
  } elseif ($PSCmdlet.ShouldProcess($targetDir, '创建 opencode plugins 目录')) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Write-Host '  创建目录'
  }
}

foreach ($plugin in $plugins) {
  $link = Join-Path $targetDir $plugin.Name
  $dest = $plugin.FullName
  $label = "  [$($plugin.Name)]"

  if ($Unlink) {
    $cur = Get-LinkTarget $link
    if ($null -eq $cur) {
      Write-Host "$label 无链接, 跳过"
      continue
    }
    if ($cur -contains $dest -or $cur -eq $dest) {
      if ($VerifyOnly) {
        Write-Host "$label 将被移除 (VerifyOnly)"
        continue
      }
      if ($PSCmdlet.ShouldProcess($link, "移除 Junction -> $dest")) {
        Remove-Item -LiteralPath $link -Force
        Write-Host "$label 已移除"
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
      Write-Host "$label 已创建 -> $dest"
    }
    continue
  }

  $cur = Get-LinkTarget $link
  if ($null -ne $cur -and ($cur -eq $dest -or $cur -contains $dest)) {
    Write-Host "$label OK"
    if (-not (Test-Path (Join-Path $link 'package.json') -PathType Leaf)) {
      Write-Warning "$label 链接存在但 package.json 不可读"
      $failures++
    }
    continue
  }

  if ($null -ne $cur) {
    if ($VerifyOnly) {
      Write-Warning "$label 指向错误: $cur (期望 $dest)"
      $failures++
      continue
    }
    if ($PSCmdlet.ShouldProcess($link, "纠正链接 $cur -> $dest")) {
      Remove-Item -LiteralPath $link -Force
      New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
      Write-Host "$label 已纠正 -> $dest"
    }
    continue
  }

  # 走到这里: link 路径上是实体目录/文件, 备份到 plugins 目录之外再替换为 Junction
  if ($VerifyOnly) {
    Write-Warning "$label 是实体目录/文件, 需备份后替换为 Junction"
    $failures++
    continue
  }
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $backup = Join-Path (Join-Path (Join-Path (Join-Path $env:USERPROFILE '.skills-migration-backup') $stamp) 'opencode-plugins') $plugin.Name
  if ($PSCmdlet.ShouldProcess($link, "备份实体到 $backup 并创建 Junction -> $dest")) {
    New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    Move-Item -LiteralPath $link -Destination $backup -Force
    New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
    Write-Host "$label 实体已备份到 $backup, 链接已创建"
  }
}

Remove-StalePluginLinks

if ($VerifyOnly) {
  if ($failures -gt 0) {
    Write-Warning "校验发现 $failures 处异常, 见上。"
    exit 1
  }
  Write-Host '全部插件链接正常。'
}
