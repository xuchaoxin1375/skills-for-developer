import { readFile, readdir, unlink } from 'node:fs/promises';
import { existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve as resolvePath } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';
import { promisify } from 'node:util';
import { parseHTML } from 'linkedom';
import { Defuddle } from 'defuddle/node';
import { ProxyAgent } from 'undici';
import { fmtBytes, fmtMs, log } from './log.js';

const execFileAsync = promisify(execFile);

export const MODES = ['markdown', 'skeleton', 'text', 'json', 'title', 'ui', 'html'];
export const EXTRACTORS = ['auto', 'defuddle', 'trafilatura', 'semantic', 'ui', 'sanitize', 'passthrough'];
/** html 模式的属性策略：none 清空全部属性 | semantic（默认）保留语义属性 | all 保留全部属性。 */
export const ATTR_POLICIES = ['none', 'semantic', 'all'];
/** html 模式的排版策略：raw 原样（保留源码缩进空白） | compact（默认）压掉缩进噪声 | pretty 重新缩进。 */
export const FORMAT_POLICIES = ['raw', 'compact', 'pretty'];

export const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15 htmlmini/0.3';

const MIN_ARTICLE_CHARS = 50;
const UI_SWITCH_CHARS = 300;
const TRAFILATURA_TIMEOUT_MS = 15000;
// 远程抓取超时：之前无超时，黑洞主机可无限挂起。默认 30s，测试可经 timeoutMs 覆盖。
export const FETCH_TIMEOUT_MS = 30000;

// UI/文本清单的截断上限：保证输出 token 可控。
const CAP = {
  headings: 100,
  fields: 100,
  buttons: 100,
  tables: 20,
  images: 30,
  links: 30,
  texts: 200,
};

export function decodeHtml(buffer) {
  const hasBom = buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf;
  try {
    const text = buffer.toString('utf8');
    if (hasBom) return text.slice(1);
    if (!text.includes('\ufffd')) return text;
  } catch {
    // fall through to GBK attempt
  }
  try {
    return new TextDecoder('gbk').decode(buffer);
  } catch {
    return buffer.toString('utf8');
  }
}

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks)));
    process.stdin.on('error', reject);
  });
}

// ---- 远程抓取：代理选路、浏览器头重试与挑战识别 ----
// htmlmini 只做静态抓取：默认跟随任务/宿主的 HTTP(S)_PROXY 环境代理（NO_PROXY 豁免），
// 可经 proxy 显式覆盖（"direct" 强制直连）；403/5xx 补一次浏览器头重试（同路线、同单次超时），
// 仍失败才按分类抛错，不换出口轮询、不判源站死（选路决策归 network-access，渲染归 resilient-browser-fetch）。

const BROWSER_HEADERS = {
  accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'accept-language': 'en-GB,en;q=0.9',
  'upgrade-insecure-requests': '1',
  'sec-fetch-dest': 'document',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-site': 'none',
  'sec-fetch-user': '?1',
};

/** NO_PROXY 匹配：`*`、精确主机、`example.com` 兼配其子域；忽略大小写与端口。 */
export function hostBypassed(hostname, noProxy) {
  const host = String(hostname || '').toLowerCase();
  for (const raw of String(noProxy || '').split(/[,\s]+/)) {
    const e = raw.trim().toLowerCase().replace(/:\d+$/, '');
    if (!e) continue;
    if (e === '*') return true;
    const domain = e.startsWith('.') ? e.slice(1) : e;
    if (host === domain || host.endsWith(`.${domain}`)) return true;
  }
  return false;
}

/**
 * 选出本次抓取的代理（纯函数，便于测试）。
 * proxy 省略走环境（https 用 HTTPS_PROXY，否则 HTTP_PROXY，皆无用 ALL_PROXY）；
 * proxy 为 "direct" 强制直连；proxy 为 URL 则显式覆盖并校验协议。
 */
export function resolveProxy(target, opts = {}) {
  return proxyOrigin(target, opts).url;
}

/**
 * 与 resolveProxy 同一判据，但额外说明"代理是谁给的"，供日志回答"代理到底生效没"。
 * origin：flag（--proxy 显式）| env:HTTPS_PROXY / env:HTTP_PROXY / env:ALL_PROXY |
 *         noproxy（NO_PROXY 命中，本题按直连）| direct（--noproxy）| none（未配置）
 */
