#Requires -Version 7
<#
.SYNOPSIS
  首屏截图兼容入口；委托 shot_scroll.py 托管浏览器，不直接创建 Chrome 进程。
.DESCRIPTION
  需要目标 Python 环境已有 Playwright。默认使用匹配缓存；本机 Edge/Chrome 可传
  -Channel，或 -DiscoverBrowser 查常用位置，免下载浏览器。-ListBrowsers 只读列候选。
  -Engine oneshot/cdp 改用轻量引擎（不导入 Playwright，须显式指定浏览器）；
  -ToBottom 逐屏滚到底只截末屏视口（仅默认引擎）；
  -Doctor 只读体检引擎与选中的浏览器，加 -ProbeLaunch 才实际探一次启动。
  总期限与回收由独立 guardian 负责；失败不自动重试。
.EXAMPLE
  ./shot-quick.ps1 -Url 'https://example.com' -Channel msedge -Out page.png
.EXAMPLE
  ./shot-quick.ps1 -Doctor -ProbeLaunch
.NOTES
  -VirtualBudget 已移除，改用 -TimeoutMs（操作）和 -WallTimeoutMs（整个任务）。
  退出码与 shot_scroll.py 一致；-Python 可指定虚拟环境解释器。
#>
[CmdletBinding()]
param(
  [string]$Url = '',
  [string]$Out = '',
  [ValidateRange(1, 8192)][int]$Width = 1440,
  [ValidateRange(1, 8192)][int]$Height = 900,
  [string]$Proxy = '',
  [string]$Chrome = '',
  [ValidateSet('chrome', 'msedge')][string]$Channel,
  [switch]$DiscoverBrowser,
  [switch]$ListBrowsers,
  [ValidateSet('playwright', 'oneshot', 'cdp')][string]$Engine = 'playwright',
  [switch]$ToBottom,
  [switch]$Doctor,
  [switch]$ProbeLaunch,
  [string]$Python = 'python',
  [ValidateRange(1, [int]::MaxValue)][int]$TimeoutMs = 30000,
  [ValidateRange(1, [int]::MaxValue)][int]$WallTimeoutMs = 60000
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
if (@(@($Chrome, $Channel, $DiscoverBrowser.IsPresent) | Where-Object { $_ }).Count -gt 1) {
  throw '-Chrome、-Channel、-DiscoverBrowser 不能同时指定'
}
if ($ListBrowsers) {
  if ($Url -or $Chrome -or $Channel -or $DiscoverBrowser) { throw '-ListBrowsers 单独使用' }
  & $Python -X utf8 (Join-Path $PSScriptRoot 'shot_scroll.py') --list-browsers
  exit $LASTEXITCODE
}
if ($ProbeLaunch -and -not $Doctor) { throw '-ProbeLaunch 需要与 -Doctor 一起使用' }
if ($Doctor) {
  if ($Url -or $Out -or $Channel -or $DiscoverBrowser -or $ListBrowsers) {
    throw '-Doctor 只与 -ProbeLaunch/-Chrome 组合'
  }
  $arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'shot_scroll.py'), '--doctor')
  if ($ProbeLaunch) { $arguments += '--probe-launch' }
  if ($Chrome) { $arguments += @('--executable-path', $Chrome) }
  & $Python @arguments
  exit $LASTEXITCODE
}
if (-not $Url) { throw '截图需要 -Url；只读查找使用 -ListBrowsers 或 -Doctor' }
$arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'shot_scroll.py'),
  '--url', $Url, '--screens', '1', '--width', "$Width", '--height', "$Height",
  '--timeout-ms', "$TimeoutMs", '--wall-timeout-ms', "$WallTimeoutMs")
if ($Engine -ne 'playwright') { $arguments += @('--engine', $Engine) }
if ($ToBottom) { $arguments += '--to-bottom' }
if ($Out) { $arguments += @('--out', $Out) }
if ($Proxy) { $arguments += @('--proxy', $Proxy) }
if ($Chrome) { $arguments += @('--executable-path', $Chrome) }
if ($Channel) { $arguments += @('--channel', $Channel) }
if ($DiscoverBrowser) { $arguments += '--discover-browser' }
& $Python @arguments
exit $LASTEXITCODE
