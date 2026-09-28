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

  幂等, 可反复执行。只管理仓库中存在的 skill 名,
  不会动 harness 自带内容 (如 Codex 的 .system/、AGENTS.md)。

.PARAMETER RepoRoot
  仓库根目录, 默认自动推导为脚本所在目录的上级。

.PARAMETER Include
  只处理指定的 skill 名 (默认处理 skills/ 下全部含 SKILL.md 的目录)。

.PARAMETER Unlink
  移除本仓库创建的 Junction (仅移除指向本仓库的链接, 实体目录不动)。

.PARAMETER VerifyOnly
  只检查链接状态, 不做任何修改, 有异常时以非零退出码返回。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Include doc-polish,htmlmini
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [string[]]$Include,
  [switch]$Unlink,
  [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'

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

$targets = @(
  (Join-Path $env:USERPROFILE '.config\opencode\skills'),
  (Join-Path $env:USERPROFILE '.codex\skills'),
  (Join-Path $env:USERPROFILE '.claude\skills')
)

$skills = Get-ChildItem -Path $skillsDir -Directory | Where-Object {
  Test-Path (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
}
if ($Include -and $Include.Count -gt 0) {
  $skills = $skills | Where-Object { $Include -contains $_.Name }
}
if (-not $skills -or $skills.Count -eq 0) {
  Write-Error '没有可处理的 skill (skills/ 下需要有含 SKILL.md 的子目录)。'
  exit 1
}

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

$failures = 0

foreach ($targetDir in $targets) {
  Write-Host "== $targetDir =="
  if (-not (Test-Path $targetDir -PathType Container)) {
    if ($VerifyOnly) {
      Write-Warning "  缺失目录 (VerifyOnly, 不创建): $targetDir"
      $failures++
      continue
    }
    if ($PSCmdlet.ShouldProcess($targetDir, '创建 harness skills 目录')) {
      New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
      Write-Host '  创建目录'
    }
  }

  foreach ($skill in $skills) {
    $link = Join-Path $targetDir $skill.Name
    $dest = $skill.FullName
    $label = "  [$($skill.Name)]"

    if ($Unlink) {
      $cur = Get-LinkTarget $link
      if ($null -eq $cur) {
        Write-Host "$label 无链接, 跳过"
        continue
      }
      # 只有指向本仓库的才删, 防止误删用户手工链到别处的内容
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
        Write-Host "$label 已纠正 -> $dest"
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
    $backup = Join-Path (Join-Path (Join-Path (Join-Path $env:USERPROFILE '.skills-migration-backup') $stamp) $harness) $skill.Name
    if ($PSCmdlet.ShouldProcess($link, "备份实体到 $backup 并创建 Junction -> $dest")) {
      New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
      Move-Item -LiteralPath $link -Destination $backup -Force
      New-Item -ItemType Junction -Path $link -Target $dest | Out-Null
      Write-Host "$label 实体已备份到 $backup, 链接已创建"
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
