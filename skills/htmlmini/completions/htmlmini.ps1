# htmlmini PowerShell completion. Load it in your profile, or print it on demand:
#   htmlmini --completion powershell
Register-ArgumentCompleter -Native -CommandName htmlmini -ScriptBlock {
  param($wordToComplete, $commandAst, $cursorPosition)
  $modes = @('markdown', 'json', 'skeleton', 'ui', 'text', 'title', 'html')
  $extractors = @('auto', 'defuddle', 'trafilatura', 'semantic', 'ui', 'sanitize', 'passthrough')
  $attrs = @('semantic', 'none', 'all')
  $flags = @('--markdown', '--json', '--skeleton', '--ui', '--text', '--title',
    '--mode', '--extractor', '--attrs', '--proxy', '--noproxy', '--render', '--headful', '--render-timeout-ms',
    '--chrome-bin', '--output', '--list-modes', '--list-extractors',
    '--completion', '--help', '-m', '-j', '-s', '-u', '-t', '-T', '-o', '-h')
  $tokens = $commandAst.ToString() -split '\s+'
  $prev = if ($tokens.Count -ge 2) { $tokens[$tokens.Count - 2] } else { '' }
  $list = switch ($prev) {
    '--mode' { $modes; break }
    '--extractor' { $extractors; break }
    '--attrs' { $attrs; break }
    '--completion' { @('bash', 'powershell'); break }
    default { $null }
  }
  if ($list) {
    $list | Where-Object { $_ -like "$wordToComplete*" } |
      ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }
  } else {
    $flags | Where-Object { $_ -like "$wordToComplete*" } |
      ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', $_) }
  }
}