export function proxyOrigin(target, { proxy, env = process.env } = {}) {
  if (proxy === 'direct') return { url: null, origin: 'direct' };
  if (typeof proxy === 'string' && proxy) {
    if (!/^https?:\/\//i.test(proxy)) throw new Error(`proxy 须是 http(s) URL 或 "direct"（实得 ${proxy}）`);
    return { url: proxy, origin: 'flag' };
  }
  let u;
  try {
    u = new URL(target);
  } catch {
    return { url: null, origin: 'none' };
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return { url: null, origin: 'none' };
  if (hostBypassed(u.hostname, env.NO_PROXY ?? env.no_proxy ?? '')) return { url: null, origin: 'noproxy' };
  const keys = u.protocol === 'https:'
    ? ['HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'all_proxy']
    : ['HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'];
  for (const k of keys) {
    const v = (env[k] ?? '').trim();
    if (v) return { url: v, origin: `env:${k}` };
  }
  return { url: null, origin: 'none' };
}

/** 代理 URL 脱敏：只留协议与主机，不回显凭据与路径。 */
export function maskProxy(proxyUrl) {
  try {
    const u = new URL(proxyUrl);
    return `${u.protocol}//${u.host}`;
  } catch {
    return '(invalid proxy)';
  }
}

/**
 * 日志用的一行代理说明，回答"这次到底走没走代理、是谁给的"：
 * `http://127.0.0.1:7890 (HTTPS_PROXY)` / `direct (NO_PROXY)` / `direct (--noproxy)` / `none`。
 * 凭据经 maskProxy 脱敏；--proxy 非法时给 invalid 而不是把异常抛进日志路径。
 */
function describeProxy(target, proxy) {
  let info;
  try {
    info = proxyOrigin(target, { proxy });
  } catch (e) {
    return `invalid (${e.message})`;
  }
  const { url, origin } = info;
  if (origin === 'none') return 'none';
  const from = origin === 'flag' ? '--proxy' : origin === 'noproxy' ? 'NO_PROXY' : origin === 'direct' ? '--noproxy' : origin.replace(/^env:/, '');
  return url ? `${maskProxy(url)} (${from})` : `direct (${from})`;
}

const proxyAgentCache = new Map();
function proxyDispatcher(proxyUrl) {
  let d = proxyAgentCache.get(proxyUrl);
  if (!d) {
    d = new ProxyAgent(proxyUrl);
    proxyAgentCache.set(proxyUrl, d);
  }
  return d;
}

/** 挑战信号（只看最终响应头，不读正文）：命中即按挑战页指引，不判源站死。 */
export function challengeSignals(headers) {
  const sigs = [];
  const get = (n) => headers?.get?.(n) ?? '';
  if (/sct=|cf_clearance=|__cf_bm|cf-chl/i.test(get('set-cookie'))) sigs.push('challenge cookie');
  if (/challenge/i.test(get('cf-mitigated'))) sigs.push('cf-mitigated: challenge');
  if (/challenge|_sc\/|_sec\/|captcha|turnstile/i.test(get('location'))) sigs.push('challenge redirect');
  if (/noindex/i.test(get('x-robots-tag')) && /cloudflare/i.test(get('server'))) sigs.push('cloudflare noindex');
  return sigs;
}

function failureHint(res) {
  const status = res.status;
  if (status === 429) {
    return '; rate-limited: honor Retry-After/cooldown, do not bypass by switching egress or reader';
  }
  if (status === 403) {
    const sigs = challengeSignals(res.headers);
    if (sigs.length) {
      return `; challenge suspected (${sigs.join(', ')}): static fetch cannot solve JS/cookie challenges – render via resilient-browser-fetch save_page (same proxy), then extract the saved file with htmlmini_extract_file`;
    }
  }
  if (status === 403 || (status >= 500 && status <= 599)) {
    return '; static fetch only (minimal + browser headers both tried on 403/5xx): verify route via network-access dual-route, TLS-level disguise via curl_cffi, or render challenge pages via resilient-browser-fetch save_page then extract the saved file';
  }
  return '';
}

async function fetchOnce(source, { headers, timeoutMs, dispatcher }) {
  const init = { headers, redirect: 'follow', signal: AbortSignal.timeout(timeoutMs) };
  if (dispatcher) init.dispatcher = dispatcher;
  return fetch(source, init);
}

export async function readSource(source, { timeoutMs = FETCH_TIMEOUT_MS, proxy } = {}) {
  if (source === '-' || source == null) {
    return { html: decodeHtml(await readStdin()), source: 'stdin', contentType: null };
  }
  if (/^https?:\/\//i.test(source)) {
    const proxyUrl = resolveProxy(source, { proxy });
    const via = proxyUrl ? ` via proxy ${maskProxy(proxyUrl)}` : '';
    let dispatcher = null;
    if (proxyUrl) {
      try {
        dispatcher = proxyDispatcher(proxyUrl);
      } catch (e) {
        throw new Error(`unusable proxy ${maskProxy(proxyUrl)} for ${source}: ${e.message}`);
      }
    }
    const doFetch = (extra) =>
      fetchOnce(source, {
        headers: { 'user-agent': DEFAULT_UA, 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8', ...extra },
        timeoutMs,
        dispatcher,
      });
    const fail = (e) => {
      if (e && e.name === 'TimeoutError') throw new Error(`fetch timeout after ${timeoutMs}ms: ${source}${via}`);
      if (proxyUrl) throw new Error(`${e.message} (via proxy ${maskProxy(proxyUrl)} for ${source})`);
      throw e;
    };
    let res;
    try {
      res = await doFetch();
    } catch (e) {
      fail(e);
    }
    let firstStatus = 0;
    if (res.status === 403 || (res.status >= 500 && res.status <= 599)) {
      firstStatus = res.status;
      try {
        res = await doFetch(BROWSER_HEADERS);
      } catch (e) {
        fail(e);
      }
    }
    if (!res.ok) {
      const initial = firstStatus && firstStatus !== res.status ? ` (initial ${firstStatus} with minimal headers)` : '';
      const err = new Error(`HTTP ${res.status} fetching ${source}${initial}${via}${failureHint(res)}`);
      err.statusCode = res.status;
      throw err;
    }
    const contentType = res.headers.get('content-type');
    return { html: decodeHtml(Buffer.from(await res.arrayBuffer())), source, contentType };
  }
  return { html: decodeHtml(await readFile(source)), source, contentType: guessContentTypeFromPath(source) };
}

// ---- 按需浏览器渲染（显式 opt-in：--render / render:true）----
// 静态抓取报 403/5xx 才回退到浏览器（404/超时/断网直接抛，不烧浏览器时间）。
// 渲染仍由 resilient-browser-fetch 的 save_page 执行（同代理），本文件只负责调度和提取。
export const RENDER_TIMEOUT_MS = 300_000;
const RENDER_SCRIPT_ENV = 'HTMLMINI_RENDER_SCRIPT';

function findRenderScript() {
  const override = (process.env[RENDER_SCRIPT_ENV] ?? '').trim();
  if (override) {
    if (!existsSync(override)) throw new Error(`render requested but renderer not found: ${override} (${RENDER_SCRIPT_ENV})`);
    return override;
  }
  const sibling = resolvePath(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    '..',
    'resilient-browser-fetch',
    'scripts',
    'example_save_page.py',
  );
  if (existsSync(sibling)) return sibling;
  throw new Error(
    'render requested but resilient-browser-fetch renderer not found next to htmlmini; install it per its SKILL references/installation.md, or set HTMLMINI_RENDER_SCRIPT to a compatible save_page script',
  );
}

const PYTHON_BIN_ENV = 'HTMLMINI_PYTHON';
const ENV_SCAN_ENV = 'HTMLMINI_ENV_SCAN';              // '0' 关闭自动扫描
const ENV_SCAN_SCRIPT_ENV = 'HTMLMINI_ENV_SCAN_SCRIPT'; // 测试/自备: 覆盖 check_environment.py 路径

/** 显式指定的解释器：--python-bin 优先，其次 HTMLMINI_PYTHON；"auto" 表示扫描后自动选择。 */
export function pythonBinOverride(pythonBin) {
  const explicit = String(pythonBin ?? '').trim() || (process.env[PYTHON_BIN_ENV] ?? '').trim();
  return explicit || null;
}

function findEnvScanScript() {
  const override = (process.env[ENV_SCAN_SCRIPT_ENV] ?? '').trim();
  if (override) return existsSync(override) ? override : null;
  const sibling = resolvePath(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    '..',
    'resilient-browser-fetch',
    'scripts',
    'check_environment.py',
  );
  return existsSync(sibling) ? sibling : null;
}

/**
 * 扫描本机哪个解释器具备所需层（借 resilient-browser-fetch 的 check_environment.py --list-envs）。
 * 只在需要时调用，结果按进程缓存；任何失败都返回 null，绝不打断主流程。
 */
export async function findCapablePython(required = ['playwright']) {
  if ((process.env[ENV_SCAN_ENV] ?? '').trim() === '0') return null;
  const script = findEnvScanScript();
  if (!script) return null;
  if (envScanCache !== undefined) return envScanCache;
  let runner;
  try {
    runner = await findDefaultPython(); // 用 PATH 上的解释器跑扫描；它只要能跑标准库即可
    if (!runner) throw new Error('no python on PATH');
  } catch {
    envScanCache = null;
    return null;
  }
  const program = [
    'import json, sys',
    'sys.path.insert(0, sys.argv[1])',
    'import check_environment as ce',
    `required = tuple(${JSON.stringify(required)})`,
    'envs = ce.scan_environments(required, sys.argv[1])',
    'usable = [e for e in envs if e.get("ok") and not e.get("satisfies")]',
    'print(json.dumps({"recommended": usable[0]["path"] if usable else None,',
    '                  "engines": usable[0]["engines"] if usable else [],',
    '                  "manager": usable[0].get("manager") if usable else None},',
    '                 ensure_ascii=False))',
  ].join('\n');
  try {
    const { stdout } = await execFileAsync(
      runner,
      ['-X', 'utf8', '-c', program, dirname(script)],
      { timeout: 120_000, windowsHide: true },
    );
    const parsed = JSON.parse(String(stdout).trim().split('\n').pop() || '{}');
    envScanCache = parsed && parsed.recommended ? parsed : null;
  } catch (e) {
    log.debug('render', `解释器环境扫描失败，忽略: ${e.message}`);
    envScanCache = null;
  }
  return envScanCache;
}

let envScanCache;

/** 清空解释器扫描缓存（环境变量变化或测试需要重新扫描时用）。 */
export function resetEnvScanCache() {
  envScanCache = undefined;
}

async function findDefaultPython() {
  const cands = process.platform === 'win32' ? ['python', 'python3'] : ['python3', 'python'];
  for (const bin of cands) {
    try {
      await execFileAsync(bin, ['--version'], { timeout: 10_000, windowsHide: true });
      return bin;
    } catch {
      // 换下一个候选解释器
    }
  }
  return null;
}

export async function findPython({ pythonBin } = {}) {
  const explicit = pythonBinOverride(pythonBin);
  if (explicit === 'auto') {
    const found = await findCapablePython(['playwright']);
    if (!found) {
      throw new Error(
        `${PYTHON_BIN_ENV}=auto 扫描后仍未找到具备层 >= 1 引擎的解释器；` +
          '请按 resilient-browser-fetch references/installation.md 安装 playwright/scrapling，' +
          '或用 ' + PYTHON_BIN_ENV + ' / --python-bin 指定具体解释器',
      );
    }
    log.info('render', `解释器自动选择: ${found.recommended} (${found.manager ?? '未知管理方式'}; 引擎: ${(found.engines ?? []).join(', ') || '无'})`);
    return found.recommended;
  }
  if (explicit) {
    // 显式指定就不做隐式回退：指错了要立刻知道，而不是悄悄换个解释器。
    try {
      await execFileAsync(explicit, ['--version'], { timeout: 10_000, windowsHide: true });
    } catch (e) {
      throw new Error(`--python-bin/${PYTHON_BIN_ENV} interpreter is not usable: ${explicit} (${e.message})`);
    }
    return explicit;
  }
  const cands = process.platform === 'win32' ? ['python', 'python3'] : ['python3', 'python'];
  const found = await findDefaultPython();
  if (found) return found;
  throw new Error(
    `render requested but no python found (tried python/python3); install Python 3.10+ to use --render, or point --python-bin / ${PYTHON_BIN_ENV} at the environment that has playwright or scrapling`,
  );
}

let renderSeq = 0;

// ---- 系统 Chrome 直渲（零依赖兼容通路）----
// 不需要 cloak，也不需要 Python：只要本机有普通 Chrome/Chromium，就用
// 无头 --dump-dom 取渲染后源码。已在 britvanlife 这类挑战站验证可用。
// 局限：无头模式不支持人工介入验证；--headful 只能走 save_page 通路。
const CHROME_BIN_ENV = 'HTMLMINI_CHROME_BIN';
const CHROME_EXTRA_ARGS_ENV = 'HTMLMINI_CHROME_EXTRA_ARGS';

export function findChromeBin() {
  const override = (process.env[CHROME_BIN_ENV] ?? '').trim();
  if (override) {
    if (!existsSync(override)) throw new Error(`chrome binary not found: ${override} (${CHROME_BIN_ENV})`);
    return { bin: override, source: 'env' };
  }
  return findChromeAuto();
}

/** 自动探测：PATH → 固定路径 → Playwright 浏览器缓存。返回 {bin, source} 或 null。 */
export function findChromeAuto() {
  const onPath = findOnPathSync(['google-chrome', 'google-chrome-stable', 'chrome', 'chromium', 'chromium-browser']);
  if (onPath) return { bin: onPath, source: 'path' };
  for (const p of fixedChromePaths()) {
    if (existsSync(p)) return { bin: p, source: 'fixed' };
  }
  const pw = pickPlaywrightChrome(playwrightBrowsersRoot(), process.platform);
  if (pw) return { bin: pw, source: 'playwright' };
  return null;
}

function fixedChromePaths() {
  if (process.platform === 'win32') {
    const out = [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    ];
    const pf = process.env['ProgramFiles'];
    if (pf) out.push(join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'));
    return out;
  }
  if (process.platform === 'darwin') return ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
  return ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium'];
}

function findOnPathSync(names) {
  const which = process.platform === 'win32' ? 'where' : 'which';
  for (const n of names) {
    try {
      const out = execFileSync(which, [n], { timeout: 5000, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
      const first = String(out).split(/\r?\n/).map((s) => s.trim()).filter(Boolean)[0];
      if (first && existsSync(first)) return first;
    } catch {
      // 不在 PATH，试下一个
    }
  }
  return null;
}

function playwrightBrowsersRoot() {
  const custom = (process.env['PLAYWRIGHT_BROWSERS_PATH'] ?? '').trim();
  if (custom) return custom;
  if (process.platform === 'win32') {
    const base = process.env['LOCALAPPDATA'] || join(process.env['USERPROFILE'] ?? '', 'AppData', 'Local');
    return join(base, 'ms-playwright');
  }
  if (process.platform === 'darwin') return join(process.env['HOME'] ?? '', 'Library', 'Caches', 'ms-playwright');
  return join(process.env['HOME'] ?? '', '.cache', 'ms-playwright');
}

/**
 * 从 Playwright 浏览器缓存选 Chromium（纯函数，便于测试）。
 * 布局按平台而异，目录名带版本号（chromium-1208）；取版本最大者，
 * 完整版优先，无头 shell 版兜底。
 */
export function pickPlaywrightChrome(root, platform = process.platform) {
  let entries;
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }
  // 新旧布局并存：chrome-win64 取代了 chrome-win，mac/linux 同理；只认旧布局会误报"未发现浏览器"。
  const layout =
    platform === 'win32'
      ? { re: /^chromium-(\d+)$/, full: ['chrome-win64', 'chrome.exe'], legacy: ['chrome-win', 'chrome.exe'], shell: ['chrome-headless-shell-win64', 'chrome-headless-shell.exe'] }
      : platform === 'darwin'
        ? { re: /^chromium-(\d+)$/, full: ['chrome-mac-arm64', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'], legacy: ['chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'], shell: ['chromium_headless_shell', 'chrome-headless-shell'] }
        : { re: /^chromium-(\d+)$/, full: ['chrome-linux64', 'chrome'], legacy: ['chrome-linux', 'chrome'], shell: ['chromium_headless_shell', 'chrome-headless-shell'] };
  const versions = [];
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const m = layout.re.exec(e.name);
    if (m) versions.push({ name: e.name, ver: Number(m[1]) });
  }
  versions.sort((a, b) => b.ver - a.ver);
  for (const v of versions) {
    for (const relative of [layout.full, layout.legacy]) {
      const candidate = join(root, v.name, ...relative);
      if (existsSync(candidate)) return candidate;
    }
  }
  for (const v of versions) {
    const sh = join(root, v.name, ...layout.shell);
    if (existsSync(sh)) return sh;
  }
  return null;
}

function chromeExtraArgs() {
  // 高级/测试钩子：前置透传参数（如用 node 跑桩脚本）。生产一般留空。
  return (process.env[CHROME_EXTRA_ARGS_ENV] ?? '').split(/\s+/).filter(Boolean);
}

export async function runChromeDump(url, { proxy, timeoutMs = 60_000, chromeBin, chromeSource = 'explicit' } = {}) {
  const bin = chromeBin ?? findChromeBin();
  if (!bin) throw new Error('no system Chrome/Chromium found; set HTMLMINI_CHROME_BIN to its path to use chrome rendering');
  const proxyUrl = resolveProxy(url, { proxy });
  const args = [...chromeExtraArgs(), '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars', '--virtual-time-budget=15000'];
  if (proxyUrl) {
    const masked = maskProxy(proxyUrl);
    if (/^https?:\/\/[^/@]+@/.test(proxyUrl)) {
      throw new Error(`chrome --proxy-server cannot carry credentials; use credential-less proxy or save_page path (${masked})`);
    }
    args.push(`--proxy-server=${proxyUrl}`);
  }
  args.push('--dump-dom', url);
  log.info('render', `engine=chrome-dump src=${chromeSource} bin=${bin} [proxy: ${describeProxy(url, proxy)}]`);
  let stdout = '';
  await new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(bin, args, { windowsHide: true });
    } catch (e) {
      reject(new Error(`chrome render failed to start for ${url}: ${e.message}`));
      return;
    }
    let done = false;
    const timer = setTimeout(() => {
      done = true;
      child.kill();
      reject(new Error(`chrome render timed out after ${timeoutMs}ms for ${url}`));
    }, timeoutMs);
    timer.unref?.();
    const decoder = new StringDecoder('utf8');
    let stderrTail = '';
    child.stdout.on('data', (b) => {
      stdout += decoder.write(b);
      if (stdout.length > 32 * 1024 * 1024) {
        if (!done) {
          done = true;
          clearTimeout(timer);
          child.kill();
          reject(new Error(`chrome render output exceeded 32MB for ${url}; page too large for static extraction`));
        }
      }
    });
    child.stderr.on('data', (b) => {
      stderrTail = (stderrTail + decoder.write(b)).slice(-2000);
    });
    child.on('error', (e) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      reject(new Error(`chrome render failed to start for ${url}: ${e.message}`));
    });
    child.on('close', (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`chrome render failed for ${url} (exit ${code ?? '?'}): ${stderrTail}`));
        return;
      }
      resolve();
    });
  });
  const html = stdout.trim();
  if (!html) throw new Error(`chrome render returned empty page for ${url}`);
  log.debug('render', `chrome dump-dom done (${html.length} chars)`);
  return html;
}

