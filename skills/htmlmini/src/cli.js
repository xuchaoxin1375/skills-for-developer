#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { ATTR_POLICIES, EXTRACTORS, FORMAT_POLICIES, MODES, runExtract } from './extract.js';
import { fmtBytes, fmtMs, log, setLogLevel } from './log.js';
import { VERSION, VERSION_LINE } from './version.js';

const HELP = `htmlmini ${VERSION} - strip CSS/JS from HTML, keep the core as Markdown (token-efficient for LLMs)

USAGE
  htmlmini [source] [options]

SOURCE
  <file>          local HTML file (a "<file>.meta.json" next to it is auto-used for the page URL,
                  e.g. pages saved by resilient-browser-fetch save_page)
  <http(s) url>   fetch a URL (uses Defuddle + schema.org metadata)
  -               read HTML from stdin (default)

OPTIONS
  -m, --markdown   output Markdown                (default; article pages use Defuddle,
                                                   UI pages auto-fallback to component inventory)
  -j, --json       output JSON {title, used, requested, version, content, stats{reductionPct}, meta?}
  -s, --skeleton   outline only: headings, tables, code-block languages
  -u, --ui         force UI-component inventory (labels/buttons/selects/tables)
  -t, --text       plain text (no markup)
  -T, --title      print only the page title
  --mode <name>    same as the flags above; explicit form for agents/scripts.
                   "html" returns the cleaned HTML itself: full DOM structure and text
                   order kept, scripts/styles/templates/icons and comments dropped,
                   appearance attributes stripped by --attrs (higher token cost than
                   markdown/ui, but nothing is truncated)
  --attrs <policy> attribute policy for --mode html (default semantic):
                   semantic = keep href/src/alt/colspan/rowspan/table+form state (recommended)
                   none     = strip every attribute (smallest; loses link targets)
                   all      = keep all attributes, only drop scripts/styles
  --format <policy> layout policy for --mode html (default compact):
                   compact  = drop source indentation and blank lines; a single space is
                              kept between inline elements (smallest, nothing reordered)
                   pretty   = re-indent for readability (uses the js-beautify dependency)
                   raw      = leave the original source whitespace as-is
  --compact        shorthand for --format compact
  --pretty         shorthand for --format pretty
  --prune-empty    with --mode html: also drop containers left empty after cleaning
                   (empty div/span/nav/header ...); table/form/pre structure is kept
  --text-max <n>   with --mode ui / --extractor ui: max characters for one text entry
                   (default 150). Longer paragraphs are dropped from the inventory and
                   the output says how many. 0 = no limit (keeps full long paragraphs).
  --allow-empty    keep the result even when it looks like a client-rendered app shell
                   (extracted text < 200 chars from >= 5 KB HTML). Default: such pages
                   error with a hint to use --render=always.
  --proxy <url>    proxy override for URL fetch: http(s) URL, or "direct" to
                   bypass env proxy (default follows HTTP_PROXY/HTTPS_PROXY/NO_PROXY)
  --noproxy        force direct connection, ignoring env proxy
  --render[=mode]   fall back to browser rendering. Default (no value / "auto"):
                   only on static 403/5xx. Chain: save_page (needs a layer >= 1
                   engine: playwright/patchright, scrapling, or cloak-cdp) ->
                   system Chrome headless dump-dom (zero-dep) -> friendly error.
                   "always": render even when the static fetch returns 200.
                   Use it for client-rendered pages whose HTML is 200 but whose
                   body only exists after hydration.
                   404/timeout/network errors still throw without rendering
  --render-always  shorthand for --render=always
  --headful        show the browser window during fallback rendering
                   (implies --render; needs a layer >= 1 save_page engine,
                   for first-time manual verification)
  --render-timeout-ms <ms>
                   timeout for the fallback browser render (default 300000;
                   chrome dump-dom is capped at 120000)
  --chrome-bin <path>
                   explicit Chrome/Chromium binary for the zero-dep chrome
                   fallback (default auto-detects: PATH, common paths,
                   Playwright browser cache; or HTMLMINI_CHROME_BIN)
  --python-bin <path>
                   explicit Python interpreter for --render (save_page) and the
                   optional Trafilatura pass. Default: "python"/"python3" on PATH,
                   which is often NOT the environment that has playwright or
                   scrapling installed; env: HTMLMINI_PYTHON. Use "auto" to scan
                   this machine (conda/venv/uv/PATH) and pick an interpreter that
                   has a layer >= 1 engine. When rendering fails for lack of an
                   engine, the error also names such an interpreter if one exists.
                   Disable scanning with HTMLMINI_ENV_SCAN=0.
  --extractor <name>
                   extraction engine: auto (default) | defuddle | trafilatura | semantic | ui | passthrough
                   auto chain: non-HTML passthrough -> Defuddle -> Trafilatura (only if "pip install trafilatura"
                   is present, silently skipped otherwise) -> semantic -> ui inventory.
                   Non-HTML (markdown/plain/JSON) is passed through untouched in any mode.
                   Forcing an engine returns its raw result (no silent switching).
  --list-modes       print available modes
  --list-extractors  print available extractors
  --completion <shell>
                   print a completion script: bash | powershell
  -o, --output <f> write to file instead of stdout (file ends with exactly one
                   newline; prefer this over capturing stdout through a shell
                   pipeline, which can add extra blank lines)
  --quiet          only errors on stderr (progress is hidden)
  --verbose        extra detail on stderr ([read]/[extract] internals, timings, sizes)
                   Progress goes to stderr as "htmlmini: [read|parse|extract|format|write] ...",
                   so stdout keeps the payload only. Env: HTMLMINI_LOG=quiet|info|debug.
  -h, --help       show this help
  -V, --version    print version (date-time based, YYYY.MM.DD.HHmm) and exit

EXAMPLES
  htmlmini --version                       # -> htmlmini <YYYY.MM.DD.HHmm>
  htmlmini page.html                       # -> markdown to stdout
  htmlmini page.html --json                # -> metadata + extractor + savings %
  htmlmini 报表面板.html -u                 # -> force UI inventory
  htmlmini page.html --mode html           # -> cleaned HTML (structure kept, scripts/styles/attrs gone)
  htmlmini page.html --mode html --attrs none
  htmlmini page.html --mode html --pretty  # -> re-indented cleaned HTML
  htmlmini page.html --mode html --prune-empty --attrs none   # -> smallest structural skeleton
  htmlmini page.html -u --text-max 0       # UI inventory without the per-entry length cap
  htmlmini "https://example.com/spa" --render=always   # render even though static returns 200
  htmlmini dashboard.html --mode json --extractor ui
  htmlmini "https://example.com/a" -s      # -> outline of remote page
  cat page.html | htmlmini - --text        # -> plain text
  # pipeline with resilient-browser-fetch (rendered HTML + sibling .meta.json):
  python scripts/example_save_page.py "https://example.com/app" --out app.html
  htmlmini app.html --json
`;

