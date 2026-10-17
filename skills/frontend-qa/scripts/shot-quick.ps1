#Requires -Version 7
<#
.SYNOPSIS
  旧截图入口；参数委托给 browser-automation 的维护版本。
#>
[CmdletBinding()]
param(
  [string]$Url, [string]$Out, [int]$Width, [int]$Height,
  [string]$Proxy, [string]$Chrome, [string]$Channel,
  [switch]$DiscoverBrowser, [switch]$ListBrowsers, [string]$Python,
  [int]$TimeoutMs, [int]$WallTimeoutMs
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$entry = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'browser-automation/scripts/shot-quick.ps1'
& $entry @PSBoundParameters
exit $LASTEXITCODE
