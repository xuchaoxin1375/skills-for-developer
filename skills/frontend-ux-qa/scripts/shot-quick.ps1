#Requires -Version 7
<#
.SYNOPSIS
  外部单页轻量截图：一发式 headless chrome，只拍首屏视口，不启常驻浏览器会话。
.DESCRIPTION
  适用：纯信息类首屏速看（取数、确认页面可达）。不适用：需滚动第二屏、注入冻结、
  验收证据链——那些走脚本化浏览器会话（见调用方 skill）。
  调用方按 network-access 规则定代理（有可用登记直接传 -Proxy，无则直连熔断），
  按 visual-acceptance 决定取景与是否免拍；本脚本只管一次拍好并自证。
.PARAMETER Url
  必填，http(s) 地址。
.PARAMETER Out
  输出 PNG 路径。缺省落系统临时目录 opencode/shot-quick/ 下按 URL 别名命名。
.PARAMETER Width
  视口宽，只认 390/1440（验收常用两档），默认 1440。
.PARAMETER Height
  视口高，默认 900。
.PARAMETER Proxy
  可选，如 'http://127.0.0.1:<port>'（真实值由本机登记给出）；不传即直连。只接受本次调用参数，不读机器配置。
.PARAMETER Chrome
  chrome 可执行文件。缺省按 显式参数 → $env:CHROME_PATH / $env:HTMLMINI_CHROME_BIN →
  PATH → 固定安装路径 → Playwright 缓存（版本最大者，完整版优先）解析，
  找不到即抛错（由调用方给定，不在本文件写死本机路径）。
  命中注入额外参数的包装器/垫片时自动取真实目标并告警。
.EXAMPLE
  .\shot-quick.ps1 -Url 'https://example.com/page' -Proxy 'http://127.0.0.1:<port>'
  成功时打印 SHOT 行（含字节数）并以 exit 0 结束；失败 exit 1 且不留 profile。
.NOTES
  pwsh 7 下运行；profile 目录必须预建（chrome 不会自动建短路径 profile，
  否则静默失败无截图）。图形界面浏览器须用 Start-Process -Wait 取进程退出码，
  不单独依赖 $LASTEXITCODE。退出前删自建 profile，并核对 chrome 进程数回到基线。
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Url,
  [string]$Out = '',
  [ValidateSet(390, 1440)][int]$Width = 1440,
  [int]$Height = 900,
  [string]$Proxy = '',
  [string]$Chrome = '',
  [int]$VirtualBudget = 15000
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

if ($Url -notmatch '^https?://') { throw "Url 须为 http(s) 地址：$Url" }

function Test-WrapperShim {
  param([string]$Path)
  if (-not $Path) { return $null }
  $sibling = [System.IO.Path]::ChangeExtension($Path, '.shim')
  $isShimDir = $Path -match '(?i)[\\/]shims?[\\/]'
  if (-not (Test-Path -LiteralPath $sibling) -and -not $isShimDir) { return $null }
  if (Test-Path -LiteralPath $sibling) {
    $line = Get-Content -LiteralPath $sibling -Encoding UTF8 -ErrorAction SilentlyContinue |
      Where-Object { $_ -match '^\s*path\s*=' } | Select-Object -First 1
    if ($line -and ($line -match '"([^"]+)"')) {
      $target = $Matches[1]
      if (Test-Path -LiteralPath $target) { return $target }
    }
  }
  return $null
}

function Get-PlaywrightChromium {
  param([string]$Root)
  if (-not $Root -or -not (Test-Path -LiteralPath $Root)) { return $null }
  $dirs = Get-ChildItem -LiteralPath $Root -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^chromium-(\d+)$' } |
    Sort-Object { if ($_.Name -match '^chromium-(\d+)$') { [int]$Matches[1] } else { 0 } } -Descending
  foreach ($d in $dirs) {
    $full = Join-Path $d.FullName 'chrome-win64/chrome.exe'
    if (Test-Path -LiteralPath $full) { return $full }
    $full = Join-Path $d.FullName 'chrome-win/chrome.exe'
    if (Test-Path -LiteralPath $full) { return $full }
    $full = Join-Path $d.FullName 'chrome-linux/chrome'
    if (Test-Path -LiteralPath $full) { return $full }
  }
  foreach ($d in $dirs) {
    $shell = Join-Path $d.FullName 'chrome-headless-shell-win64/chrome-headless-shell.exe'
    if (Test-Path -LiteralPath $shell) { return $shell }
  }
  return $null
}