const MODE_FLAGS = {
  '-m': 'markdown',
  '--markdown': 'markdown',
  '-j': 'json',
  '--json': 'json',
  '-s': 'skeleton',
  '--skeleton': 'skeleton',
  '-u': 'ui',
  '--ui': 'ui',
  '-t': 'text',
  '--text': 'text',
  '-T': 'title',
  '--title': 'title',
};

function splitEq(arg) {
  const i = arg.indexOf('=');
  return i < 0 ? [arg, null] : [arg.slice(0, i), arg.slice(i + 1)];
}

async function printCompletion(shell) {
  const file = shell === 'bash' ? '../completions/htmlmini.bash' : shell === 'powershell' ? '../completions/htmlmini.ps1' : null;
  if (!file) {
    log.error(`unknown shell "${shell}" (use: bash | powershell)`);
    process.exit(2);
  }
  process.stdout.write(await readFile(new URL(file, import.meta.url), 'utf8'));
  process.exit(0);
}

const argv = process.argv.slice(2);
let source = '-';
let mode = 'markdown';
let extractor = 'auto';
let output = null;
let proxy;
let render = false;
let renderTimeoutMs;
let headful = false;
let chromeBin;
let pythonBin;
let attrs = 'semantic';
let format = 'compact';
let pruneEmpty = false;
let textMax = 150;
let allowEmpty = false;
let logLevelOverride = null;