export async function renderViaBrowser(url, { proxy, renderTimeoutMs = RENDER_TIMEOUT_MS, headful = false, chromeBin, pythonBin } = {}) {
  const { script, engines, solver, python } = await renderCapability(pythonBin);
  const canSavePage =
    Boolean(script) && (engines === null || engines.some((name) => BROWSER_ENGINES.includes(name)));

  // Chrome 无头 dump-dom 不支持开窗，--headful 只走 save_page 通路。
  let found = null;
  if (!headful) {
    if (chromeBin) {
      if (!existsSync(chromeBin)) throw new Error(`chrome binary not found: ${chromeBin} (--chrome-bin)`);
      found = { bin: chromeBin, source: 'explicit' };
    } else {
      try {
        found = findChromeBin();
      } catch {
        found = null;
      }
    }
  }

  // 有求解引擎、需要开窗、或本机没有 Chrome 时，save_page 更合适；层 1 与 Chrome 同能力时优先零依赖通路。
  if (canSavePage && (solver || headful || !found)) {
    return runSavePage(url, { script, proxy, renderTimeoutMs, headful, pythonBin, python });
  }
  if (found) {
    try {
      return await runChromeDump(url, { proxy, timeoutMs: Math.min(renderTimeoutMs, 120_000), chromeBin: found.bin, chromeSource: found.source });
    } catch (chromeErr) {
      if (!canSavePage) throw chromeErr;
      // 零依赖通路崩了（进程退出码异常、超时等）时，同能力的 save_page 值得再试一次。
      log.info('render', `chrome 通路失败，改用 save_page 重试: ${chromeErr.message}`);
      try {
        return await runSavePage(url, { script, proxy, renderTimeoutMs, headful, pythonBin, python });
      } catch (saveErr) {
        throw new Error(`${chromeErr.message}; save_page 回退也失败: ${saveErr.message}`);
      }
    }
  }
  if (canSavePage) return runSavePage(url, { script, proxy, renderTimeoutMs, headful, pythonBin, python });
  const alternative = await findCapablePython(['playwright']).catch(() => null);
  if (headful) {
    throw new Error(
      '--headful needs the save_page renderer for manual verification, but no browser-capable engine is available here (layer >= 1: playwright/patchright, scrapling, or cloak-cdp); install per resilient-browser-fetch references/installation.md, then retry'
      + pythonHint(python, alternative),
    );
  }
  throw new Error(
    'render requested but neither save_page (layer >= 1: playwright/patchright, scrapling, or cloak-cdp) nor system Chrome/Chromium (PATH, common paths, Playwright cache) is available; install per resilient-browser-fetch references/installation.md, or specify one with --chrome-bin / HTMLMINI_CHROME_BIN'
    + pythonHint(python, alternative),
  );
}

/** 渲染通路不可用时提示实际用到的解释器，以及怎么换到装了依赖的环境。 */
function pythonHint(python, alternative) {
  const probed = python ? ` (probed interpreter: ${python})` : ' (no usable python interpreter was found)';
  const suggestion =
    alternative && alternative.recommended && alternative.recommended !== python
      ? `; another interpreter on this machine has it: ${alternative.recommended} (${(alternative.engines ?? []).join(', ') || 'layer >= 1'}) — point --python-bin at it, or set ${PYTHON_BIN_ENV}=auto`
      : '';
  return `${probed}; if the engines live in another environment (conda/venv), point --python-bin or ${PYTHON_BIN_ENV} at it, or list candidates with resilient-browser-fetch check_environment.py --list-envs${suggestion}`;
}


