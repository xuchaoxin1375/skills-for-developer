<#
.SYNOPSIS
    Calibrate text encoding across the hops an agent shell uses.

.DESCRIPTION
    Writes one UTF-8 sample and measures each hop on its own:
      * file bytes -> PowerShell string      (Get-Content / .NET / ASCII JSON)
      * PowerShell string -> stdout          (VISUAL_* lines, judged by eye)
      * native producer -> PS pipeline/file  (redirect / Out-File / Out-String)
      * native producer -> bytes / gate      (documented safe fallbacks)
      * native producer -> direct redirect   (7.4+ keeps raw bytes)

    Matrix cases run one per child process, each starting from a normalized
    "ANSI code page" baseline, so a case cannot inherit state left by an
    earlier one. The matrix emits ASCII only; raw sample text is printed at
    the end under VISUAL_* because only the reader can judge whether the
    harness displays it correctly. The process you start it in is NOT
    reconfigured: the snapshot shows the state the agent actually gets.

    Exit codes: 0 = every safe route preserved, 1 = a safe route failed,
    2 = bad arguments, 3 = incomplete (python not found).

.PARAMETER Case
    'all' runs the snapshot + matrix + visual samples in a fresh child
    process per case, then prints a summary. Any other value runs that one
    case in the current process; those values are used internally by 'all'
    and are not meant to be typed by hand.

.PARAMETER WorkDir
    Directory for probe files. 'all' creates one under the temp directory
    unless you pass this.

.PARAMETER IncludeWindowsPowerShell
    Also run the matrix under Windows PowerShell 5.1 (powershell.exe) when
    it is available, for a same-machine version comparison.

.PARAMETER Keep
    Keep probe files and print their paths, e.g. to compare the harness's
    own file-read tool against PowerShell on the same sample.

.EXAMPLE
    pwsh -NoProfile -File calibrate-encoding.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File calibrate-encoding.ps1 -IncludeWindowsPowerShell -Keep
#>
[CmdletBinding()]
param(
    [string]$Case = 'all',
    [string]$WorkDir = '',
    [switch]$IncludeWindowsPowerShell,
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'

# The whole file is ASCII on purpose: Windows PowerShell 5.1 parses a UTF-8
# file without BOM using the ANSI code page, so non-ASCII source text (even
# comments) could break the probe before it runs. Sample text is built from
# code points and passed to Python as \u escapes.
$script:Utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
$script:Sample = -join ([char[]](0x4E2D, 0x6587, 0x20, 0x63, 0x61, 0x66, 0xE9, 0x20, 0x65E5, 0x672C, 0x8A9E, 0x20, 0xD83D, 0xDE00))
$script:PyEscaped = '\u4e2d\u6587 caf\u00e9 \u65e5\u672c\u8a9e \U0001f600\n'
$script:IsWin = $true
if (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) { $script:IsWin = [bool]$IsWindows }
$script:AnsiCP = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
if (-not $script:IsWin -or $script:AnsiCP -le 0) { $script:AnsiCP = 65001 }
$script:Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $script:Python) { $script:Python = Get-Command python3 -ErrorAction SilentlyContinue }
if ($script:Python) { $script:Python = $script:Python.Source }

$script:Matrix = @(
    'read-default',
    'read-utf8',
    'read-dotnet',
    'read-ascii-json',
    'ps-to-file',
    'redirect-dirty',
    'redirect-utf8',
    'native-redirect',
    'outfile-dirty',
    'outfile-utf8',
    'outstring-dirty',
    'outstring-utf8',
    'gate-utf8',
    'producer-bytes',
    'json-fallback'
)
# Routes that must survive on any host; the rest are facts, not assertions.
$script:SafeCases = @(
    'read-utf8',
    'read-dotnet',
    'read-ascii-json',
    'ps-to-file',
    'gate-utf8',
    'producer-bytes',
    'json-fallback'
)

# One source for valid -Case values: the matrix above plus 'all'.
if ($Case -ne 'all' -and -not ($script:Matrix -contains $Case)) {
    Write-Error ("unknown -Case value: {0}; valid: all, {1}" -f $Case, ($script:Matrix -join ', ')) -ErrorAction Continue
    exit 2
}

