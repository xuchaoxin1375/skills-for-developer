<#
.SYNOPSIS
  Render one Mermaid file (or the mermaid blocks of a markdown file) with mermaid-cli.

.DESCRIPTION
  One command for the mermaid-render-fix loop: precheck -> resolve renderer ->
  render -> report exit code and elapsed milliseconds.

  - Renderer order: mmdc on PATH, then 'pnpm dlx', then 'npx -y -p'.
  - The browser (Chrome/Edge/Chromium) is auto-detected and written to a temporary
    puppeteer config, so puppeteer never downloads Chromium.
  - Only flags valid for current mermaid-cli are used: 12.x dropped '-w/--width'
    in favour of '--size', and '--puppeteerConfigFile' is the long form of '-p'.
  - The temporary config and directory are removed on success and on failure.

  Logs go to stdout as KEY=VALUE lines; warnings and errors go to stderr.

  Exit codes:
    0 ok
    1 usage or input error
    2 precheck reported SUSPICIOUS (only with -CheckOnly)
    3 no renderer available (no mmdc / pnpm / npx)
    4 render failed or the output file is missing/empty
    5 no browser found and -PuppeteerConfigFile was not given

.PARAMETER InputFile
  Path to a .mmd file, or to a .md file whose mermaid blocks get rendered.

.PARAMETER OutputFile
  Output path; the format follows the extension (.png/.svg/.pdf).
  Default for .mmd input: same name with a .png extension.
  Markdown input needs an explicit -OutputFile with a .md extension (mermaid-cli
  then writes the rendered blocks as artefacts next to it).

.PARAMETER Size
  Maximum width/height in px for PNG, max-width for SVG (mermaid-cli '--size').

.PARAMETER Theme
  mermaid theme name, e.g. default, forest, dark, neutral.

.PARAMETER BrowserPath
  Explicit browser executable; skips auto-detection.

.PARAMETER PuppeteerConfigFile
  Existing puppeteer config JSON; skips browser detection and temp file creation.

.PARAMETER CheckOnly
  Run the heuristic precheck only, no rendering.

.PARAMETER KeepTemp
  Keep the generated puppeteer config for debugging.

.EXAMPLE
  render_mmd.ps1 -InputFile .\block.mmd

.EXAMPLE
  render_mmd.ps1 -i .\block.mmd -o .\block.svg -s 1200

.EXAMPLE
  render_mmd.ps1 -i .\block.mmd -c
#>
#Requires -Version 5.1
[CmdletBinding()]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '',
  Justification = 'Log lines must bypass the output stream: Main returns an exit code, and native output written into it would corrupt that return value.')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', '',
  Justification = 'Script parameters are consumed inside Main; the analyzer only inspects top-level scope.')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '',
  Justification = 'New-PuppeteerConfig only writes a config file into the caller-supplied temp directory.')]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [Alias('i')]
  [string]$InputFile,

  [Alias('o')]
  [string]$OutputFile = '',

  [Alias('s')]
  [int]$Size = 0,

  [Alias('t')]
  [string]$Theme = '',

  [Alias('b')]
  [string]$BrowserPath = '',

  [Alias('p')]
  [string]$PuppeteerConfigFile = '',

  [Alias('c')]
  [switch]$CheckOnly,

  [Alias('k')]
  [switch]$KeepTemp
)

$ErrorActionPreference = 'Stop'

function Write-Err([string]$Message) {
  [Console]::Error.WriteLine("render_mmd: $Message")
}