// save_page 可用性探测：从不抛错。判定口径是"层 ≥1 有可用引擎"（playwright/scrapling/cloak-cdp），
// 不再要求必须装 scrapling；静态抓取仍由本模块自己完成。
// 但层 1 与零依赖 Chrome 直渲能力重叠（都只是渲染、都不求解挑战），
// 因此只在下列情况优先 save_page：有求解引擎（层 2/3）、需要 --headful、或本机没有 Chrome。
const BROWSER_ENGINES = ['playwright', 'scrapling', 'cloak-cdp'];
const SOLVER_ENGINES = ['scrapling', 'cloak-cdp'];
const RENDER_ENGINES_ENV = 'HTMLMINI_RENDER_ENGINES';

async function probeRenderEngines(python, script) {
  // 测试/高级钩子：直接声明可用引擎，跳过 python 探测。
  const declared = (process.env[RENDER_ENGINES_ENV] ?? '').trim();
  if (declared) return declared.split(',').map((s) => s.trim()).filter(Boolean);
  const program = [
    'import json, sys',
    'sys.path.insert(0, sys.argv[1])',
    'import resilient_fetch as rf',
    'print(json.dumps(list(rf.available_engines())))',
  ].join('\n');
  try {
    const { stdout } = await execFileAsync(python, ['-X', 'utf8', '-c', program, dirname(script)], {
      timeout: 60_000,
      windowsHide: true,
    });
    const parsed = JSON.parse(String(stdout).trim() || '[]');
    return Array.isArray(parsed) ? parsed.map((s) => String(s)) : null;
  } catch (e) {
    log.debug('render', `引擎探测失败，回退到 scrapling 导入探测: ${e.message}`);
    return null;
  }
}

/**
 * 汇总 save_page 通路的可用性：engines 为 null 表示"按旧口径信任脚本"（显式覆盖或旧版 skill）。
 * python 为实际探测用的解释器，供调用方在失败信息里指名，或提示改用 --python-bin。
 */
async function renderCapability(pythonBin) {
  let script;
  try {
    script = findRenderScript();
  } catch {
    return { script: null, engines: null, solver: false, python: null };
  }
  // 显式覆盖（测试桩/自备渲染器）视为可用且具求解能力，不探依赖。
  if ((process.env[RENDER_SCRIPT_ENV] ?? '').trim()) return { script, engines: null, solver: true, python: null };
  let python;
  try {
    python = await findPython({ pythonBin });
  } catch (e) {
    // 默认探测失败只当作"没有 python"；显式指定的解释器不可用是配置错误，必须让用户看到。
    if (pythonBinOverride(pythonBin)) throw e;
    return { script: null, engines: null, solver: false, python: null };
  }
  const engines = await probeRenderEngines(python, script);
  if (engines === null) {
    // 兼容旧版 resilient-browser-fetch（无 available_engines）或探测整体失败：
    // 退回"能否 import scrapling"的旧口径，宁可不判死。
    try {
      await execFileAsync(python, ['-X', 'utf8', '-c', 'import scrapling'], { timeout: 60_000, windowsHide: true });
      return { script, engines: ['scrapling'], solver: true, python };
    } catch {
      return { script: null, engines: null, solver: false, python };
    }
  }
  log.debug('render', `save_page 可用引擎: ${engines.join(', ') || '无'} (python: ${python})`);
  return { script, engines, solver: engines.some((name) => SOLVER_ENGINES.includes(name)), python };
}

/** save_page 是否有层 ≥1 的可用引擎；供测试与调用方判断渲染通路。 */
export async function savePageUsable(pythonBin) {
  const { script, engines } = await renderCapability(pythonBin);
  if (!script) return null;
  if (engines === null || engines.some((name) => BROWSER_ENGINES.includes(name))) return script;
  return null;
}


async function runSavePage(url, { script, proxy, renderTimeoutMs, headful, pythonBin, python }) {
  const interpreter = python ?? (await findPython({ pythonBin }));
  const proxyUrl = resolveProxy(url, { proxy });
  const out = join(tmpdir(), `htmlmini-render-${process.pid}-${Date.now()}-${renderSeq++}.html`);
  // -X utf8 + PYTHONUTF8：子进程日志强制 UTF-8 输出，本侧按 UTF-8 增量解码、
  // 逐行透传（Windows 控制台查看侧按 powershell-pitfalls 的 UTF-8 模板设置）。
  const args = ['-X', 'utf8', script, url, '--out', out, '--engine', 'auto', '--timeout-ms', String(renderTimeoutMs)];
  if (proxyUrl) args.push('--proxy', proxyUrl);
  else args.push('--discover-proxy');
  if (headful) args.push('--headful');
  const proxyNote = describeProxy(url, proxy);
  log.info('render', `engine=save-page${headful ? ' headful' : ''} [python: ${interpreter}] [proxy: ${proxyNote === 'none' ? 'none, render script discovers its own' : proxyNote}]`);
  const tail = [];
  let tailSize = 0;
  const TAIL_CAP = 256 * 1024;
  const remember = (line) => {
    tail.push(line);
    tailSize += line.length + 1;
    while (tailSize > TAIL_CAP && tail.length > 1) tailSize -= tail.shift().length + 1;
  };
  const limit = renderTimeoutMs + 60_000;
  try {
    await new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(interpreter, args, {
        cwd: dirname(script),
        env: { ...process.env, PYTHONUTF8: '1' },
        windowsHide: true,
      });
    } catch (e) {
      reject(new Error(`browser render failed to start for ${url}: ${e.message}`));
      return;
    }
    let done = false;
    const timer = setTimeout(() => {
      done = true;
      child.kill();
      reject(new Error(`browser render timed out after ${limit}ms for ${url}`));
    }, limit);
    timer.unref?.();
    const decoder = new StringDecoder('utf8');
    let rest = '';
    const emit = (buf) => {
      const parts = (rest + decoder.write(buf)).split('\n');
      rest = parts.pop();
      for (const line of parts) {
        remember(line);
        log.info('render', line);
      }
    };
    child.stderr.on('data', emit);
    child.on('error', (e) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      reject(new Error(`browser render failed to start for ${url}: ${e.message}`));
    });
    child.on('close', (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (rest) {
        remember(rest);
        log.info('render', rest);
        rest = '';
      }
      if (code !== 0) {
        reject(new Error(`browser render failed for ${url} (exit ${code ?? '?'}): ${tail.join('\n').slice(-2000)}`));
        return;
      }
      resolve();
    });
  });
    const html = decodeHtml(await readFile(out));
    if (!html.trim()) throw new Error(`browser render returned empty page for ${url}`);
    return html;
  } finally {
    // save_page 成功/失败都会在 out 旁落文件（正文、.meta.json、.attempts.json、
    // .<engine>.blocked.html）；basename 唯一，按前缀全清，不留残留。
    // finally 包住 spawn（失败早抛也清），读文件在 finally 之前（先读后删）。
    await cleanupRenderArtifacts(out);
  }
}

/** 清理某次渲染落到临时目录的全部产物（正文、meta 与诊断文件）。 */
export async function cleanupRenderArtifacts(out) {
  const dir = dirname(out);
  const base = out.split(/[\\/]/).pop();
  let entries;
  try {
    entries = await readdir(dir);
  } catch {
    return;
  }
  await Promise.all(
    entries
      .filter((e) => e === base || e.startsWith(`${base}.`))
      .map((e) => unlink(join(dir, e)).catch(() => {})),
  );
}

export function isRenderableError(e) {
  const s = e?.statusCode;
  return s === 403 || (s >= 500 && s <= 599);
}

export async function readWithRender(
  source,
  { timeoutMs = FETCH_TIMEOUT_MS, proxy, render = false, renderTimeoutMs, headful = false, chromeBin, pythonBin } = {},
) {
  const remote = /^https?:\/\//i.test(source ?? '');
  const tRead = Date.now();
  // 抓取前先报：网络与浏览器渲染都是长等待，不能静默；[proxy: …] 说明实际路由与来源。
  // 放在这一层而不是 runExtract，CLI 与 MCP（handleSource 直接调本函数）才都有进度。
  if (remote) log.info('read', `fetching ${source} [proxy: ${describeProxy(source, proxy)}]`);
  const done = (r) => {
    log.info('read', `${r.source ?? source} ${fmtBytes(r.html.length)} in ${fmtMs(Date.now() - tRead)}${r.rendered ? ' via browser render' : ''}`);
    log.debug('read', `source=${r.source ?? source} contentType=${r.contentType ?? 'unknown'}${remote ? ` render=${render ? 'allowed' : 'static-only'} proxy=${describeProxy(source, proxy)}` : ''}`);
    return r;
  };
  if (!remote || !render) {
    return done(await readSource(source, { timeoutMs, proxy }));
  }
  try {
    return done(await readSource(source, { timeoutMs, proxy }));
  } catch (e) {
    if (!isRenderableError(e)) throw e;
    const html = await renderViaBrowser(
      source,
      {
        proxy,
        ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
        ...(headful ? { headful: true } : {}),
        ...(chromeBin == null ? {} : { chromeBin }),
        ...(pythonBin == null ? {} : { pythonBin }),
      },
    );
    return done({ html, source, contentType: 'text/html', rendered: true });
  }
}