for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '-h' || a === '--help') {
    process.stdout.write(HELP);
    process.exit(0);
  } else if (a === '-V' || a === '--version') {
    process.stdout.write(`${VERSION_LINE}\n`);
    process.exit(0);
  } else if (a === '--list-modes') {
    process.stdout.write(`${MODES.join('\n')}\n`);
    process.exit(0);
  } else if (a === '--list-extractors') {
    process.stdout.write(`${EXTRACTORS.join('\n')}\n`);
    process.exit(0);
  } else if (a === '-o' || a === '--output') {
    output = argv[++i];
    if (!output) {
      log.error('--output needs a file argument');
      process.exit(2);
    }
  } else if (a === '--mode' || a === '--extractor' || a === '--attrs' || a === '--format' || a === '--completion' || a === '--proxy' || a === '--chrome-bin' || a === '--python-bin') {
    const v = argv[++i];
    if (!v) {
      log.error(`${a} needs a value`);
      process.exit(2);
    }
    if (a === '--mode') mode = v;
    else if (a === '--extractor') extractor = v;
    else if (a === '--attrs') attrs = v;
    else if (a === '--format') format = v;
    else if (a === '--proxy') proxy = v;
    else if (a === '--chrome-bin') chromeBin = v;
    else if (a === '--python-bin') pythonBin = v;
    else await printCompletion(v);
  } else if (a === '--compact') {
    format = 'compact';
  } else if (a === '--pretty') {
    format = 'pretty';
  } else if (a === '--prune-empty') {
    pruneEmpty = true;
  } else if (a === '--text-max') {
    const v = argv[++i];
    textMax = Number(v);
    if (!Number.isFinite(textMax) || textMax < 0) {
      log.error(`--text-max needs a number >= 0 (0 = no limit), got "${v ?? ''}"`);
      process.exit(2);
    }
  } else if (a.startsWith('--text-max=')) {
    const [, v] = splitEq(a);
    textMax = Number(v);
    if (!Number.isFinite(textMax) || textMax < 0) {
      log.error(`--text-max needs a number >= 0 (0 = no limit), got "${v ?? ''}"`);
      process.exit(2);
    }
  } else if (a === '--allow-empty') {
    allowEmpty = true;
  } else if (a === '--quiet') {
    logLevelOverride = 'quiet';
  } else if (a === '--verbose') {
    logLevelOverride = 'debug';
  } else if (a === '--noproxy') {
    proxy = 'direct';
  } else if (a === '--render') {
    render = true;
  } else if (a === '--render-always') {
    render = 'always';
  } else if (a.startsWith('--render=')) {
    const [, v] = splitEq(a);
    if (v !== 'always' && v !== 'auto') {
      log.error(`--render accepts "auto" or "always" (got "${v}")`);
      process.exit(2);
    }
    render = v === 'always' ? 'always' : true;
  } else if (a === '--headful') {
    headful = true;
    render = true;
  } else if (a === '--render-timeout-ms') {
    const v = argv[++i];
    renderTimeoutMs = Number(v);
    if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
      log.error(`--render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
      process.exit(2);
    }
  } else if (a.startsWith('--mode=') || a.startsWith('--extractor=') || a.startsWith('--attrs=') || a.startsWith('--format=') || a.startsWith('--output=') || a.startsWith('--completion=') || a.startsWith('--proxy=') || a.startsWith('--chrome-bin=') || a.startsWith('--python-bin=') || a.startsWith('--render-timeout-ms=')) {
    const [k, v] = splitEq(a);
    if (k === '--mode') mode = v;
    else if (k === '--extractor') extractor = v;
    else if (k === '--attrs') attrs = v;
    else if (k === '--format') format = v;
    else if (k === '--output') output = v;
    else if (k === '--proxy') proxy = v;
    else if (k === '--chrome-bin') chromeBin = v;
    else if (k === '--python-bin') pythonBin = v;
    else if (k === '--render-timeout-ms') {
      renderTimeoutMs = Number(v);
      if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
        log.error(`--render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
        process.exit(2);
      }
    } else await printCompletion(v);
  } else if (MODE_FLAGS[a]) {
    mode = MODE_FLAGS[a];
  } else if (a === '-' || !a.startsWith('-')) {
    source = a;
  } else {
    log.error(`unknown option "${a}" (see --help)`);
    process.exit(2);
  }
}

if (!MODES.includes(mode)) {
  log.error(`unknown mode "${mode}" (see --list-modes)`);
  process.exit(2);
}
if (!EXTRACTORS.includes(extractor)) {
  log.error(`unknown extractor "${extractor}" (see --list-extractors)`);
  process.exit(2);
}
if (!ATTR_POLICIES.includes(attrs)) {
  log.error(`unknown --attrs policy "${attrs}" (use: ${ATTR_POLICIES.join(' | ')})`);
  process.exit(2);
}
if (!FORMAT_POLICIES.includes(format)) {
  log.error(`unknown --format policy "${format}" (use: ${FORMAT_POLICIES.join(' | ')})`);
  process.exit(2);
}
if (logLevelOverride) setLogLevel(logLevelOverride);

// 终端裸跑（无管道、无文件参数）会无限等 stdin：直接给提示而不是挂起。
if (source === '-' && process.stdin.isTTY) {
  log.error('no input (stdin is a terminal). Give a file, a URL, or pipe HTML via stdin. See --help.');
  process.exit(2);
}

try {
  const startedAt = Date.now();
  const out = await runExtract(source, mode, { extractor, attrs, format, pruneEmpty, textMax, allowEmpty, ...(proxy === undefined ? {} : { proxy }), ...(render ? { render } : {}), ...(renderTimeoutMs === undefined ? {} : { renderTimeoutMs }), ...(headful ? { headful: true } : {}), ...(chromeBin === undefined ? {} : { chromeBin }), ...(pythonBin === undefined ? {} : { pythonBin }) });
  const total = `total ${fmtMs(Date.now() - startedAt)}`;
  if (output) {
    // 与 stdout 分支同口径：结果已以换行结尾时不再补，避免落盘文件尾部多出空行。
    await writeFile(output, out.endsWith('\n') ? out : out + '\n', 'utf8');
    log.info('write', `${output} ${fmtBytes(Buffer.byteLength(out, 'utf8'))} (${total})`);
  } else {
    process.stdout.write(out + (out.endsWith('\n') ? '' : '\n'));
    log.info('write', `stdout ${fmtBytes(Buffer.byteLength(out, 'utf8'))} (${total})`);
  }
} catch (err) {
  log.error(err.message);
  // 不用 process.exit(1)：Windows 上静态抓取失败后 undici 句柄仍在收尾，
  // 立刻 exit 会在管道 stdout/stderr 写入未落定时触发 libuv 断言
  // （Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), src\win\async.c），
  // 进程 abort 成 0xC0000409 而不是约定的退出码 1。
  // 置 exitCode 让事件循环自然退出，退出码语义不变。
  process.exitCode = 1;
}