function Write-Usage {
  [Console]::Error.WriteLine(@'
usage: render_mmd.ps1 -InputFile <file.mmd|file.md> [options]

  -i  -InputFile            .mmd file, or .md file with mermaid blocks
  -o  -OutputFile           .png/.svg/.pdf output (default: <input>.png)
  -s  -Size                 max px for png, max-width for svg
  -t  -Theme                mermaid theme (default, forest, dark, neutral, ...)
  -b  -BrowserPath          explicit Chrome/Edge/Chromium executable
  -p  -PuppeteerConfigFile  existing puppeteer config JSON
  -c  -CheckOnly            heuristic precheck only
  -k  -KeepTemp             keep the generated puppeteer config
'@)
}

function Join-Base([string]$Base, [string]$Child) {
  if ([string]::IsNullOrWhiteSpace($Base)) { return $null }
  return (Join-Path $Base $Child)
}

function Get-BrowserPath {
  $candidates = @()
  $candidates += Join-Base $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
  $candidates += Join-Base ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'
  $candidates += Join-Base $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'
  $candidates += Join-Base $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
  $candidates += Join-Base ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
  $candidates += '/usr/bin/google-chrome'
  $candidates += '/usr/bin/chromium'
  $candidates += '/usr/bin/chromium-browser'
  $candidates += '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { return $c }
  }
  return $null
}

function Get-PnpmMajor([string]$Exe) {
  $raw = & $Exe --version 2>$null
  if (-not $raw) { return 0 }
  $parts = ([string]$raw).Trim().Split('.')
  $major = 0
  if ([int]::TryParse($parts[0], [ref]$major)) { return $major }
  return 0
}