/** 按文件扩展名猜内容类型（仅提示作用，最终由正文启发式裁决）。 */
export function guessContentTypeFromPath(p) {
  const lower = String(p || '').toLowerCase();
  if (/\.(md|markdown)$/.test(lower)) return 'text/markdown';
  if (/\.txt$/.test(lower)) return 'text/plain';
  if (/\.json$/.test(lower)) return 'application/json';
  if (/\.(html?|xhtml)$/.test(lower)) return 'text/html';
  return null;
}

/**
 * 读取 resilient-browser-fetch `save_page` 产物同目录的 `<html>.meta.json`。
 * 存在则返回 { url, meta }，否则返回 null（静默跳过，不阻塞提取）。
 */
export async function readSiblingMeta(filePath) {
  if (!filePath || filePath === 'stdin' || /^https?:\/\//i.test(filePath)) return null;
  try {
    const raw = await readFile(`${filePath}.meta.json`, 'utf8');
    const meta = JSON.parse(raw);
    const url = meta.url || meta.pageUrl || meta.finalUrl || '';
    return { url, meta };
  } catch {
    return null;
  }
}

function collectText(el) {
  return (el.textContent || '').replace(/\s+/g, ' ').trim();
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

/**
 * 增量去重：完全相同或互相包含时保留较长者（O(n^2) 可接受）。
 * 清单类输出按"去重后"计预算，必须边收边去重：否则页头/页脚里的重复样板先占满额度，
 * 文档顺序靠后的内容（如长页尾部的定价卡）会被整段截断。
 */
function dedupeInsert(unique, t) {
  const i = unique.findIndex((u) => u === t || u.includes(t) || t.includes(u));
  if (i < 0) {
    unique.push(t);
    return;
  }
  if (t.length > unique[i].length) unique[i] = t;
}

/** 去重：输入已截断，语义同 dedupeInsert。 */
function dedupe(items) {
  const unique = [];
  for (const t of items) dedupeInsert(unique, t);
  return unique;
}

/** aria-labelledby 引用的文本拼接。 */
function labelledByText(doc, el) {
  const ref = typeof el.getAttribute === 'function' ? el.getAttribute('aria-labelledby') : null;
  if (!ref) return '';
  return ref
    .split(/\s+/)
    .map((id) => {
      try {
        const t = doc.getElementById(id);
        return t ? collectText(t) : '';
      } catch {
        return '';
      }
    })
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** 表单控件的可访问名称：label[for] > 包裹 label > aria-labelledby > aria-label > placeholder > name/id。 */
function fieldLabel(doc, el) {
  const id = typeof el.getAttribute === 'function' ? el.getAttribute('id') : null;
  if (id) {
    for (const lab of doc.querySelectorAll('label')) {
      if (typeof lab.getAttribute === 'function' && lab.getAttribute('for') === id) {
        const t = collectText(lab);
        if (t) return t;
      }
    }
  }
  let node = el.parentElement;
  for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
    if (node.tagName && node.tagName.toLowerCase() === 'label') {
      const t = collectText(node);
      if (t) return t;
      break;
    }
  }
  const by = labelledByText(doc, el);
  if (by) return by;
  const get = (name) => (typeof el.getAttribute === 'function' ? el.getAttribute(name) : null) || '';
  return get('aria-label') || get('placeholder') || get('name') || (id ? `#${id}` : '');
}

function buttonName(doc, el) {
  const by = labelledByText(doc, el);
  if (by) return by;
  const get = (name) => (typeof el.getAttribute === 'function' ? el.getAttribute(name) : null) || '';
  return collectText(el) || get('aria-label') || get('value') || get('title');
}

/**
 * 保守清洗：只剥非内容元素与表观属性，保留完整 DOM 结构与文本顺序。
 * 与 `ui` 清单的区别：清单是扁平化 + 条数预算（可能截断），清洗是完整结构（token 更高）。
 * - 剥离：脚本/样式/模板/元信息/图标类（含 svg path 数据）与注释
 * - 属性：none 全清（最省 token，丢链接目标与合并单元格）/ semantic 保留语义属性 / all 只去脚本样式
 * - 排版选项：compact 压掉源码缩进空白（默认）/ pruneEmpty 顺带剪掉清洗后变空的容器（非默认）
 */
const SANITIZE_DROP_TAGS = 'script,style,noscript,template,link,meta,base,canvas,svg,path,source,track';
const SANITIZE_KEEP_ATTRS = new Set([
  'href', 'src', 'alt', 'title',
  'colspan', 'rowspan', 'span', 'scope',
  'type', 'value', 'placeholder', 'name', 'for', 'label',
  'checked', 'selected', 'disabled', 'readonly', 'multiple',
  'action', 'method', 'datetime', 'open', 'start', 'lang', 'dir', 'role',
]);

/**
 * 行内级元素白名单（其余按块级处理）。
 * 压缩空白时靠它区分两种情况：块级之间换行只是源码缩进（可删）；
 * 行内元素之间换行在渲染上等于一个空格（必须留一个，否则 "A</b> B" 会粘成 "AB"）。
 */
const INLINE_TAGS = new Set([
  'a', 'abbr', 'audio', 'b', 'bdi', 'bdo', 'br', 'button', 'canvas', 'cite', 'code', 'data',
  'datalist', 'del', 'dfn', 'em', 'embed', 'i', 'iframe', 'img', 'input', 'ins', 'kbd', 'label',
  'map', 'mark', 'meter', 'noscript', 'object', 'output', 'picture', 'progress', 'q', 'rp', 'rt',
  'ruby', 's', 'samp', 'select', 'slot', 'small', 'span', 'strong', 'sub', 'sup', 'svg', 'time',
  'u', 'var', 'video', 'wbr',
]);

/** 内容空白有意义的元素：压缩时整棵子树跳过（缩进/换行属于内容本身）。 */
const WS_PRESERVE_TAGS = new Set(['pre', 'textarea', 'xmp', 'plaintext']);

/**
 * 空元素剪除的豁免表：
 * - void/替换元素：本来就没有子节点
 * - 表格与表单结构：空单元格、空 select 仍承载结构，删了会丢行列表格骨架
 */
const PRUNE_KEEP_TAGS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr',
  'td', 'th', 'tr', 'table', 'thead', 'tbody', 'tfoot', 'colgroup', 'caption',
  'select', 'optgroup', 'option', 'textarea', 'pre', 'iframe', 'canvas', 'video', 'audio',
  'object', 'picture', 'slot', 'template',
]);

function hasAncestorIn(node, tags) {
  for (let p = node.parentNode; p && p.nodeType === 1; p = p.parentNode) {
    if (tags.has((p.tagName || '').toLowerCase())) return true;
  }
  return false;
}

/** 兄弟方向上的第一个“有意义”节点：元素，或非纯空白文本。 */
function neighborNode(node, dir) {
  for (let n = node[dir]; n; n = n[dir]) {
    if (n.nodeType === 1) return n;
    if (n.nodeType === 3 && (n.nodeValue ?? '').trim()) return n;
  }
  return null;
}

function isInlineNode(n) {
  if (!n) return false;
  if (n.nodeType === 3) return true; // 文本本身就是行内内容
  return INLINE_TAGS.has((n.tagName || '').toLowerCase());
}

/**
 * 压缩 DOM 缩进噪声（紧凑排版的前半程，必须在序列化前做）：
 * - 纯空白文本节点：夹在两个行内内容之间压成单个空格，其余（首尾、块级之间）直接删
 * - 非纯空白文本节点：内部连续空白折叠为单空格，并裁掉贴着块级边界的首尾空格
 * 遍历起点是文档节点本身而非 `documentElement`：真源 HTML 常在 doctype 之前、
 * `</html>` 之后带换行，那些文档级空白节点不在 `<html>` 子树里，只走元素会漏掉，
 * 序列化后就成了输出首尾的空行。
 * 不做全局 `>\s+<` 替换——那会把 `</b> <i>` 之间的空格也吃掉，改变渲染结果。
 */
export function compactDom(doc) {
  const texts = [];
  const walk = (node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === 3) texts.push(child);
      else if (child.nodeType === 1) walk(child);
    }
  };
  walk(doc);
  for (const node of texts) {
    if (hasAncestorIn(node, WS_PRESERVE_TAGS)) continue;
    const value = node.nodeValue ?? '';
    if (!value.trim()) {
      if (isInlineNode(neighborNode(node, 'previousSibling')) && isInlineNode(neighborNode(node, 'nextSibling'))) {
        node.nodeValue = ' ';
      } else {
        node.remove();
      }
      continue;
    }
    let text = value.replace(/\s+/g, ' ');
    if (!isInlineNode(neighborNode(node, 'previousSibling'))) text = text.replace(/^\s+/, '');
    if (!isInlineNode(neighborNode(node, 'nextSibling'))) text = text.replace(/\s+$/, '');
    if (text) node.nodeValue = text;
    else node.remove();
  }
  return doc;
}

