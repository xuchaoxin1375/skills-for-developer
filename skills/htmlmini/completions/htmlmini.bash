# htmlmini bash completion: source this file or drop it into bash_completion.d.
#   source /path/to/skills-for-developer/skills/htmlmini/completions/htmlmini.bash
# Or print it on demand: htmlmini --completion bash
_htmlmini() {
  local cur prev modes extractors
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  modes="markdown json skeleton ui text title"
  extractors="auto defuddle trafilatura semantic ui"
  case "$prev" in
    --mode) COMPREPLY=( $(compgen -W "$modes" -- "$cur") ); return 0 ;;
    --extractor) COMPREPLY=( $(compgen -W "$extractors" -- "$cur") ); return 0 ;;
    --completion) COMPREPLY=( $(compgen -W "bash powershell" -- "$cur") ); return 0 ;;
    -o|--output) COMPREPLY=( $(compgen -f -- "$cur") ); return 0 ;;
  esac
  if [[ "$cur" == -* ]]; then
    COMPREPLY=( $(compgen -W "--markdown --json --skeleton --ui --text --title --mode --extractor --output --list-modes --list-extractors --completion --help" -- "$cur") )
  else
    COMPREPLY=( $(compgen -f -- "$cur") )
  fi
}
complete -F _htmlmini htmlmini
