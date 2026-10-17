#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { ATTR_POLICIES, EXTRACTORS, MODES, runExtract } from './extract.js';

const HELP = `htmlmini - strip CSS/JS from HTML, keep the core as Markdown (token-efficient for LLMs)

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
  -j, --json       output JSON {title, used, requested, content, stats{reductionPct}, meta?}
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
  --proxy <url>    proxy override for URL fetch: http(s) URL, or "direct" to
                   bypass env proxy (default follows HTTP_PROXY/HTTPS_PROXY/NO_PROXY)
  --noproxy        force direct connection, ignoring env proxy
  --render         on static 403/5xx, fall back to browser rendering, then extract.
                   Chain: save_page (needs its Python env) -> system Chrome
                   headless dump-dom (zero-dep) -> friendly error.
                   404/timeout/network errors still throw without rendering
  --headful        show the browser window during fallback rendering
                   (implies --render; only supported by the save_page path,
                   for first-time manual verification)
  --render-timeout-ms <ms>
                   timeout for the fallback browser render (default 300000;
                   chrome dump-dom is capped at 120000)
  --chrome-bin <path>
                   explicit Chrome/Chromium binary for the zero-dep chrome
                   fallback (default auto-detects: PATH, common paths,
                   Playwright browser cache; or HTMLMINI_CHROME_BIN)
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
  -o, --output <f> write to file instead of stdout
  -h, --help       show this help

EXAMPLES
  htmlmini page.html                       # -> markdown to stdout
  htmlmini page.html --json                # -> metadata + extractor + savings %
  htmlmini 报表面板.html -u                 # -> force UI inventory
  htmlmini page.html --mode html           # -> cleaned HTML (structure kept, scripts/styles/attrs gone)
  htmlmini page.html --mode html --attrs none
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
    console.error(`htmlmini: unknown shell "${shell}" (use: bash | powershell)`);
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
let attrs = 'semantic';

for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '-h' || a === '--help') {
    process.stdout.write(HELP);
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
      console.error('htmlmini: --output needs a file argument');
      process.exit(2);
    }
  } else if (a === '--mode' || a === '--extractor' || a === '--attrs' || a === '--completion' || a === '--proxy' || a === '--chrome-bin') {
    const v = argv[++i];
    if (!v) {
      console.error(`htmlmini: ${a} needs a value`);
      process.exit(2);
    }
    if (a === '--mode') mode = v;
    else if (a === '--extractor') extractor = v;
    else if (a === '--attrs') attrs = v;
    else if (a === '--proxy') proxy = v;
    else if (a === '--chrome-bin') chromeBin = v;
    else await printCompletion(v);
  } else if (a === '--noproxy') {
    proxy = 'direct';
  } else if (a === '--render') {
    render = true;
  } else if (a === '--headful') {
    headful = true;
    render = true;
  } else if (a === '--render-timeout-ms') {
    const v = argv[++i];
    renderTimeoutMs = Number(v);
    if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
      console.error(`htmlmini: --render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
      process.exit(2);
    }
  } else if (a.startsWith('--mode=') || a.startsWith('--extractor=') || a.startsWith('--attrs=') || a.startsWith('--output=') || a.startsWith('--completion=') || a.startsWith('--proxy=') || a.startsWith('--chrome-bin=') || a.startsWith('--render-timeout-ms=')) {
    const [k, v] = splitEq(a);
    if (k === '--mode') mode = v;
    else if (k === '--extractor') extractor = v;
    else if (k === '--attrs') attrs = v;
    else if (k === '--output') output = v;
    else if (k === '--proxy') proxy = v;
    else if (k === '--chrome-bin') chromeBin = v;
    else if (k === '--render-timeout-ms') {
      renderTimeoutMs = Number(v);
      if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
        console.error(`htmlmini: --render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
        process.exit(2);
      }
    } else await printCompletion(v);
  } else if (MODE_FLAGS[a]) {
    mode = MODE_FLAGS[a];
  } else if (a === '-' || !a.startsWith('-')) {
    source = a;
  } else {
    console.error(`htmlmini: unknown option "${a}" (see --help)`);
    process.exit(2);
  }
}

if (!MODES.includes(mode)) {
  console.error(`htmlmini: unknown mode "${mode}" (see --list-modes)`);
  process.exit(2);
}
if (!EXTRACTORS.includes(extractor)) {
  console.error(`htmlmini: unknown extractor "${extractor}" (see --list-extractors)`);
  process.exit(2);
}
if (!ATTR_POLICIES.includes(attrs)) {
  console.error(`htmlmini: unknown --attrs policy "${attrs}" (use: ${ATTR_POLICIES.join(' | ')})`);
  process.exit(2);
}

// 终端裸跑（无管道、无文件参数）会无限等 stdin：直接给提示而不是挂起。
if (source === '-' && process.stdin.isTTY) {
  console.error('htmlmini: no input (stdin is a terminal). Give a file, a URL, or pipe HTML via stdin. See --help.');
  process.exit(2);
}

try {
  const out = await runExtract(source, mode, { extractor, attrs, ...(proxy === undefined ? {} : { proxy }), ...(render ? { render: true } : {}), ...(renderTimeoutMs === undefined ? {} : { renderTimeoutMs }), ...(headful ? { headful: true } : {}), ...(chromeBin === undefined ? {} : { chromeBin }) });
  if (output) {
    await writeFile(output, out + '\n', 'utf8');
    console.error(`htmlmini: wrote ${output}`);
  } else {
    process.stdout.write(out + (out.endsWith('\n') ? '' : '\n'));
  }
} catch (err) {
  console.error(`htmlmini: ${err.message}`);
  process.exit(1);
}