/**
 * 剪除清洗后变空的容器（`--prune-empty`，非默认）：
 * 自底向上反复扫，直到没有新的空元素；`<div></div>`、空 `<nav>` 是页面体积的大头。
 * 表格/表单/内容空白容器按 PRUNE_KEEP_TAGS 豁免。
 */
export function pruneEmptyElements(doc) {
  const isBlank = (el) =>
    ![...el.childNodes].some((n) => n.nodeType === 1 || (n.nodeType === 3 && (n.nodeValue ?? '').trim()));
  let changed = true;
  while (changed) {
    changed = false;
    for (const el of [...doc.querySelectorAll('*')]) {
      const tag = (el.tagName || '').toLowerCase();
      if (PRUNE_KEEP_TAGS.has(tag) || hasAncestorIn(el, WS_PRESERVE_TAGS)) continue;
      if (!isBlank(el)) continue;
      el.remove();
      changed = true;
    }
  }
  return doc;
}

/**
 * pretty 排版：交给 js-beautify（可选依赖，动态加载；缺失时给安装提示而不是崩）。
 * 入参应是已压缩的 HTML——先压掉源码缩进空白，再重排，不然会把原页面的空行当内容保留。
 */
export async function prettifyHtml(html) {
  let mod;
  try {
    mod = await import('js-beautify');
  } catch {
    throw new Error('--format pretty 需要 js-beautify 依赖：在 skills/htmlmini 目录执行一次安装（pnpm add js-beautify / pnpm install）');
  }
  const beautify = mod.default ?? mod;
  const out = beautify.html(html, {
    indent_size: 2,
    indent_inner_html: true,
    wrap_line_length: 0,
    preserve_newlines: false,
    max_preserve_newlines: 0,
    end_with_newline: false,
    extra_liners: [],
  });
  return out.trim();
}

export function sanitizeHtml(doc, attrs = 'semantic', { compact = false, pruneEmpty = false } = {}) {
  if (!ATTR_POLICIES.includes(attrs)) {
    throw new Error(`unknown attrs policy "${attrs}"（可选: ${ATTR_POLICIES.join(', ')}）`);
  }
  for (const el of doc.querySelectorAll(SANITIZE_DROP_TAGS)) el.remove();
  for (const el of doc.querySelectorAll('*')) {
    for (const node of [...el.childNodes]) {
      if (node.nodeType === 8) node.remove(); // 注释
    }
    if (attrs === 'all') continue;
    for (const attr of [...el.attributes]) {
      if (attrs === 'semantic' && SANITIZE_KEEP_ATTRS.has(attr.name.toLowerCase())) continue;
      el.removeAttribute(attr.name);
    }
  }
  // 剪空壳要在压空白之前：先按“有无实质子节点”判定，`<div>\n</div>` 才不会因为换行文本而漏判。
  if (pruneEmpty) pruneEmptyElements(doc);
  if (compact) compactDom(doc);
  return doc.toString();
}

/**
 * UI 组件清单（v2：按可访问语义重写）。
 * 只认语义标签/ARIA，不再用 class*="btn" 之类正则猜，避免样式类误伤。
 */
export function uiSkeleton(doc) {
  const out = [];
  const title = safeTitle(doc) || '(no title)';
  out.push(`# ${title}`);

  const headings = [...doc.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .map((el) => {
      const level = el.tagName ? el.tagName.toLowerCase() : 'h';
      const t = collectText(el);
      return t ? `${level.toUpperCase()}: ${t}` : '';
    })
    .filter(Boolean)
    .slice(0, CAP.headings);
  if (headings.length) {
    out.push('', '## 标题');
    headings.forEach((h) => out.push(`- ${truncate(h, 140)}`));
  }

  const landmarks = [];
  for (const [sel, name] of [
    ['header', 'header'],
    ['nav', 'nav'],
    ['main', 'main'],
    ['footer', 'footer'],
    ['aside', 'aside'],
    ['form', 'form'],
    ['[role="search"]', 'search'],
  ]) {
    const n = doc.querySelectorAll(sel).length;
    if (n) landmarks.push(`${name}×${n}`);
  }
  if (landmarks.length) {
    out.push('', '## 地标');
    out.push(`- ${landmarks.join(' / ')}`);
  }

  const fields = [];
  for (const el of doc.querySelectorAll('input,select,textarea')) {
    if (fields.length >= CAP.fields) break;
    const tag = el.tagName ? el.tagName.toLowerCase() : '';
    const get = (name) => (typeof el.getAttribute === 'function' ? el.getAttribute(name) : null) || '';
    const type = (get('type') || (tag === 'select' ? 'select' : tag)).toLowerCase();
    if (type === 'hidden') continue;
    const label = fieldLabel(doc, el) || '(未命名)';
    const required = el.hasAttribute && el.hasAttribute('required') ? ' (必填)' : '';
    if (tag === 'select') {
      const opts = [...el.querySelectorAll('option')].map(collectText).filter(Boolean).slice(0, 10);
      fields.push(`[select] ${label}: ${opts.join(' / ') || '(空选项)'}${required}`);
    } else if (type === 'checkbox' || type === 'radio') {
      const checked = el.hasAttribute && el.hasAttribute('checked') ? ' [已选]' : '';
      fields.push(`[${type}] ${label}${checked}${required}`);
    } else {
      const ph = get('placeholder') && get('placeholder') !== label ? `（${get('placeholder')}）` : '';
      fields.push(`[${type || tag}] ${label}${ph}${required}`);
    }
  }
  if (fields.length) {
    out.push('', '## 表单字段');
    dedupe(fields).slice(0, CAP.fields).forEach((f) => out.push(`- ${truncate(f, 160)}`));
  }

  const buttons = [];
  for (const el of doc.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"],input[type="reset"]')) {
    if (buttons.length >= CAP.buttons) break;
    const name = buttonName(doc, el);
    if (name) buttons.push(name);
  }
  // a 仅当显式 role="button" 才算按钮（上面已覆盖），避免导航链接污染。
  const uniqButtons = dedupe(buttons);
  if (uniqButtons.length) {
    out.push('', '## 按钮');
    uniqButtons.slice(0, CAP.buttons).forEach((b) => out.push(`- ${truncate(b, 120)}`));
  }

  const tables = [...doc.querySelectorAll('table')].slice(0, CAP.tables).map((t) => {
    const cap = t.querySelector('caption') ? truncate(collectText(t.querySelector('caption')), 60) : '';
    const heads = [...t.querySelectorAll('th')].map(collectText).filter(Boolean).slice(0, 8);
    const rows = t.querySelectorAll('tr').length;
    let cols = 0;
    for (const tr of t.querySelectorAll('tr')) {
      cols = Math.max(cols, tr.querySelectorAll('th,td').length);
    }
    let sample = '';
    for (const tr of t.querySelectorAll('tr')) {
      const cells = [...tr.querySelectorAll('td')].map((c) => truncate(collectText(c), 40)).filter(Boolean);
      if (cells.length) {
        sample = ` | 首行: ${cells.slice(0, 5).join(' / ')}`;
        break;
      }
    }
    return `${cap ? `《${cap}》` : ''}${heads.length ? heads.join(' | ') : `${rows}行×${cols}列`}${sample}`;
  });
  if (tables.length) {
    out.push('', '## 表格');
    tables.forEach((t) => out.push(`- ${truncate(t, 200)}`));
  }

  const images = [...doc.querySelectorAll('img')]
    .map((img) => (typeof img.getAttribute === 'function' ? img.getAttribute('alt') : '') || '')
    .map((s) => s.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  if (images.length) {
    out.push('', '## 图片');
    dedupe(images).slice(0, CAP.images).forEach((a) => out.push(`- ${truncate(a, 120)}`));
  }

  // 链接预算按去重后计数（页脚导航等重复项不占额度）。
  const links = [];
  for (const a of doc.querySelectorAll('a[href]')) {
    if (links.length >= CAP.links) break;
    if (typeof a.getAttribute === 'function' && a.getAttribute('role') === 'button') continue;
    const t = collectText(a);
    if (!t || t.length > 80) continue;
    const href = truncate(a.getAttribute('href') || '', 80);
    dedupeInsert(links, href && href !== t ? `${t} (${href})` : t);
  }
  if (links.length) {
    out.push('', '## 链接');
    links.slice(0, CAP.links).forEach((l) => out.push(`- ${truncate(l, 160)}`));
  }

  // 文本预算同样按去重后计数：重复样板不吃额度，长页尾部才不会被截断。
  const uniqueTexts = [];
  for (const el of doc.querySelectorAll('p,li,td,th,div,span')) {
    if (uniqueTexts.length >= CAP.texts) break;
    if (el.querySelector('p,li,td,th,div,label,button,select,h1,h2,h3,h4,h5,h6,input,table,a')) continue;
    let node = el.parentElement;
    let interactive = false;
    for (let depth = 0; node && depth < 3; depth++, node = node.parentElement) {
      const tag = node.tagName ? node.tagName.toLowerCase() : '';
      if (tag === 'button' || tag === 'select' || tag === 'option' || tag === 'nav') {
        interactive = true;
        break;
      }
    }
    if (interactive) continue;
    const t = collectText(el);
    if (t.length >= 2 && t.length <= 150 && !/^[0-9\s%.,]+$/.test(t)) dedupeInsert(uniqueTexts, t);
  }
  if (uniqueTexts.length) {
    out.push('', '## 文本');
    uniqueTexts.forEach((t) => out.push(`- ${t}`));
  }
  return out.join('\n');
}

/** 纯 JS 语义回退：取 main/article/[role=main] 候选区的标题与叶子文本流。 */
export function semanticFallback(doc) {
  const root =
    doc.querySelector('main,article,[role="main"]') || doc.querySelector('body') || doc;
  const out = [`# ${safeTitle(doc) || '(no title)'}`];
  const headings = [...root.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .map(collectText)
    .filter(Boolean)
    .slice(0, 50);
  if (headings.length) {
    out.push('', '## 标题');
    headings.forEach((h) => out.push(`- ${truncate(h, 140)}`));
  }
  const texts = [];
  for (const el of root.querySelectorAll('p,li,td,th,div,span')) {
    if (texts.length >= 300) break;
    if (el.querySelector('p,li,td,th,div,button,select,input,table')) continue;
    const t = collectText(el);
    if (t.length >= 2 && t.length <= 300) texts.push(t);
  }
  dedupe(texts).slice(0, 200).forEach((t) => out.push(`- ${t}`));
  return out.join('\n');
}

function parseOnce(html) {
  // 空/纯空白输入 linkedom 会产出无 documentElement 的文档，后续读 title 直接抛：归一化。
  const src = html && html.trim() ? html : '<html><head><title></title></head><body></body></html>';
  return parseHTML(src).document;
}

/** linkedom 的 title getter 在畸形文档上可能抛（如只剩 doctype），统一吞掉。 */
function safeTitle(doc) {
  try {
    return doc.title || '';
  } catch {
    return '';
  }
}

async function extractWithDefuddle(document, url) {
  return await Defuddle(document, url, { markdown: true });
}

const TRAFILATURA_PY = `
import sys
try:
    import trafilatura
except ImportError:
    sys.exit(2)
html = sys.stdin.buffer.read().decode('utf-8', 'replace')
text = trafilatura.extract(html, output_format='txt', include_comments=False)
if not text or not text.strip():
    sys.exit(3)
sys.stdout.write(text)
`;

/**
 * 带 stdin 的子进程调用。Windows 上 execFile 的 `input` 选项在本机会挂起
 * （子进程收不到 EOF；仓库测试里已记录同一现象），所以显式 spawn + write/end。
 * 解析 { code, stdout, stderr }；启动失败（ENOENT 等）或超时后 kill 则 reject。
 */
function runWithStdin(bin, args, input, { timeoutMs, maxBuffer = 32 * 1024 * 1024 } = {}) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(bin, args, { windowsHide: true });
    } catch (e) {
      reject(e);
      return;
    }
    let stdout = '';
    let stderr = '';
    let size = 0;
    let done = false;
    const finish = (fn, v) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      fn(v);
    };
    const timer = setTimeout(() => {
      child.kill();
      const err = new Error(`command timed out after ${timeoutMs}ms: ${bin}`);
      err.timedOut = true;
      finish(reject, err);
    }, timeoutMs);
    timer.unref?.();
    child.stdout.on('data', (d) => {
      size += d.length;
      if (size > maxBuffer) {
        child.kill();
        finish(reject, new Error(`command output exceeded ${maxBuffer} bytes: ${bin}`));
        return;
      }
      stdout += d;
    });
    child.stderr.on('data', (d) => {
      stderr += d;
    });
    child.on('error', (e) => finish(reject, e));
    child.on('close', (code) => finish(resolve, { code, stdout, stderr }));
    // 子进程先退出时 write 会 EPIPE，忽略即可（按 close 的退出码判断成败）。
    child.stdin.on('error', () => {});
    child.stdin.end(input);
  });
}

