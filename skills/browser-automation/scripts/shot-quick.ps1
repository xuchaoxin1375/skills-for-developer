#Requires -Version 7
<#
.SYNOPSIS
  首屏截图兼容入口；委托 shot_scroll.py 托管浏览器，不直接创建 Chrome 进程。
.DESCRIPTION
  需要目标 Python 环境已有 Playwright。默认使用匹配缓存；本机 Edge/Chrome 可传
  -Channel，或 -DiscoverBrowser 查常用位置，免下载浏览器。-ListBrowsers 只读列候选。
  总期限与回收由独立 guardian 负责；失败不自动重试。
.EXAMPLE
  ./shot-quick.ps1 -Url 'https://example.com' -Channel msedge -Out page.png
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
if (-not $Url) { throw '截图需要 -Url；只读查找使用 -ListBrowsers' }
$arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'shot_scroll.py'),
  '--url', $Url, '--screens', '1', '--width', "$Width", '--height', "$Height",
  '--timeout-ms', "$TimeoutMs", '--wall-timeout-ms', "$WallTimeoutMs")
if ($Out) { $arguments += @('--out', $Out) }
if ($Proxy) { $arguments += @('--proxy', $Proxy) }
if ($Chrome) { $arguments += @('--executable-path', $Chrome) }
if ($Channel) { $arguments += @('--channel', $Channel) }
if ($DiscoverBrowser) { $arguments += '--discover-browser' }
& $Python @arguments
exit $LASTEXITCODE