function Resolve-BrowserBinary {
  param([string]$Explicit)
  if ($Explicit) {
    $real = Test-WrapperShim -Path $Explicit
    if ($real) { Write-Warning "显式浏览器为包装器，已改用真实目标：$real"; return @{ Path = $real; Source = 'explicit-real' } }
    if (-not (Test-Path -LiteralPath $Explicit)) { throw "指定的 chrome 不存在：$Explicit" }
    return @{ Path = $Explicit; Source = 'explicit' }
  }
  foreach ($key in @('CHROME_PATH', 'HTMLMINI_CHROME_BIN')) {
    $p = [System.Environment]::GetEnvironmentVariable($key)
    if ($p) {
      $real = Test-WrapperShim -Path $p
      if ($real) { Write-Warning "环境变量 $key 指向包装器，已改用真实目标：$real"; return @{ Path = $real; Source = 'env-real' } }
      if (Test-Path -LiteralPath $p) { return @{ Path = $p; Source = 'env' } }
      throw "环境变量 $key 指向不存在的路径：$p"
    }
  }
  $found = Get-Command chrome, google-chrome, chromium -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) {
    $real = Test-WrapperShim -Path $found.Source
    if ($real) { Write-Warning "PATH 命中包装器，已改用真实目标：$real"; return @{ Path = $real; Source = 'path-real' } }
    if ($found.Source -match '(?i)[\\/]shims?[\\/]') {
      Write-Warning "PATH 命中包装器且无法解析真实目标，跳过并继续固定路径/Playwright 查找：$($found.Source)"
    } else {
      return @{ Path = $found.Source; Source = 'path' }
    }
  }
  $fixed = @()
  foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
    if ($root) { $fixed += (Join-Path $root 'Google/Chrome/Application/chrome.exe') }
  }
  $fixed += @('/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
  foreach ($p in $fixed) {
    if ($p -and (Test-Path -LiteralPath $p)) { return @{ Path = $p; Source = 'fixed' } }
  }
  $pwRoot = $env:PLAYWRIGHT_BROWSERS_PATH
  if (-not $pwRoot) {
    if ($env:LOCALAPPDATA) { $pwRoot = Join-Path $env:LOCALAPPDATA 'ms-playwright' }
    elseif ($env:HOME) { $pwRoot = Join-Path $env:HOME '.cache/ms-playwright' }
  }
  $pw = Get-PlaywrightChromium -Root $pwRoot
  if ($pw) { return @{ Path = $pw; Source = 'playwright' } }
  throw '找不到 chrome：请传 -Chrome 或设 $env:CHROME_PATH / $env:HTMLMINI_CHROME_BIN，或安装 Playwright Chromium 缓存'
}

$browser = Resolve-BrowserBinary -Explicit $Chrome
$Chrome = $browser.Path
Write-Host "BROWSER source=$($browser.Source) bin=$Chrome"

$slug = (($Url -replace '^https?://', '') -replace '[^a-z0-9]+', '-').Trim('-').ToLower()
if (-not $slug) { $slug = 'page' }
if ($slug.Length -gt 60) { $slug = $slug.Substring(0, 60) }
if (-not $Out) {
  $Out = Join-Path ([System.IO.Path]::GetTempPath()) "opencode/shot-quick/$slug-s1-$Width.png"
}
$prof = Join-Path ([System.IO.Path]::GetTempPath()) "opencode/shot-quick-prof-$([System.Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $prof | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null
Remove-Item -LiteralPath $Out -ErrorAction SilentlyContinue

$before = @(Get-Process chrome -ErrorAction SilentlyContinue).Count
$chromeArgs = @(
  '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
  "--window-size=$Width,$Height",
  "--virtual-time-budget=$VirtualBudget",
  "--user-data-dir=$prof",
  "--screenshot=$Out",
  $Url
)
if ($Proxy) { $chromeArgs = @("--proxy-server=$Proxy") + $chromeArgs }

try {
  $proc = Start-Process -FilePath $Chrome -ArgumentList $chromeArgs -Wait -PassThru -NoNewWindow
  if ($proc.ExitCode -ne 0) { throw "chrome exit=$($proc.ExitCode)" }
  $file = Get-Item -LiteralPath $Out -ErrorAction Stop
  Write-Host ("SHOT $Out (" + [math]::Round($file.Length / 1KB) + 'KB)')
}
finally {
  Remove-Item -LiteralPath $prof -Recurse -Force -ErrorAction SilentlyContinue
}
$after = @(Get-Process chrome -ErrorAction SilentlyContinue).Count
if ($after -gt $before) { Write-Warning "chrome 进程数未回基线：before=$before after=$after" }
