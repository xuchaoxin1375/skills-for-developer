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

  幂等, 可反复执行。只管理仓库中存在的 skill 名,
  不会动 harness 自带内容 (如 Codex 的 .system/、AGENTS.md)。

.PARAMETER RepoRoot
  仓库根目录, 默认自动推导为脚本所在目录的上级。

.PARAMETER Include
  只处理指定的 skill 名 (默认处理 skills/ 下全部含 SKILL.md 的目录)。

.PARAMETER Unlink
  移除本仓库创建的 Junction (仅移除指向本仓库的链接, 实体目录不动)。

.PARAMETER VerifyOnly
  只检查链接状态与全局 AGENTS.md 是否漂移, 不做任何修改,
  有异常时以非零退出码返回 (AGENTS 缺失计异常, 内容不一致只警告)。

.PARAMETER ApplyRecommendedCli
  直接应用仓库推荐的 opencode cli.json (config/opencode/cli.json),
  不询问。原文件先备份为同目录 cli.json.bak-<时间戳>。

.PARAMETER SkipRecommendedCli
  跳过推荐 cli.json 的询问与应用。

.PARAMETER ApplyRecommendedSkills
  直接安装推荐 skill (config/recommended-skills.txt) 的依赖，不询问。

.PARAMETER SkipRecommendedSkills
  跳过推荐 skill 的依赖与命令安装（含 VerifyOnly 中的对应检查)。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -ApplyRecommendedCli

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -VerifyOnly
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\link-skills.ps1 -Include doc-rewrite-review,htmlmini
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$RepoRoot = '',
  [string[]]$Include,
  [switch]$Unlink,
  [switch]$VerifyOnly,
  [switch]$ApplyRecommendedCli,
  [switch]$SkipRecommendedCli,
  [switch]$ApplyRecommendedSkills,
  [switch]$SkipRecommendedSkills
)

$ErrorActionPreference = 'Stop'

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
    elseif ($targetDir -match '\.agents') { $harness = 'agents' }
    elseif ($targetDir -match '\.dsh') { $harness = 'dsh' }
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

if (-not $Unlink -and -not $VerifyOnly) {
  # 推荐 cli.json: 缺失或与真源不一致时, 交互终端下询问是否应用;
  # 非交互环境默认跳过 (用 -ApplyRecommendedCli 显式应用)。
  $repoCli = Join-Path (Join-Path (Join-Path $RepoRoot 'config') 'opencode') 'cli.json'
  if (Test-Path -LiteralPath $repoCli -PathType Leaf) {
    $dstDir = Join-Path $env:USERPROFILE '.config\opencode'
    $dstCli = Join-Path $dstDir 'cli.json'
    $inSync = (Test-Path -LiteralPath $dstCli -PathType Leaf) -and `
      ((Get-FileHash -LiteralPath $repoCli).Hash -eq (Get-FileHash -LiteralPath $dstCli).Hash)
    if ($inSync) {
      Write-Host '推荐 cli.json 已是最新。'
    } elseif ($SkipRecommendedCli) {
      Write-Host '已跳过推荐 cli.json (-SkipRecommendedCli)。'
    } else {
      $doApply = $false
      if ($ApplyRecommendedCli) {
        $doApply = $true
      } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $ans = Read-Host '是否应用仓库推荐的 opencode cli.json (覆盖当前配置, 原文件先备份)? [y/N]'
        $doApply = $ans -match '^(y|Y|yes|YES)$'
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

  # 推荐 skill（需依赖/命令）：依赖走询问/显式开关，命令默认安装
  $recSkills = @(Get-RecommendedSkills)
  if ($recSkills.Count -gt 0) {
    if ($SkipRecommendedSkills) {
      Write-Host "已跳过推荐 skill 部署（-SkipRecommendedSkills）：$($recSkills -join ', ')"
    } else {
      Write-Host "== 推荐 skill（需依赖/命令）：$($recSkills -join ', ') =="
      $doDeps = $false
      if ($ApplyRecommendedSkills) {
        $doDeps = $true
      } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $ans = Read-Host '是否安装推荐 skill 的依赖（如 htmlmini 的 pnpm install）？[Y/n]'
        $doDeps = $ans -match '^([yY]([eE][sS])?)?$'
      } else {
        Write-Host '非交互环境，跳过依赖安装（用 -ApplyRecommendedSkills 执行）；命令仍默认安装。'
      }
      foreach ($s in $recSkills) {
        if ($doDeps) {
          if (-not (Install-RecommendedSkillDeps $s)) {
            Write-Warning "  [$s] 依赖安装未完成，命令照常安装"
          }
        }
        Install-SkillCommand $s
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
}

if ($VerifyOnly) {
  $repoAgents = Join-Path (Join-Path $RepoRoot 'config') 'global-AGENTS.md'
  $liveAgents = Join-Path $env:USERPROFILE '.config\opencode\AGENTS.md'
  if (Test-Path -LiteralPath $repoAgents -PathType Leaf) {
    if (-not (Test-Path -LiteralPath $liveAgents -PathType Leaf)) {
      Write-Warning '全局 AGENTS.md 缺失 (期望按 README 从 config/global-AGENTS.md 恢复)'
      $failures++
    } elseif ((Get-FileHash -LiteralPath $repoAgents).Hash -ne (Get-FileHash -LiteralPath $liveAgents).Hash) {
      Write-Warning '全局 AGENTS.md 与真源不一致, 按 README 手工合并 (不自动覆盖)'
    } else {
      Write-Host '全局 AGENTS.md 与真源一致。'
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
        $onPath = $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
        if ($isOurs -and $onPath) {
          Write-Host "推荐 skill [$s] 命令 OK：$cmd"
        } else {
          Write-Warning "推荐 skill [$s] 命令缺失（期望 $shim 可用，重跑链接脚本安装）"
          $failures++
        }
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