/**
 * 可选的 Trafilatura 增强：本机有 Python + trafilatura 模块时才生效，
 * 否则静默返回 { ok: false }，调用方继续走下一级回退。
 * 指定了 --python-bin / HTMLMINI_PYTHON 时只试那个解释器（显式即显式）。
 */
export async function tryTrafilatura(html, { pythonBin } = {}) {
  const explicit = pythonBinOverride(pythonBin);
  const bins = explicit ? [explicit] : ['python3', 'python'];
  for (const bin of bins) {
    let res;
    try {
      res = await runWithStdin(bin, ['-c', TRAFILATURA_PY], html, { timeoutMs: TRAFILATURA_TIMEOUT_MS });
    } catch {
      // 启动失败（ENOENT 等）或超时：换下一个候选解释器。
      continue;
    }
    if (res.code === 0) {
      const text = (res.stdout || '').trim();
      return text ? { ok: true, text } : { ok: false };
    }
    // 2 = 缺模块；3 = 抽不出正文。
    if (res.code === 2) return { ok: false, missing: true };
    return { ok: false };
  }
  return { ok: false, missing: true };
}

/** 中英混排字数估计（回退引擎没有 Defuddle 的 wordCount 时用）。 */
function countWords(text) {
  const cjk = (text.match(/[一-鿿぀-ヿ가-힯]/g) || []).length;
  const latin = (text.match(/[A-Za-z0-9_]+/g) || []).length;
  return cjk + latin;
}

function uiSignalCount(html) {
  return (html.match(/<(button|select|label|input|table)\b/gi) || []).length;
}

function isWeakArticle(content, html) {
  if (content.length < MIN_ARTICLE_CHARS) return true;
  return content.length < UI_SWITCH_CHARS && uiSignalCount(html) >= 3;
}

const HTML_TAG_RE =
  /<(html|head|body|div|p|span|a|h1|h2|h3|h4|h5|h6|table|thead|tbody|tr|td|th|ul|ol|li|form|input|select|textarea|button|article|main|section|nav|header|footer|img|figure|figcaption|video|audio|canvas|script|style|link|meta|title)\b/gi;

function hasMarkdownSignals(s) {
  return /^#{1,6}\s+\S/m.test(s) || /```/.test(s) || /^\s*\|.*\|\s*$/m.test(s);
}

/**
 * 非 HTML 启发式：gitee 这类 `Content-Type: text/plain` 直接返回 markdown、
 * 纯文本/JSON 日志等都不该被硬塞进 HTML 解析器。
 * 只认白名单 HTML 标签，避免 markdown 里的 `<skill-name>` 占位符误判。
 */
export function looksLikeHtml(s, contentType) {
  const text = String(s || '');
  const head = text.slice(0, 2000);
  if (/<!doctype\s+html/i.test(head)) return true;
  if (/<html[\s>]/i.test(head)) return true;
  const tags = text.match(HTML_TAG_RE);
  const tagCount = tags ? tags.length : 0;
  // 没有任何白名单标签：一定不是 HTML（扩展名/content-type 说是 html 也不算，
  // 如 curl 把 text/plain 正文存成了 .html 文件）。
  if (tagCount === 0) return false;
  const ct = String(contentType || '').toLowerCase();
  if (ct.includes('text/html') || ct.includes('application/xhtml')) return true;
  // 明确的非 HTML 类型：除非标签多到明显是 HTML，否则透传。
  if (ct.includes('text/markdown') || ct.includes('text/plain') || ct.includes('application/json') || ct.includes('text/csv')) {
    return tagCount >= 5;
  }
  // markdown 信号强（标题/代码块/表格）且标签少：是“讲 HTML 的 markdown”，不是 HTML。
  if (hasMarkdownSignals(text) && tagCount < 5) return false;
  return true;
}