function Get-ApplicationCommand([string]$Name) {
  # Prefer a real executable/.cmd shim: invoking a .ps1 shim leaves
  # $LASTEXITCODE stale, so a failed render can look like a success.
  return (Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Resolve-Renderer {
  $mmdc = Get-ApplicationCommand 'mmdc'
  if (-not $mmdc) {
    $mmdc = Get-Command mmdc -ErrorAction SilentlyContinue
  }
  if ($mmdc) {
    return @{ Name = 'mmdc'; Exe = $mmdc.Source; Prefix = @() }
  }
  $pnpm = Get-ApplicationCommand 'pnpm'
  if ($pnpm) {
    $prefix = @('dlx', '--package', '@mermaid-js/mermaid-cli')
    if ((Get-PnpmMajor $pnpm.Source) -ge 10) {
      # pnpm 10+ blocks dependency build scripts unless allowed.
      $prefix = @('dlx', '--allow-build=puppeteer', '--package', '@mermaid-js/mermaid-cli')
    }
    $prefix += 'mmdc'
    return @{ Name = 'pnpm-dlx'; Exe = $pnpm.Source; Prefix = $prefix }
  }
  $npx = Get-ApplicationCommand 'npx'
  if ($npx) {
    return @{
      Name   = 'npx'
      Exe    = $npx.Source
      Prefix = @('-y', '-p', '@mermaid-js/mermaid-cli', 'mmdc')
    }
  }
  return $null
}

function New-PuppeteerConfig([string]$Browser, [string]$Directory) {
  $payload = @{ executablePath = $Browser }
  if ($env:OS -ne 'Windows_NT') {
    $payload.args = @('--no-sandbox', '--disable-dev-shm-usage')
  }
  $path = Join-Path $Directory 'puppeteer.json'
  # No BOM: mermaid-cli feeds this file straight to JSON.parse.
  $json = $payload | ConvertTo-Json -Compress
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [IO.File]::WriteAllText($path, $json, $utf8NoBom)
  return $path
}

function Invoke-Precheck([string]$Path) {
  $checker = Join-Path $PSScriptRoot 'check_mermaid.py'
  if (-not (Test-Path -LiteralPath $checker -PathType Leaf)) {
    Write-Err "precheck script not found: $checker"
    return 1
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
  if (-not $python) {
    Write-Err 'python not found, skipping precheck'
    return -1
  }
  # Output is captured so it does not leak into the return value; the ASCII
  # status words (OK/SUSPICIOUS) are what the caller relies on, echoed detail
  # lines may lose non-ASCII characters in console capture.
  $report = & $python.Source -X utf8 $checker $Path
  $code = $LASTEXITCODE
  foreach ($line in $report) { Write-Host $line }
  return $code
}

function Main {
  if (-not (Test-Path -LiteralPath $InputFile -PathType Leaf)) {
    Write-Err "input not found: $InputFile"
    Write-Usage
    return 1
  }
  $inPath = (Resolve-Path -LiteralPath $InputFile).Path
  $isMarkdown = $inPath -match '\.(md|markdown)$'
  Write-Host "INPUT=$inPath"

  $precheck = Invoke-Precheck $inPath
  if ($precheck -eq 1) {
    Write-Err 'precheck found no mermaid blocks (or failed)'
    return 1
  }
  if ($precheck -eq 2) {
    Write-Err 'precheck reported SUSPICIOUS lines; rendering anyway is still authoritative'
  }

  if ($CheckOnly) {
    if ($precheck -eq 2) { return 2 }
    Write-Host 'CHECK=OK'
    return 0
  }

  if (-not $OutputFile) {
    if ($isMarkdown) {
      Write-Err 'markdown input needs an explicit -OutputFile (e.g. -o out.md)'
      Write-Usage
      return 1
    }
    $OutputFile = [IO.Path]::ChangeExtension($inPath, '.png')
  }

  $renderer = Resolve-Renderer
  if (-not $renderer) {
    Write-Err 'no renderer found: install mmdc, or make pnpm/npx available'
    return 3
  }
  Write-Host ("RENDERER=" + $renderer.Name)

  $tempDir = $null
  $pupPath = $PuppeteerConfigFile
  if ($pupPath -and -not (Test-Path -LiteralPath $pupPath -PathType Leaf)) {
    Write-Err "puppeteer config not found: $pupPath"
    return 1
  }
  try {
    if (-not $pupPath) {
      $browser = $BrowserPath
      if (-not $browser) { $browser = Get-BrowserPath }
      if (-not $browser) {
        Write-Err 'no browser found; pass -BrowserPath or -PuppeteerConfigFile'
        return 5
      }
      if (-not (Test-Path -LiteralPath $browser -PathType Leaf)) {
        Write-Err "browser not found: $browser"
        return 5
      }
      $tempDir = Join-Path ([IO.Path]::GetTempPath()) ('render_mmd_' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
      New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
      $pupPath = New-PuppeteerConfig $browser $tempDir
      $env:PUPPETEER_SKIP_DOWNLOAD = 'true'
      Write-Host "BROWSER=$browser"
    }

    $arguments = @()
    $arguments += $renderer.Prefix
    $arguments += @('-p', $pupPath, '-i', $inPath, '-o', $OutputFile)
    if ($Size -gt 0) { $arguments += @('--size', [string]$Size) }
    if ($Theme) { $arguments += @('--theme', $Theme) }

    # The output is a derived artefact: clearing it first makes the "file exists
    # and is non-empty" check below a real signal instead of a stale file.
    if (Test-Path -LiteralPath $OutputFile) {
      Remove-Item -LiteralPath $OutputFile -Force
    }

    $LASTEXITCODE = 0
    $watch = [Diagnostics.Stopwatch]::StartNew()
    # Capture stdout and re-emit it: native output written straight into this
    # function would become part of Main's return value. stderr is left alone so
    # parser errors keep their raw bytes and stream.
    $output = & $renderer.Exe @arguments
    $code = $LASTEXITCODE
    $watch.Stop()
    foreach ($line in $output) { Write-Host $line }
    Write-Host ('ELAPSED_MS=' + [int]$watch.Elapsed.TotalMilliseconds)
    Write-Host "RENDERER_EXIT=$code"

    $outItem = Get-Item -LiteralPath $OutputFile -ErrorAction SilentlyContinue
    if ($code -ne 0) {
      Write-Host 'RENDER=FAILED'
      Write-Err "renderer exited with $code"
      return 4
    }
    if (-not $outItem -or $outItem.Length -eq 0) {
      Write-Host 'RENDER=FAILED'
      # 'pnpm dlx' has been observed exiting 0 when the inner mermaid-cli run
      # threw, so the artefact check below is the real gate.
      Write-Err "no output produced: $OutputFile (exit was 0; see stderr for the parser error)"
      return 4
    }
    Write-Host 'RENDER=OK'
    Write-Host ('OUTPUT=' + $outItem.FullName)
    Write-Host ('BYTES=' + $outItem.Length)
    return 0
  }
  finally {
    if ($tempDir -and -not $KeepTemp) {
      Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

exit (Main)