function Get-ChcpCodePage {
    if (-not $script:IsWin) { return 'n/a' }
    $raw = (& chcp) 2>$null
    if ($null -eq $raw) { return 'unknown' }
    $digits = ([string]$raw) -replace '[^0-9]', ''
    if ($digits) { return $digits }
    return 'unknown'
}

function Set-DirtyEncoding {
    if ($script:IsWin) { & chcp $script:AnsiCP | Out-Null }
    $enc = [System.Text.Encoding]::GetEncoding($script:AnsiCP)
    [Console]::OutputEncoding = $enc
    # Preference variables are global; assigning inside a function would create
    # a local copy and silently leave the real pipe encoding untouched.
    $global:OutputEncoding = $enc
}

function Set-Utf8Encoding {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $global:OutputEncoding = [System.Text.Encoding]::UTF8
}

# Decode by BOM when present: PowerShell redirection writes UTF-16LE on 5.1,
# and the question is whether the text survived, not which encoding was used.
function Get-FileText([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        return [System.Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        return [System.Text.Encoding]::BigEndianUnicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return $script:Utf8.GetString($bytes, 3, $bytes.Length - 3)
    }
    return $script:Utf8.GetString($bytes)
}

function Test-Text([string]$Text) {
    if ($Text.Contains($script:Sample)) { return 'PASS' }
    $fffd = ([regex]::Matches($Text, [string][char]0xFFFD)).Count
    $question = ([regex]::Matches($Text, '\?\?\?')).Count
    if ($fffd -gt 0) { return 'LOSSY_FFFD' }
    if ($question -gt 0) { return 'LOSSY_ASCII' }
    return 'MANGLED'
}

function Get-FileVerdict([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 'MISSING' }
    return Test-Text (Get-FileText $Path)
}

function Invoke-PyStdout {
    & $script:Python -X utf8 -c "import sys;sys.stdout.write('$script:PyEscaped')"
}

function Invoke-PyStdoutJson {
    & $script:Python -X utf8 -c "import json;print(json.dumps('$script:PyEscaped',ensure_ascii=True))"
}

function Write-PyBytes([string]$Path) {
    & $script:Python -X utf8 -c "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('$script:PyEscaped',encoding='utf-8',newline='')" $Path
}

function Invoke-SingleCase([string]$Name) {
    New-Item -ItemType Directory -Force -Path $script:WorkDir | Out-Null
    $sample = Join-Path $script:WorkDir 'sample.txt'
    [IO.File]::WriteAllText($sample, $script:Sample + "`n", $script:Utf8)
    $out = Join-Path $script:WorkDir ("out-" + $Name + ".txt")
    Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue

    if (-not $script:Python) {
        Write-Output ('CASE ' + $Name + ' RESULT=SKIP_NOPYTHON')
        return
    }

    Set-DirtyEncoding
    $verdict = 'ERROR'
    switch ($Name) {
        'read-default' {
            $verdict = Test-Text (Get-Content -LiteralPath $sample -Raw -ErrorAction Stop)
        }
        'read-utf8' {
            $verdict = Test-Text (Get-Content -LiteralPath $sample -Raw -Encoding UTF8 -ErrorAction Stop)
        }
        'read-dotnet' {
            $verdict = Test-Text ([IO.File]::ReadAllText($sample, $script:Utf8))
        }
        'read-ascii-json' {
            $json = (Invoke-PyStdoutJson) -join ''
            $verdict = Test-Text ([string]($json | ConvertFrom-Json))
        }
        'ps-to-file' {
            [IO.File]::WriteAllText($out, $script:Sample + "`n", $script:Utf8)
            $verdict = Get-FileVerdict $out
        }
        'redirect-dirty' {
            Invoke-PyStdout > $out
            $verdict = Get-FileVerdict $out
        }
        'redirect-utf8' {
            Set-Utf8Encoding
            Invoke-PyStdout > $out
            $verdict = Get-FileVerdict $out
        }
        # Direct native redirect: no PowerShell command/function in between, so
        # pwsh 7.4+ can keep the producer's raw bytes. Wrapping the same call in
        # a function or piping it through Out-File turns it into PS text again.
        'native-redirect' {
            & $script:Python -X utf8 -c "import sys;sys.stdout.write('$script:PyEscaped')" > $out
            $verdict = Get-FileVerdict $out
        }
        'outfile-dirty' {
            Invoke-PyStdout | Out-File -LiteralPath $out -Encoding utf8
            $verdict = Get-FileVerdict $out
        }
        'outfile-utf8' {
            Set-Utf8Encoding
            Invoke-PyStdout | Out-File -LiteralPath $out -Encoding utf8
            $verdict = Get-FileVerdict $out
        }
        'outstring-dirty' {
            $text = (Invoke-PyStdout | Out-String)
            [IO.File]::WriteAllText($out, $text, $script:Utf8)
            $verdict = Get-FileVerdict $out
        }
        'outstring-utf8' {
            Set-Utf8Encoding
            $text = (Invoke-PyStdout | Out-String)
            [IO.File]::WriteAllText($out, $text, $script:Utf8)
            $verdict = Get-FileVerdict $out
        }
        'gate-utf8' {
            Set-Utf8Encoding
            Invoke-PyStdout | & $script:Python -X utf8 -c "import sys,pathlib;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())" $out
            $verdict = Get-FileVerdict $out
        }
        'producer-bytes' {
            Write-PyBytes $out
            $verdict = Get-FileVerdict $out
        }
        'json-fallback' {
            $json = (Invoke-PyStdoutJson) -join ''
            $text = [string]($json | ConvertFrom-Json)
            [IO.File]::WriteAllText($out, $text, $script:Utf8)
            $verdict = Get-FileVerdict $out
        }
        default {
            throw "unknown case: $Name"
        }
    }

    $state = 'DOTNET=' + [Console]::OutputEncoding.CodePage +
        ' OUTENC=' + $OutputEncoding.CodePage +
        ' CHCP=' + (Get-ChcpCodePage)
    Write-Output ('CASE ' + $Name + ' RESULT=' + $verdict + ' ' + $state)
}

function Get-Snapshot {
    $profileState = 'missing'
    if ($PROFILE -and (Test-Path -LiteralPath $PROFILE)) { $profileState = 'exists' }
    $pyVersion = 'n/a'
    if ($script:Python) {
        $rawVersion = & $script:Python -X utf8 -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($rawVersion) { $pyVersion = ([string]$rawVersion).Trim() }
    }
    'CALIB_SNAPSHOT_BEGIN'
    'CALIB_PS=' + $PSVersionTable.PSVersion.ToString() + ' EDITION=' + $PSVersionTable.PSEdition
    'CALIB_EXE=' + [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    'CALIB_CULTURE=' + [System.Globalization.CultureInfo]::CurrentCulture.Name
    'CALIB_ANSI_CP=' + $script:AnsiCP
    'CALIB_DOTNET_DEFAULT_CP=' + [System.Text.Encoding]::Default.CodePage
    'CALIB_CONSOLE_OUTPUT_CP=' + [Console]::OutputEncoding.CodePage
    'CALIB_OUTPUTENC_CP=' + $OutputEncoding.CodePage
    # chcp self-report only: it can disagree with Console.OutputEncoding and with
    # what child processes actually inherit, so judge the real state from the
    # two lines above.
    'CALIB_CHCP=' + (Get-ChcpCodePage)
    'CALIB_ISOUTREDIRECTED=' + [Console]::IsOutputRedirected
    'CALIB_PROFILE=' + $profileState
    'CALIB_PYTHON=' + $script:Python
    'CALIB_PYTHON_VERSION=' + $pyVersion
    'CALIB_SNAPSHOT_END'
}

function Show-Visuals {
    # Do not touch encoding here: these lines show what this process sends as-is.
    'VISUAL_NOTE=judge these lines in raw output; piping them through Select-Object/Out-String mangles them'
    'VISUAL_EXPECT=U+4E2D U+6587 space c a f U+00E9 space U+65E5 U+672C U+8A9E space U+1F600'
    'VISUAL_EXPECT_CODEPOINTS=' + (($script:Sample.ToCharArray() | ForEach-Object { [int]$_ }) -join ',')
    'VISUAL_PS_TEXT_BEGIN'
    Write-Output $script:Sample
    'VISUAL_PS_TEXT_END'
    if ($script:Python) {
        'VISUAL_CHILD_TEXT_BEGIN'
        Invoke-PyStdout
        'VISUAL_CHILD_TEXT_END'
    }
}

function Invoke-All {
    $root = $WorkDir
    if (-not $root) {
        $root = Join-Path ([IO.Path]::GetTempPath()) ('opencode\enc-calib-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    }
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $script:WorkDir = $root

    'CALIB_PROBE=1'
    $scriptName = $PSCommandPath
    $exe = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName

    Get-Snapshot
    'CALIB_WORKDIR=' + $root

    $hosts = @(@{ Tag = 'current'; Exe = $exe; Extra = @() })
    # Skip the duplicate when the script itself already runs on 5.1.
    $already51 = $exe.ToLowerInvariant().EndsWith('powershell.exe')
    if ($IncludeWindowsPowerShell -and $script:IsWin -and -not $already51) {
        $ps51 = Get-Command powershell.exe -ErrorAction SilentlyContinue
        if ($ps51) {
            $hosts += @{ Tag = 'ps51'; Exe = $ps51.Source; Extra = @('-ExecutionPolicy', 'Bypass') }
        }
    }

    $failures = 0
    $safeTotal = 0
    $safePass = 0
    $transitTotal = 0
    $transitPass = 0

    foreach ($hostInfo in $hosts) {
        'CALIB_MATRIX_BEGIN host=' + $hostInfo.Tag
        $dir = Join-Path $root $hostInfo.Tag
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        foreach ($name in $script:Matrix) {
            $childArgs = @('-NoLogo', '-NoProfile', '-NonInteractive')
            $childArgs += $hostInfo.Extra
            $childArgs += @('-File', $scriptName, '-Case', $name, '-WorkDir', $dir)
            $raw = & $hostInfo.Exe @childArgs 2>&1
            $line = @($raw | Where-Object { $_ -is [string] -and $_ -match '^CASE ' })
            if ($line.Count -eq 0) {
                Write-Output ('CASE ' + $name + ' RESULT=CHILD_ERROR')
                $line = @('CASE ' + $name + ' RESULT=CHILD_ERROR')
            }
            Write-Output $line[0]

            if ($line[0] -match '^CASE \S+ RESULT=(\S+)') {
                $result = $Matches[1]
                $isSafe = $script:SafeCases -contains $name
                if ($isSafe) {
                    $safeTotal++
                    if ($result -eq 'PASS') { $safePass++ } else { $failures++ }
                } else {
                    $transitTotal++
                    if ($result -eq 'PASS') { $transitPass++ }
                }
            }
        }
        'CALIB_MATRIX_END host=' + $hostInfo.Tag
    }

    Show-Visuals

    'CALIB_SAFE_ROUTES=' + $safePass + '/' + $safeTotal
    'CALIB_TRANSIT_ROUTES=' + $transitPass + '/' + $transitTotal + ' (informational)'
    if (-not $script:Python) { 'CALIB_INCOMPLETE=python-missing' }

    if ($Keep) {
        'CALIB_SAMPLE_FILE=' + (Join-Path (Join-Path $root 'current') 'sample.txt')
        'CALIB_KEPT=' + $root
    } else {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    }

    $script:ExitCode = 0
    if (-not $script:Python) { $script:ExitCode = 3 }
    elseif ($failures -gt 0) { $script:ExitCode = 1 }
    'CALIB_EXIT=' + $script:ExitCode
}

if ($Case -eq 'all') {
    # Invoke-All writes its report to the host; the exit code travels separately
    # so the report is not swallowed into a return value.
    Invoke-All
    exit $script:ExitCode
}

if (-not $WorkDir) {
    Write-Error 'WorkDir is required for a single case.' -ErrorAction Continue
    exit 2
}
$script:WorkDir = $WorkDir
Invoke-SingleCase $Case
exit 0