/** 从纯文本/markdown 第一行提标题：优先 `# 标题`，否则首个非空行。 */
export function titleFromText(s) {
  const text = String(s || '').replace(/\r\n/g, '\n');
  const m = text.match(/^#{1,6}\s+(.+?)\s*$/m);
  if (m) return m[1].replace(/[*_`~]/g, '').trim().slice(0, 120);
  for (const line of text.split('\n')) {
    const t = line.trim().replace(/^[#>*\-\s]+/, '').trim();
    if (t) return t.slice(0, 120);
  }
  return '';
}

/**
 * 回退链：auto = 非HTML透传 -> Defuddle -> Trafilatura(可选) -> semantic -> ui。
 * 非 HTML 输入（markdown/纯文本/JSON）任何模式下都透传原文，不硬抽；
 * 强制指定 extractor 时同理（硬把 markdown 当 HTML 解析只会得到空标题）。
 */
export async function extractHtml(html, { url = 'about:blank', extractor = 'auto', contentType = null, attrs = 'semantic', format = 'compact', pruneEmpty = false, pythonBin } = {}) {
  if (!EXTRACTORS.includes(extractor)) {
    throw new Error(`unknown extractor "${extractor}"（可选: ${EXTRACTORS.join(', ')}）`);
  }
  if (extractor === 'sanitize' && !ATTR_POLICIES.includes(attrs)) {
    throw new Error(`unknown attrs policy "${attrs}"（可选: ${ATTR_POLICIES.join(', ')}）`);
  }
  if (extractor === 'sanitize' && !FORMAT_POLICIES.includes(format)) {
    throw new Error(`unknown format "${format}"（可选: ${FORMAT_POLICIES.join(', ')}）`);
  }
  const t0 = Date.now();
  const raw = String(html ?? '');
  const finishPassthrough = () => {
    const text = raw.replace(/\r\n/g, '\n').trim();
    const title = titleFromText(text);
    log.info('extract', `used=passthrough（非 HTML，原样透传） ${fmtBytes(text.length)}`);
    return {
      title,
      description: '',
      published: '',
      site: '',
      domain: '',
      language: '',
      wordCount: countWords(text),
      requested: extractor,
      used: 'passthrough',
      contentType: contentType ?? null,
      content: text,
      stats: {
        inputChars: raw.length,
        outputChars: text.length,
        reductionPct: raw.length ? Math.round((1 - text.length / raw.length) * 1000) / 10 : 0,
        parseMs: Date.now() - t0,
      },
    };
  };

  if (extractor === 'passthrough') return finishPassthrough();
  if (!looksLikeHtml(raw, contentType)) return finishPassthrough();

  const tParse = Date.now();
  const document = parseOnce(raw);
  log.info('parse', `dom ${fmtMs(Date.now() - tParse)}`);

  // [extract] 只报一次：sanitize 分支要赶在 pretty 之前先报，所以由分支显式记账。
  const tEngine = Date.now();
  let extractNoted = false;
  const markExtract = (msg) => {
    if (extractNoted) return;
    extractNoted = true;
    log.info('extract', msg);
  };

  const finish = (content, used, base = {}) => {
    markExtract(`used=${used} ${fmtBytes(content.length)} in ${fmtMs(Date.now() - tEngine)}`);
    return {
      title: base.title ?? safeTitle(document),
      description: base.description ?? '',
      published: base.published ?? '',
      site: base.site ?? '',
      domain: base.domain ?? '',
      language: base.language ?? '',
      wordCount: base.wordCount ?? countWords(content),
      requested: extractor,
      used,
      content,
      stats: {
        inputChars: html.length,
        outputChars: content.length,
        reductionPct: html.length ? Math.round((1 - content.length / html.length) * 1000) / 10 : 0,
        parseMs: Date.now() - t0,
      },
    };
  };

  if (extractor === 'sanitize') {
    // html 模式的“清洗”与“排版”分开计时：pretty 往往是整条命令里最慢的一段。
    const tClean = Date.now();
    const cleaned = sanitizeHtml(document, attrs, { compact: format !== 'raw', pruneEmpty });
    markExtract(`used=sanitize attrs=${attrs} format=${format} ${fmtBytes(cleaned.length)} in ${fmtMs(Date.now() - tClean)}`);
    if (format !== 'pretty') return finish(cleaned, 'sanitize');
    const tPretty = Date.now();
    const pretty = await prettifyHtml(cleaned);
    log.info('format', `pretty ${fmtBytes(pretty.length)} in ${fmtMs(Date.now() - tPretty)}`);
    return finish(pretty, 'sanitize');
  }

  if (extractor === 'ui') {
    return finish(uiSkeleton(document), 'ui');
  }

  let defuddle = null;
  try {
    defuddle = await extractWithDefuddle(document, url);
  } catch {
    defuddle = null;
  }

  if (extractor === 'defuddle') {
    return finish(defuddle?.content ?? '', 'defuddle', defuddle ?? {});
  }

  if (extractor === 'trafilatura') {
    const alt = await tryTrafilatura(html, { pythonBin });
    if (alt.ok && alt.text.length >= MIN_ARTICLE_CHARS) {
      return finish(alt.text, 'trafilatura', defuddle ?? {});
    }
    if (alt.missing) {
      throw new Error('trafilatura 不可用：请先 pip install trafilatura（auto 模式会自动跳过它）');
    }
    return finish(alt.text || '', 'trafilatura', defuddle ?? {});
  }

  if (extractor === 'semantic') {
    return finish(semanticFallback(document), 'semantic', defuddle ?? {});
  }

  // ---- auto 链 ----
  if (defuddle && !isWeakArticle(defuddle.content ?? '', html)) {
    return finish(defuddle.content, 'defuddle', defuddle);
  }

  const alt = await tryTrafilatura(html, { pythonBin });
  // 与下面 semantic 档同口径：面板/表单页（UI 信号多）且抽出的文字不长时，
  // Trafilatura 只能拿到导航/表头碎片，应交回 UI 清单，而不是抢走结果。
  if (alt.ok && alt.text.length >= MIN_ARTICLE_CHARS && (alt.text.length >= UI_SWITCH_CHARS || uiSignalCount(html) < 3)) {
    return finish(alt.text, 'trafilatura', defuddle ?? {});
  }

  const semantic = semanticFallback(document);
  if (semantic.length >= MIN_ARTICLE_CHARS && !(defuddle && (defuddle.content ?? '').length >= semantic.length)) {
    // semantic 只有在确实比 Defuddle 残留多时才采用，否则直接进 UI。
    if (semantic.length >= UI_SWITCH_CHARS || uiSignalCount(html) < 3) {
      return finish(semantic, 'semantic', defuddle ?? {});
    }
  }

  return finish(uiSkeleton(document), 'ui', defuddle ?? {});
}

export function skeletonFromMarkdown(md) {
  const outline = [];
  const tables = [];
  const codeLangs = [];
  let codeBlocks = 0;
  let paragraphs = 0;
  let inCode = false;
  for (const line of md.split('\n')) {
    const l = line.trimEnd();
    if (/^```/.test(l)) {
      inCode = !inCode;
      if (inCode) {
        codeBlocks++;
        const tag = l.match(/^```(\S+)?/);
        codeLangs.push(tag && tag[1] ? tag[1] : 'text');
      }
      continue;
    }
    if (inCode) continue;
    if (/^\s*\|.*\|/.test(l)) {
      tables.push(l.replace(/^\s+/, ''));
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(l);
    if (h) {
      outline.push({ level: h[1].length, text: h[2].replace(/[*_`~]/g, '') });
      continue;
    }
    if (l.length > 0 && !/^[\s\-*+>]/.test(l[0])) paragraphs++;
  }
  const head = [
    `# SKELETON (outline)`,
    `- headings: ${outline.length} | text lines: ${paragraphs} | tables: ${tables.length} | code blocks: ${codeBlocks}${codeLangs.length ? ' (' + [...new Set(codeLangs)].join(', ') + ')' : ''}`,
    ``,
  ];
  const body = outline.map((h) => `${'  '.repeat(h.level - 1)}${'#'.repeat(h.level)} ${h.text}`);
  const tbl = tables.length ? [``, `## Tables`, ...tables] : [];
  const code = codeBlocks ? [``, `## Code blocks`] : [];
  return [...head, ...body, ...tbl, ...code, ``].join('\n');
}

function stripMarkdown(md) {
  return md
    .replace(/^```.*$/gm, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[|:-]+\s*$/gm, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_>`~]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function renderResult(res, mode) {
  switch (mode) {
    case 'json':
      return JSON.stringify(res, null, 2);
    case 'skeleton':
      return skeletonFromMarkdown(res.content);
    case 'text':
      return stripMarkdown(res.content);
    case 'title':
      return res.title ?? '';
    case 'markdown':
    default:
      return res.content;
  }
}

export async function runExtract(source, mode = 'markdown', { forceContent, extractor = 'auto', attrs = 'semantic', format = 'compact', pruneEmpty = false, timeoutMs, proxy, render = false, renderTimeoutMs, headful = false, chromeBin, pythonBin } = {}) {
  if (!MODES.includes(mode)) {
    throw new Error(`unknown mode "${mode}"（可选: ${MODES.join(', ')}）`);
  }
  let html;
  let src;
  let sibling = null;
  let contentType = null;
  if (forceContent != null) {
    html = forceContent;
    src = 'content';
    log.debug('read', `inline content ${fmtBytes(String(forceContent).length)}`);
  } else {
    const r = await readWithRender(
      source,
      {
        ...(timeoutMs == null ? {} : { timeoutMs }),
        ...(proxy === undefined ? {} : { proxy }),
        ...(render ? { render: true } : {}),
        ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
        ...(headful ? { headful: true } : {}),
        ...(chromeBin == null ? {} : { chromeBin }),
        ...(pythonBin == null ? {} : { pythonBin }),
      },
    );
    html = r.html;
    src = r.source;
    contentType = r.contentType ?? guessContentTypeFromPath(src);
    if (!/^https?:\/\//i.test(src) && src !== 'stdin') {
      sibling = await readSiblingMeta(src);
    }
  }
  const url = /^https?:/i.test(src)
    ? src
    : sibling && /^https?:/i.test(sibling.url)
      ? sibling.url
      : 'file:///' + (src === 'stdin' || src === 'content' ? src : src.replaceAll('\\', '/'));
  const res = await extractHtml(html, { url, extractor: mode === 'ui' ? 'ui' : mode === 'html' ? 'sanitize' : extractor, contentType, attrs, format, pruneEmpty, ...(pythonBin == null ? {} : { pythonBin }) });
  log.debug('extract', `mode=${mode} requested=${res.requested} used=${res.used} reduction=${res.stats.reductionPct}% title="${res.title ?? ''}"`);
  if (sibling) res.meta = sibling.meta;
  return renderResult(res, mode);
}
