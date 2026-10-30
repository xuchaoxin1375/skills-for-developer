import { readFile, readdir, unlink, writeFile } from 'node:fs/promises';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { basename, dirname, join, resolve as resolvePath } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';
import { promisify } from 'node:util';
import { parseHTML } from 'linkedom';
import { Defuddle } from 'defuddle/node';
import { ProxyAgent } from 'undici';
import { fmtBytes, fmtMs, log, paintStatus, timestamp } from './log.js';
import { VERSION } from './version.js';

const execFileAsync = promisify(execFile);

export const MODES = ['markdown', 'skeleton', 'text', 'json', 'title', 'ui', 'html'];
export const EXTRACTORS = ['auto', 'defuddle', 'trafilatura', 'semantic', 'ui', 'sanitize', 'passthrough'];
/** html 模式的属性策略：none 清空全部属性 | semantic（默认）保留语义属性 | all 保留全部属性。 */
export const ATTR_POLICIES = ['none', 'semantic', 'all'];
/** html 模式的排版策略：raw 原样（保留源码缩进空白） | compact（默认）压掉缩进噪声 | pretty 重新缩进。 */
export const FORMAT_POLICIES = ['raw', 'compact', 'pretty'];

/**
 * 取值清单的一句话说明：CLI 帮助、MCP 参数说明、--list-* 输出共用同一份，
 * 避免"帮助里写的取值"与"代码里允许的取值"各说各话（历史上就这么漂移过一次）。
 * 新增取值时只改这里，文档与补全脚本的漂移由 tests/reliability.mjs 断言兜住。
 */
export const MODE_DESCRIPTIONS = {
  markdown: '正文 Markdown（默认）：文章页走 Defuddle，界面页自动回退为组件清单',
  skeleton: '只出大纲：标题层级、表格、代码块语言',
  text: '纯文本，不带任何标记',
  json: 'JSON：title / used / requested / version / content / stats{reductionPct} / meta?',
  title: '只打印页面标题',
  ui: '界面组件清单：标签、按钮、输入框、表格',
  html: '清理后的 HTML：保留完整 DOM 结构与文字顺序，去掉脚本/样式/模板/图标/注释',
};
export const EXTRACTOR_DESCRIPTIONS = {
  auto: '自动选择（默认）：非 HTML 原样透传 → Defuddle → Trafilatura（装了才用，否则静默跳过）→ semantic → ui 清单',
  defuddle: '正文抽取（文章页首选）',
  trafilatura: '正文抽取（备选，需 pip install trafilatura）',
  semantic: '按语义标签抽正文',
  ui: '界面组件清单',
  sanitize: '只做清理（去脚本/样式/事件属性），不抽正文；--mode html 就是它',
  passthrough: '原样透传，不做任何处理',
};
export const ATTR_POLICY_DESCRIPTIONS = {
  none: '清空全部属性（最小，但丢链接目标与合并单元格）',
  semantic: '保留 href/src/alt/title/colspan/rowspan/scope 与表格/表单状态（默认，推荐）',
  all: '保留全部属性，只去掉脚本与样式',
};
export const FORMAT_POLICY_DESCRIPTIONS = {
  raw: '保留源码缩进空白',
  compact: '压掉缩进与空行，行内元素间留一个空格（默认，最小）',
  pretty: '重新缩进，便于人读（需要 js-beautify 依赖）',
};
export const RENDER_ENGINE_DESCRIPTIONS = {
  auto: '逐层升档（默认）：静态优先；装了求解引擎就从 scrapling/cloak-cdp 起步，playwright 兜底',
  playwright: '层 1：Playwright/Patchright 驱动，只渲染不求解',
  scrapling: '层 2：Patchright + 挑战求解（需 ≥60s 预算）',
  'cloak-cdp': '层 2：CloakBrowser 直连 CDP，带挑战求解（需 ≥60s 预算）',
  'chrome-late': '晚接入：先让站点的挑战跑完，再接入读已渲染 DOM（挑战站点专用）',
  nodriver: '层 1 备用：系统 Chrome 直接 CDP，不伪造指纹',
};

export const DEFAULT_UA =
  `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15 htmlmini/${VERSION}`;

const MIN_ARTICLE_CHARS = 50;
const UI_SWITCH_CHARS = 300;
const TRAFILATURA_TIMEOUT_MS = 15000;
// 渲染后判"仍是挑战空壳"的正文上限：真内容页不会短到这个程度（与"应用壳"判据同量级）。
const BODY_CHALLENGE_MAX_CHARS = 300;
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

/** 渲染后正文里的挑战特征：零依赖 Chrome 只渲染、不求解，拿到空壳时靠它把原因说对。 */
export function bodyChallengeSignals(html) {
  const s = String(html ?? '');
  const sigs = [];
  const title = (s.match(/<title[^>]*>([\s\S]{0,120}?)<\/title>/i)?.[1] ?? '').replace(/\s+/g, ' ').trim();
  // 标题是强判据：挑战中间页的标题就是这几句，正常内容页不会长这样。
  if (/just a moment|attention required|checking your browser|verifying you are human|请稍候|正在验证/i.test(title)) {
    return [`challenge title "${title}"`];
  }
  // WAF 直接拒绝的页面（Akamai 的 "Access Denied"）也是强判据：没有正常内容页用这种标题。
  // 它和"挑战还在跑"不是一回事：挑战页再等就有机会，拒绝页是终局，处置方式不同。
  if (/access denied|^forbidden$|^error 10(15|20)$|you have been blocked/i.test(title)) {
    return [`block page title "${title}"`];
  }
  // 其余判据只在正文极短时才认：避免把讲 Cloudflare / 嵌入 Turnstile 组件但确有内容的页面误判。
  const text = s
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (text.length > BODY_CHALLENGE_MAX_CHARS) return sigs;
  // 这些是 Cloudflare 自己的内部标识（DOM id、挑战脚本 URL），几乎不会出现在正常正文里；
  // 裸词 "turnstile" / "challenges.cloudflare.com" 不算——文档页与表单页都会有。
  if (/cf-chl|__cf_chl|_cf_chl_opt|cdn-cgi\/challenge/i.test(s)) sigs.push('cloudflare challenge markers');
  if (/challenges\.cloudflare\.com\/(turnstile|[^"'\s]*\.js)/i.test(s)) sigs.push('cloudflare turnstile script');
  return sigs;
}

const PROXY_REGISTRY_ENV = 'HTMLMINI_PROXY_REGISTRY';
const DEFAULT_PROXY_REGISTRY = join(homedir(), '.config', 'proxy-resources.json');

/**
 * 读本机代理登记（network-access 约定的 ~/.config/proxy-resources.json）里的候选入口。
 * 只读不探测：本函数用在失败路径上补提示，不替用户改路线。
 */
export function proxyRegistryCandidates(registryPath) {
  const file = registryPath ?? process.env[PROXY_REGISTRY_ENV] ?? DEFAULT_PROXY_REGISTRY;
  try {
    const data = JSON.parse(readFileSync(file, 'utf8'));
    const list = Array.isArray(data?.proxies) ? data.proxies : [];
    return list
      .map((p) => (typeof p === 'string' ? p : p?.url))
      .filter((u) => typeof u === 'string' && u.trim());
  } catch {
    return [];
  }
}

/** 抓取失败时的登记提示：htmlmini 不自动读登记文件，得让调用方知道有条现成的路。 */
function registryHint(source, proxy) {
  if (proxy !== undefined) return '';
  const { origin } = proxyOrigin(source, { proxy });
  const cands = proxyRegistryCandidates();
  if (!cands.length) return '';
  const shown = cands.map((u) => maskProxy(u)).join(', ');
  return origin === 'none'
    ? `; no proxy in use and this machine has a proxy registry (~/.config/proxy-resources.json): ${shown} — htmlmini does not read it automatically, pass --proxy <url> or set HTTPS_PROXY`
    : `; the ${origin} proxy failed; the machine registry also lists: ${shown} — try them one by one instead of concluding the site is unreachable`;
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
      if (e && e.name === 'TimeoutError') throw new Error(`fetch timeout after ${timeoutMs}ms: ${source}${via}${registryHint(source, proxy)}`);
      if (proxyUrl) throw new Error(`${e.message} (via proxy ${maskProxy(proxyUrl)} for ${source})${registryHint(source, proxy)}`);
      throw new Error(`${e.message}${registryHint(source, proxy)}`);
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
      // 登记提示只对"可能是路线问题"的状态出现：404/410 是资源级结论，换出口不会变。
      const routeHint = res.status === 403 || (res.status >= 500 && res.status <= 599) ? registryHint(source, proxy) : '';
      const err = new Error(`HTTP ${res.status} fetching ${source}${initial}${via}${failureHint(res)}${routeHint}`);
      err.statusCode = res.status;
      throw err;
    }
    const contentType = res.headers.get('content-type');
    return { html: decodeHtml(Buffer.from(await res.arrayBuffer())), source, contentType, status: res.status };
  }
  return { html: decodeHtml(await readFile(source)), source, contentType: guessContentTypeFromPath(source), status: null };
}

// ---- 按需浏览器渲染（显式 opt-in：--render / render:true）----
// 静态抓取报 403/5xx 才回退到浏览器（404/超时/断网直接抛，不烧浏览器时间）。
// 渲染仍由 resilient-browser-fetch 的 save_page 执行（同代理），本文件只负责调度和提取。
export const RENDER_TIMEOUT_MS = 300_000;
/** 可钉住的渲染引擎：save_page 的浏览器层；static/scrapling-cli 在渲染语境下不适用。 */
export const RENDER_ENGINE_CHOICES = ['auto', 'playwright', 'scrapling', 'cloak-cdp', 'chrome-late', 'nodriver'];
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

/** 引擎名 → 层号；扫描结果缺 levels 时按引擎名推导（兼容旧版脚本与测试桩）。 */
const ENGINE_LEVELS = { static: 0, playwright: 1, patchright: 1, scrapling: 2, 'cloak-cdp': 3 };

function candidateLevel(entry) {
  const declared = Math.max(0, ...(entry?.levels ?? []));
  const derived = Math.max(
    0,
    ...(entry?.engines ?? []).map((name) => ENGINE_LEVELS[String(name).toLowerCase()] ?? 0),
  );
  return Math.max(declared, derived);
}

/**
 * 扫描本机候选解释器，返回按能力排序的可用列表（借 resilient-browser-fetch 的 check_environment.py --list-envs）。
 * 只在需要时调用，结果按 required 组合缓存；任何失败都返回空数组，绝不打断主流程。
 */
export async function scanPythonEnvironments(required = ['playwright']) {
  if ((process.env[ENV_SCAN_ENV] ?? '').trim() === '0') return [];
  const key = required.join(',');
  if (envScanCache.has(key)) return envScanCache.get(key);
  const script = findEnvScanScript();
  if (!script) return [];
  let runner;
  try {
    runner = await findDefaultPython(); // 用 PATH 上的解释器跑扫描；它只要能跑标准库即可
    if (!runner) throw new Error('no python on PATH');
  } catch {
    envScanCache.set(key, []);
    return [];
  }
  const program = [
    'import json, sys',
    'sys.path.insert(0, sys.argv[1])',
    'import check_environment as ce',
    `required = tuple(${JSON.stringify(required)})`,
    'envs = ce.scan_environments(required, sys.argv[1])',
    'usable = [e for e in envs if e.get("ok") and not e.get("satisfies")]',
    'print(json.dumps([{"path": e.get("path"), "engines": list(e.get("engines") or []),',
    '                  "levels": list(e.get("levels") or []), "manager": e.get("manager")}',
    '                 for e in usable], ensure_ascii=False))',
  ].join('\n');
  let candidates = [];
  try {
    const { stdout } = await execFileAsync(
      runner,
      ['-X', 'utf8', '-c', program, dirname(script)],
      { timeout: 120_000, windowsHide: true },
    );
    const parsed = JSON.parse(String(stdout).trim().split('\n').pop() || '[]');
    if (Array.isArray(parsed)) candidates = parsed.filter((e) => e && e.path);
  } catch (e) {
    log.debug('render', `解释器环境扫描失败，忽略: ${e.message}`);
  }
  envScanCache.set(key, candidates);
  return candidates;
}

const envScanCache = new Map();

/** 清空解释器扫描缓存（环境变量变化或测试需要重新扫描时用）。 */
export function resetEnvScanCache() {
  envScanCache.clear();
}

/** 扫描后挑第一个具备所需层的解释器；没有则 null。 */
export async function findCapablePython(required = ['playwright']) {
  const [first] = await scanPythonEnvironments(required);
  if (!first) return null;
  return { recommended: first.path, engines: first.engines ?? [], manager: first.manager ?? null };
}

/**
 * 找本机装了挑战求解引擎（scrapling / cloak-cdp）的解释器；扫描结果按能力排序，首个命中即最强。
 * 没有则 null：扫描脚本缺失、没装求解引擎、或者只有显式指定的环境，都走这条路。
 */
export async function findSolverPython() {
  const candidates = await scanPythonEnvironments(['playwright']);
  for (const entry of candidates) {
    const engines = entry.engines ?? [];
    if (!entry.path) continue;
    if (!engines.some((name) => SOLVER_ENGINES.includes(name))) continue;
    return { path: entry.path, engines, manager: entry.manager ?? null, level: candidateLevel(entry) };
  }
  return null;
}

/**
 * 渲染失败后是否可以换更强的解释器再试。
 * 显式指定了解释器就尊重用户选择；配置类错误换环境也没用。
 */
export async function pickStrongerPython({ pythonBin, current = null, minLevel = 2 } = {}) {
  if (pythonBinOverride(pythonBin)) return null;
  const candidates = await scanPythonEnvironments(['playwright']);
  const currentPath = current ? resolvePath(String(current)).toLowerCase() : null;
  for (const entry of candidates) {
    if (candidateLevel(entry) < minLevel) continue;
    if (currentPath && resolvePath(String(entry.path)).toLowerCase() === currentPath) continue;
    return {
      recommended: entry.path,
      engines: entry.engines ?? [],
      manager: entry.manager ?? null,
      level: candidateLevel(entry),
    };
  }
  return null;
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

export async function runChromeDump(url, { proxy, timeoutMs = 60_000, chromeBin, chromeSource = 'explicit', info = null } = {}) {
  const bin = chromeBin ?? findChromeBin();
  if (!bin) throw new Error('no system Chrome/Chromium found; set HTMLMINI_CHROME_BIN to its path to use chrome rendering');
  if (info) Object.assign(info, { engine: 'chrome-dump', status: null });
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

export async function renderViaBrowser(url, { proxy, renderTimeoutMs = RENDER_TIMEOUT_MS, headful = false, chromeBin, browserBrand, pythonBin, renderEngine, cdpUrl, info = null, forceRender = false } = {}) {
  const { script, engines, solver, python } = await renderCapability(pythonBin, { renderTimeoutMs });
  // 记下实际用的解释器：渲染失败时要能回退到默认环境（更强环境可能没装浏览器二进制）。
  if (info) info.python = python;
  const canSavePage =
    Boolean(script) && (engines === null || engines.some((name) => BROWSER_ENGINES.includes(name)));
  // 显式钉住引擎：save_page 只在那个引擎上跑（缺件直接失败），因此通路必须走 save_page，
  // 否则零依赖 Chrome 会顶掉用户的选择，钉层等于没生效。
  const pinned = renderEngine && renderEngine !== 'auto' ? renderEngine : null;
  if (pinned && !canSavePage) {
    const alternative = await findCapablePython(['playwright']).catch(() => null);
    throw new Error(
      `--render-engine ${pinned} needs the save_page renderer (resilient-browser-fetch), but no browser-capable engine is available here`
      + pythonHint(python, alternative),
    );
  }
  // 求解引擎（scrapling/cloak-cdp）至少要 60s 预算（挑战页自身要等满时长）。
  // 预算不够时求解引擎用不了：显式钉了求解引擎就直说，否则由 runSavePage 把阶梯钉到层 1。
  if (pinned && SOLVER_ENGINES.includes(pinned) && renderTimeoutMs < MIN_SOLVER_TIMEOUT_MS) {
    throw new Error(
      `--render-engine ${pinned} 至少需要 ${MIN_SOLVER_TIMEOUT_MS}ms 的渲染预算（挑战页自身要等满时长）；`
      + `当前 --render-timeout-ms ${renderTimeoutMs}。要按这个预算渲染，改用 --render-engine playwright（只渲染，不求解挑战）。`,
    );
  }

  // Chrome 无头 dump-dom 不支持开窗，--headful 只走 save_page 通路。
  let found = null;
  // 浏览器路径两条通路都要用, 先验存在性: 传下去之前不校验, 报错会晚到子进程里。
  if (chromeBin && !existsSync(chromeBin)) throw new Error(`chrome binary not found: ${chromeBin} (--chrome-bin)`);
  if (!headful) {
    if (chromeBin) {
      found = { bin: chromeBin, source: 'explicit' };
    } else {
      try {
        found = findChromeBin();
      } catch {
        found = null;
      }
    }
  }

  // 有求解引擎、需要开窗、本机没有 Chrome、显式钉了引擎，或要接管用户已开着的浏览器时，save_page 更合适；
  // 层 1 与 Chrome 同能力时优先零依赖通路。接管路线没有零依赖版本(必须走 CDP), 所以 cdpUrl 强制走 save_page。
  const runSave = (engineOverride) => runSavePage(url, {
    script,
    proxy,
    renderTimeoutMs,
    headful,
    pythonBin,
    python,
    renderEngine: engineOverride ?? renderEngine,
    cdpUrl,
    chromeBin,
    browserBrand,
    info,
    solver,
  });
  // render=always 的语义是"必须执行 JS"。save_page 的 auto 阶梯以 static 层起步，页面 200 时
  // 它先"成功"，交回未水合 HTML；这时换浏览器层重跑一次，而不是把没跑脚本的 DOM 当结果。
  const ensureHydrated = async (html) => {
    if (!forceRender || !info || info.engine !== 'static') return html;
    const engine = pickHydrationEngine({ engines, renderTimeoutMs });
    if (!engine) {
      throw new Error(
        'render=always: save_page 的 auto 阶梯用 static 层返回了未执行 JS 的页面，本机也没有可用的浏览器层'
        + '（playwright / nodriver / 求解引擎）；安装 playwright，或改用 --render-engine chrome-late',
      );
    }
    log.info('render', `render=always: save_page 用 static 层返回了未执行 JS 的页面，改用 ${engine} 重渲染`);
    // 只清上一轮的结果，保留 info.python（升档逻辑要用它判断当前解释器）。
    for (const k of ['status', 'engine', 'notes']) delete info[k];
    return await runSave(engine);
  };
  if (canSavePage && (pinned || solver || headful || !found || cdpUrl)) {
    return await ensureHydrated(await runSave());
  }
  if (found) {
    try {
      return await runChromeDump(url, { proxy, timeoutMs: Math.min(renderTimeoutMs, 120_000), chromeBin: found.bin, chromeSource: found.source, info });
    } catch (chromeErr) {
      if (!canSavePage) throw chromeErr;
      // 零依赖通路崩了（进程退出码异常、超时等）时，同能力的 save_page 值得再试一次。
      log.info('render', `chrome 通路失败，改用 save_page 重试: ${chromeErr.message}`);
      try {
        return await ensureHydrated(await runSave());
      } catch (saveErr) {
        throw new Error(`${chromeErr.message}; save_page 回退也失败: ${saveErr.message}`);
      }
    }
  }
  if (canSavePage) return await ensureHydrated(await runSave());
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

/**
 * 渲染失败是否值得换一个更强的解释器再试一次。
 * 配置类错误（找不到渲染器/解释器、目标资源 404/410、域名解析失败）换环境无用。
 */
export function isInterpreterRetryable(e) {
  const m = String(e?.message ?? '');
  if (!m) return false;
  if (/renderer not found|no python found|interpreter is not usable/i.test(m)) return false;
  if (/ENOTFOUND|EAI_AGAIN|\b(?:404|410)\b/.test(m)) return false;
  return /challenge|save_page|engine|引擎|render|渲染|chrome|dump-dom|timeout|超时/i.test(m);
}


// save_page 可用性探测：从不抛错。判定口径是"层 ≥1 有可用引擎"（playwright/scrapling/cloak-cdp/
// chrome-late/nodriver），不再要求必须装 scrapling；静态抓取仍由本模块自己完成。
// 但层 1 与零依赖 Chrome 直渲能力重叠（都只是渲染、都不求解挑战），
// 因此只在下列情况优先 save_page：有求解引擎（层 2/3）、需要 --headful、本机没有 Chrome，
// 或显式钉了 chrome-late 这类"先让挑战跑完再接入"的引擎。
const BROWSER_ENGINES = ['playwright', 'scrapling', 'cloak-cdp', 'chrome-late', 'nodriver'];
const SOLVER_ENGINES = ['scrapling', 'cloak-cdp'];
/** 求解引擎的最低预算：挑战页自身要等满时长（与 resilient-browser-fetch 的 MIN_SOLVER_TIMEOUT_MS 对齐）。 */
const MIN_SOLVER_TIMEOUT_MS = 60_000;
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
async function renderCapability(pythonBin, { renderTimeoutMs = RENDER_TIMEOUT_MS } = {}) {
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
  let engines = await probeRenderEngines(python, script);
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
  let solver = engines.some((name) => SOLVER_ENGINES.includes(name));
  // 默认解释器只会渲染、不会求解挑战，而本机另有装了 scrapling/cloak-cdp 的环境：
  // 直接用那个环境，省掉"弱引擎先跑一遍"的往返（层 1 遇到挑战页必然过不去）。
  // 显式指定了解释器就尊重用户选择，不静默换环境。
  // 求解引擎至少要 60s 预算：预算不够时它用不上，别为一个用不了的引擎换环境。
  if (!solver && !pythonBinOverride(pythonBin) && renderTimeoutMs >= MIN_SOLVER_TIMEOUT_MS) {
    const stronger = await findSolverPython();
    if (stronger && resolvePath(String(stronger.path)).toLowerCase() !== resolvePath(String(python)).toLowerCase()) {
      const probed = await probeRenderEngines(stronger.path, script);
      if (probed && probed.some((name) => SOLVER_ENGINES.includes(name))) {
        log.info(
          'render',
          `默认解释器不具备挑战求解能力，改用更强环境: ${stronger.path} (${stronger.manager ?? '未知管理方式'}; 引擎: ${probed.join(', ')})`,
        );
        python = stronger.path;
        engines = probed;
        solver = true;
      }
    }
  }
  return { script, engines, solver, python };
}

/** save_page 是否有层 ≥1 的可用引擎；供测试与调用方判断渲染通路。 */
export async function savePageUsable(pythonBin) {
  const { script, engines } = await renderCapability(pythonBin);
  if (!script) return null;
  if (engines === null || engines.some((name) => BROWSER_ENGINES.includes(name))) return script;
  return null;
}


/**
 * 构造 save_page(resilient-browser-fetch) 的子进程参数。
 *
 * 单独抽出来是为了能直接断言参数：浏览器路径必须真的传下去。
 * 早先 --chrome-bin 只喂给零依赖的 chrome dump-dom 通路，走 save_page
 * (chrome-late 等) 时被静默丢掉，WAF 按客户端品牌判负时会一路踩空。
 */
export function savePageArgs({
  script,
  url,
  out,
  engine = 'auto',
  renderTimeoutMs,
  proxyUrl = null,
  cdpUrl = null,
  headful = false,
  chromeBin = null,
  browserBrand = null,
}) {
  // -X utf8 + PYTHONUTF8：子进程日志强制 UTF-8 输出，本侧按 UTF-8 增量解码、
  // 逐行透传（Windows 控制台查看侧按 powershell-pitfalls 的 UTF-8 模板设置）。
  // --engine 透传：显式指定时 save_page 只用该层（不再自动升档），已知站点可省掉注定失败的升档。
  const args = ['-X', 'utf8', script, url, '--out', out, '--engine', engine, '--timeout-ms', String(renderTimeoutMs)];
  // 渲染预算同时透传给引擎: 客户端渲染的应用常在静态壳上停很久, chrome-late 这类
  // "接入后等渲染稳定"的引擎要拿到同样的上限, 否则会在半渲染状态下被读走。
  // 上限取 60s: 够 SPA 水合, 又不至于把外层预算全耗在等一个永不稳定的 DOM 上。
  args.push('--render-timeout-ms', String(Math.min(renderTimeoutMs, 60_000)));
  if (proxyUrl) args.push('--proxy', proxyUrl);
  else args.push('--discover-proxy');
  // 接管用户已开着的浏览器: 复用它的 profile/cookie/放行凭据, 只读已渲染的 DOM。
  if (cdpUrl) args.push('--cdp-url', cdpUrl);
  if (headful) args.push('--headful');
  // 浏览器路径: 晚接入引擎默认挑 Chrome, 但 WAF 可能按客户端品牌判负
  // (实测同一出口 Chrome 被拒、Edge 放行), 显式指定必须传下去。
  if (chromeBin) args.push('--executable-path', chromeBin);
  // 品牌偏好: 让渲染脚本按品牌去找已安装的浏览器(不用自己写路径)。
  if (browserBrand) args.push('--browser-brand', browserBrand);
  return args;
}

/**
 * 决定传给 save_page 的引擎：显式指定优先；auto 模式下若渲染预算低于求解引擎下限，
 * 就把阶梯钉到层 1（只渲染，不求解挑战）——save_page 在启用求解时要求 timeout_ms ≥ 60s，
 * 预算不够时整条命令会被参数校验直接拒绝。
 */
export function resolveSavePageEngine({ renderEngine = null, solver = false, renderTimeoutMs = RENDER_TIMEOUT_MS } = {}) {
  const engine = renderEngine ?? 'auto';
  if (engine === 'auto' && solver && renderTimeoutMs < MIN_SOLVER_TIMEOUT_MS) return 'playwright';
  return engine;
}

/**
 * `render=always` 要的是"执行过 JS 的 DOM"，但 save_page 的 auto 阶梯以 `static` 层起步：
 * 页面返回 200 时它先算成功，交回的是没跑脚本的 HTML（异步 fetch 的清单、客户端渲染的正文都不在）。
 * 拿到 static 结果时换一个真正的浏览器层重跑一次；engines 为 null 表示旧版脚本不报引擎清单，
 * 按层 1（playwright）试。求解引擎要够预算，否则返回 null，由调用方报错而不是静默交出未水合页面。
 */
export function pickHydrationEngine({ engines = null, renderTimeoutMs = RENDER_TIMEOUT_MS } = {}) {
  if (engines === null) return 'playwright';
  const browser = engines.filter((name) => BROWSER_ENGINES.includes(name));
  for (const name of ['playwright', 'nodriver']) if (browser.includes(name)) return name;
  const solver = browser.find((name) => SOLVER_ENGINES.includes(name));
  if (solver) return renderTimeoutMs >= MIN_SOLVER_TIMEOUT_MS ? solver : null;
  return null;
}

async function runSavePage(url, { script, proxy, renderTimeoutMs, headful, pythonBin, python, renderEngine, cdpUrl, chromeBin, browserBrand, info = null, solver = false }) {
  const interpreter = python ?? (await findPython({ pythonBin }));
  const proxyUrl = resolveProxy(url, { proxy });
  const out = join(tmpdir(), `htmlmini-render-${process.pid}-${Date.now()}-${renderSeq++}.html`);
  // 求解引擎至少要 60s 预算：预算不够时把 auto 阶梯钉到层 1（只渲染，不求解挑战），
  // 否则 save_page 会因"启用 Cloudflare 求解时 timeout_ms 不得低于 60000"直接拒绝参数。
  const engine = resolveSavePageEngine({ renderEngine, solver, renderTimeoutMs });
  if (engine === 'playwright' && (renderEngine ?? 'auto') === 'auto') {
    log.info(
      'render',
      `渲染预算 ${renderTimeoutMs}ms 不足求解引擎的 ${MIN_SOLVER_TIMEOUT_MS}ms 下限，本次只渲染不求解挑战`,
    );
  }
  const args = savePageArgs({
    script,
    url,
    out,
    engine,
    renderTimeoutMs,
    proxyUrl,
    cdpUrl,
    headful,
    chromeBin,
    browserBrand,
  });
  const proxyNote = describeProxy(url, proxy);
  const browserNote = chromeBin
    ? ` [browser: ${basename(chromeBin)}]`
    : browserBrand
      ? ` [browser: ${browserBrand}]`
      : '';
  log.info('render', `engine=save-page${headful ? ' headful' : ''} [python: ${interpreter}] [proxy: ${proxyNote === 'none' ? 'none, render script discovers its own' : proxyNote}]${browserNote}`);
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
    // save_page 把最终 URL、状态码与引擎写在 <out>.meta.json；渲染通路的真实状态码只在这里，
    // 读完正文立刻取（finally 里会清理临时产物）。
    if (info) Object.assign(info, await readRenderMeta(out));
    if (!html.trim()) throw new Error(`browser render returned empty page for ${url}`);
    return html;
  } finally {
    // save_page 成功/失败都会在 out 旁落文件（正文、.meta.json、.attempts.json、
    // .<engine>.blocked.html）；basename 唯一，按前缀全清，不留残留。
    // finally 包住 spawn（失败早抛也清），读文件在 finally 之前（先读后删）。
    await cleanupRenderArtifacts(out);
  }
}

/**
 * 读 save_page 写在正文旁的 `<out>.meta.json`：渲染通路的真实状态码与引擎只有这里知道。
 * 缺失或损坏时返回空对象——渲染结果本身仍可用，不该因为元数据缺失而失败。
 */
async function readRenderMeta(out) {
  try {
    const meta = JSON.parse(await readFile(`${out}.meta.json`, 'utf8'));
    const info = {};
    if (Number.isFinite(meta?.status)) info.status = meta.status;
    if (meta?.engine) info.engine = String(meta.engine);
    if (Array.isArray(meta?.notes) && meta.notes.length) info.notes = meta.notes.map(String);
    return info;
  } catch {
    return {};
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
  { timeoutMs = FETCH_TIMEOUT_MS, proxy, render = false, renderTimeoutMs, headful = false, chromeBin, browserBrand, pythonBin, renderEngine, cdpUrl, allowEmpty = false } = {},
) {
  const remote = /^https?:\/\//i.test(source ?? '');
  const tRead = Date.now();
  // 抓取前先报：网络与浏览器渲染都是长等待，不能静默；[proxy: …] 说明实际路由与来源。
  // 放在这一层而不是 runExtract，CLI 与 MCP（handleSource 直接调本函数）才都有进度。
  if (remote) log.info('read', `fetching ${source} [proxy: ${describeProxy(source, proxy)}]`);
  // 渲染通路的状态码只有 save_page 的 meta 里有，零依赖 chrome dump-dom 拿不到，故用采集器回传。
  const info = {};
  const done = (r) => {
    const status = Number.isFinite(r.status) ? r.status : Number.isFinite(info.status) ? info.status : null;
    r.status = status;
    r.engine = info.engine ?? null;
    // 状态码放在最前面并着色（TTY）：它比体积/耗时更能说明这次抓取是否可信。
    const unknown = r.rendered && !Number.isFinite(status);
    const staticNote = Number.isFinite(info.staticStatus) ? ` (static ${info.staticStatus})` : '';
    const statusLabel = Number.isFinite(status)
      ? paintStatus(`status=${status}`, status)
      : unknown
        ? paintStatus(`status=unknown${staticNote}`, NaN)
        : '';
    log.info('read', `${statusLabel ? `${statusLabel} ` : ''}${r.source ?? source} ${fmtBytes(r.html.length)} in ${fmtMs(Date.now() - tRead)}${r.rendered ? ' via browser render' : ''}`);
    if (unknown) {
      log.info(
        'read',
        info.engine === 'chrome-dump' || !info.engine
          ? 'status unknown: chrome dump-dom 不返回 HTTP 状态码；要确切状态码请加 --render-engine playwright 或 scrapling（走 save_page，状态码来自 meta.json）'
          : 'status unknown: save_page 的 meta.json 未给出 status（渲染成功但缺少元数据）',
      );
    }
    log.debug('read', `source=${r.source ?? source} status=${Number.isFinite(status) ? status : 'unknown'} contentType=${r.contentType ?? 'unknown'}${r.engine ? ` engine=${r.engine}` : ''}${remote ? ` render=${render === 'always' ? 'always' : render ? 'allowed' : 'static-only'} proxy=${describeProxy(source, proxy)}` : ''}`);
    return r;
  };
  // 渲染通路拿到的仍是挑战空壳时，别把"水合没做"当成原因：零依赖 Chrome 只渲染、不求解。
  // 正文极短且带挑战特征才判（见 bodyChallengeSignals），长文章提到挑战机制不会误伤。
  const guardRendered = (r) => {
    const sigs = bodyChallengeSignals(r.html);
    if (!sigs.length || allowEmpty) return r;
    // WAF 拒绝页与"挑战还在跑"处置不同：拒绝页是终局（再换渲染方式也没用），
    // 挑战页再等就有机会。下一步提示也要分开写。
    const blocked = sigs.filter((s) => s.startsWith('block page title'));
    if (blocked.length) {
      throw new Error(
        `rendered page is the site's block page (${blocked.join(', ')}): the request was refused outright — don't keep switching render modes, the site rejected this one. Use --render-engine chrome-late (attach late: let the site's challenge finish before attaching) on the same proxy, or change the exit/proxy. Pass --allow-empty to keep the block HTML anyway.`,
      );
    }
    throw new Error(
      `rendered page still looks like a challenge (${sigs.join(', ')}): the rendering pathway does not solve challenges — add --python-bin auto (or set HTMLMINI_PYTHON=auto) so the save_page engine (scrapling/cloak-cdp) solves it, or fetch it with resilient-browser-fetch (--headful for manual verification). Pass --allow-empty to keep the challenge HTML anyway.`,
    );
  };
  // 静态 200 也可能是 WAF 拒绝页（标题 "Access Denied" 一类）。当正文交出去是假成功，
  // 必须报错：标题判据足够强，正常内容页不会用这种标题。
  const guardBlocked = (r) => {
    const blocked = bodyChallengeSignals(r.html ?? '').filter((s) => s.startsWith('block page title'));
    if (!blocked.length || allowEmpty) return r;
    const err = new Error(
      `this page is the site's block page (${blocked.join(', ')}), not content — the request was refused outright. Re-fetch from a different exit/proxy, or render it via resilient-browser-fetch --engine chrome-late (attach late) on the same proxy. Pass --allow-empty to keep the HTML anyway.`,
    );
    // 静态正文就是拒绝页时，值得再渲染一次：真实浏览器可能过得去（403/5xx 也是这个处置）。
    err.blockPage = true;
    throw err;
  };
  // 渲染一次并做挑战判定；bin 为空表示沿用默认解释器（PATH 的 python/python3）。
  const renderHtml = async (bin) => {
    // 只清上一轮渲染的结果，保留静态回退时记下的状态码（info.staticStatus）。
    for (const k of ['status', 'engine', 'notes', 'python']) delete info[k];
    const html = await renderViaBrowser(source, {
      proxy,
      info,
      ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
      ...(headful ? { headful: true } : {}),
      ...(chromeBin == null ? {} : { chromeBin }),
      ...(browserBrand == null ? {} : { browserBrand }),
      ...(bin == null ? {} : { pythonBin: bin }),
      ...(renderEngine == null ? {} : { renderEngine }),
      ...(cdpUrl == null ? {} : { cdpUrl }),
      ...(render === 'always' ? { forceRender: true } : {}),
    });
    return guardRendered({ html, source, contentType: 'text/html', rendered: true });
  };
  // 渲染没成功时的处置顺序：先换默认环境（更强环境可能没装浏览器二进制），
  // 再换另一个更强环境。显式指定了解释器就尊重用户选择，不自动换。
  const renderWithEscalation = async () => {
    let firstError = null;
    const tryRender = async (bin) => {
      try {
        return done(await renderHtml(bin));
      } catch (e) {
        if (!isInterpreterRetryable(e)) throw e;
        if (!firstError) firstError = e;
        return null;
      }
    };
    const rendered = await tryRender(pythonBin);
    if (rendered) return rendered;
    const used = info.python ?? null;
    let current = null;
    try {
      current = await findPython({ pythonBin });
    } catch {
      current = null;
    }
    // 首选的更强环境失败 → 回退到默认环境再试一次。
    if (
      !pythonBinOverride(pythonBin)
      && used
      && current
      && resolvePath(String(used)).toLowerCase() !== resolvePath(String(current)).toLowerCase()
    ) {
      log.info('render', `更强环境未成功，回退到默认解释器重试: ${current}`);
      const fallback = await tryRender(current);
      if (fallback) return fallback;
    }
    const stronger = await pickStrongerPython({ pythonBin, current: used ?? current }).catch(() => null);
    if (!stronger) throw firstError;
    log.info(
      'render',
      `渲染未成功，改用更强的解释器重试: ${stronger.recommended} (层 ${stronger.level}; 引擎: ${stronger.engines.join(', ') || '未知'})`,
    );
    try {
      return done(await renderHtml(stronger.recommended));
    } catch (retryErr) {
      throw new Error(`${firstError.message}; 改用 ${stronger.recommended} 重试后仍失败: ${retryErr.message}`);
    }
  };
  // render="always"：静态 200 也照样渲染。客户端渲染页的正文在水合后才进 DOM，
  // 静态抓到的 HTML 是 200 却没有正文，只按 403/5xx 回退永远等不到渲染。
  if (remote && render === 'always') {
    return await renderWithEscalation();
  }
  if (!remote || !render) {
    return done(guardBlocked(await readSource(source, { timeoutMs, proxy })));
  }
  try {
    return done(guardBlocked(await readSource(source, { timeoutMs, proxy })));
  } catch (e) {
    // 403/5xx，或静态 200 但正文就是拒绝页：都换渲染通路再试一次。
    if (!isRenderableError(e) && !e?.blockPage) throw e;
    // 记下静态阶段的状态码：渲染后状态码未知时，日志能说明"静态 403 才转渲染"。
    if (Number.isFinite(e.statusCode)) info.staticStatus = e.statusCode;
    return await renderWithEscalation();
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

/**
 * 把本次实际用于提取的 HTML（静态抓取的原文或浏览器渲染后的原文）落盘，并写同名
 * `.meta.json` 记下源 URL 与是否走过渲染，供后续任一模式复用（等价于"渲染一次、多视图"）。
 *
 * 为什么落盘原文而不是 `--mode html` 的清洗产物：清洗去掉 class/id/role 等信号后，
 * Defuddle 的样板剪裁与 ui 清单会变化（实测同一页 markdown 由 1313 字符变 2363，
 * `--attrs none` 时 ui 清单少近一半），相对链接也会失去 URL 基准变成 file:///。
 * 落盘位置与是否渲染由调用方决定；非 URL 输入返回 null，由调用方提示。
 */
export async function saveSourceHtml(html, { source, outPath, rendered = false, contentType = null } = {}) {
  if (!outPath || !/^https?:\/\//i.test(source ?? '')) return null;
  const bytes = Buffer.byteLength(html, 'utf8');
  await writeFile(outPath, html, 'utf8');
  // 同一份 URL 基准要跟着走，否则后续本地提取会把相对链接解析成 file:///。
  const meta = {
    url: source,
    savedBy: `htmlmini/${VERSION}`,
    savedAt: new Date().toISOString(),
    rendered: rendered === true,
    contentType: contentType ?? 'text/html',
    bytes,
  };
  await writeFile(`${outPath}.meta.json`, `${JSON.stringify(meta, null, 2)}\n`, 'utf8');
  log.info('write', `saved source HTML ${outPath} (${fmtBytes(bytes)}${rendered ? ', browser render' : ', static fetch'})`);
  return outPath;
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
// ui / semantic 用 textContent 收集文本，script/style 的源码会被当成正文
// （叶子 div 包一层 script 时尤其明显）。取内容前先删这些非内容标签，与 html 模式同口径。
const NON_CONTENT_TAGS = 'script,style,noscript,template';

function stripNonContent(doc) {
  for (const el of doc.querySelectorAll(NON_CONTENT_TAGS)) el.remove();
}

// CSS 生成内容（::before / ::after 的 content）不在 DOM 文本里，textContent 取不到。
// 价格/计量类页面常把小数点做成 `content:"."`（DOM 里是 `$`+`1`+`00`），
// 不并入就会把 $1.00 读成 $100。只并短标点，避免把图标字体的私有区字符塞进正文。
const CSS_CONTENT_SAFE = /^[\s.,:;/|$%()\[\]-]{1,3}$/;
const CSS_CONTENT_MAX_INSERTIONS = 500;
const CSS_MAX_FILES = 5;
const CSS_MAX_BYTES = 2 * 1024 * 1024;

async function fetchCssText(url, { proxy, timeoutMs = 5000 } = {}) {
  const proxyUrl = resolveProxy(url, { proxy });
  const dispatcher = proxyUrl ? proxyDispatcher(proxyUrl) : null;
  const res = await fetchOnce(url, {
    headers: { 'user-agent': DEFAULT_UA, accept: 'text/css,*/*;q=0.1' },
    timeoutMs,
    dispatcher,
  });
  if (!res.ok) return '';
  // 路径写错时站点常回落到 HTML 首页，别把它当样式表解析。
  const ct = res.headers.get('content-type') || '';
  if (/text\/html/i.test(ct)) return '';
  return decodeHtml(Buffer.from(await res.arrayBuffer()));
}

/**
 * 把 ::before / ::after 的短标点 content 并入 DOM 文本。
 * - 始终读页面自带的 <style>（本地文件也适用）；
 * - fetchExternal（浏览器渲染通路）时再读外链 CSS，同一代理、限文件数与总字节；
 * - 只认 1~3 个安全标点，跳过 `\e900` 图标、url()、attr()、counter() 与空串；
 * - 同一元素同一侧只并一次，避免多条规则重复插入。
 */
async function inlineGeneratedContent(document, { baseUrl, fetchExternal = false, proxy, timeoutMs } = {}) {
  const sheets = [];
  for (const el of document.querySelectorAll('style')) sheets.push(el.textContent || '');
  if (fetchExternal && /^https?:/i.test(baseUrl || '')) {
    // 相对 CSS 路径要按文档的 <base href> 解析（SPA 常用 <base href="/">）。
    let docBase = baseUrl;
    const baseHref = document.querySelector('base[href]')?.getAttribute('href');
    if (baseHref) {
      try {
        docBase = new URL(baseHref, baseUrl).href;
      } catch {
        docBase = baseUrl;
      }
    }
    let budget = CSS_MAX_BYTES;
    const links = [...document.querySelectorAll('link[rel~="stylesheet"][href]')].slice(0, CSS_MAX_FILES);
    for (const link of links) {
      if (budget <= 0) break;
      let abs;
      try {
        abs = new URL(link.getAttribute('href'), docBase).href;
      } catch {
        continue;
      }
      if (!/^https?:/i.test(abs)) continue;
      // 只取同源样式表：跨域 CSS 通常只影响地图/第三方控件，白花抓取时间。
      try {
        if (new URL(abs).host !== new URL(baseUrl).host) continue;
      } catch {
        continue;
      }
      try {
        const css = await fetchCssText(abs, { proxy, timeoutMs });
        if (!css || css.length > budget) continue;
        budget -= css.length;
        sheets.push(css);
      } catch {
        // 样式表取不到不影响正文提取
      }
    }
  }
  const applied = new WeakMap();
  let inserted = 0;
  log.debug('extract', `css sheets=${sheets.length} bytes=${sheets.reduce((n, s) => n + s.length, 0)}`);
  for (const css of sheets) {
    if (inserted >= CSS_CONTENT_MAX_INSERTIONS) break;
    const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = /([^{}]+)\{([^{}]*)\}/g;
    let m;
    while ((m = rule.exec(clean)) && inserted < CSS_CONTENT_MAX_INSERTIONS) {
      const cm = /(?:^|;)\s*content\s*:\s*(['"])([\s\S]*?)\1/.exec(m[2]);
      if (!cm) continue;
      const value = cm[2];
      if (!value || !CSS_CONTENT_SAFE.test(value)) continue;
      for (const rawSelector of m[1].split(',')) {
        if (inserted >= CSS_CONTENT_MAX_INSERTIONS) break;
        const sel = rawSelector.trim();
        const pm = /::?(before|after)\s*$/i.exec(sel);
        if (!pm) continue;
        const pos = pm[1].toLowerCase();
        const base = sel.slice(0, pm.index).trim();
        if (!base || base.includes('@')) continue;
        let els;
        try {
          els = document.querySelectorAll(base);
        } catch {
          continue;
        }
        for (const el of els) {
          const done = applied.get(el) ?? new Set();
          if (done.has(pos)) continue;
          done.add(pos);
          applied.set(el, done);
          const node = document.createTextNode(value);
          if (pos === 'before') el.insertBefore(node, el.firstChild);
          else el.appendChild(node);
          if (++inserted >= CSS_CONTENT_MAX_INSERTIONS) break;
        }
      }
    }
  }
  return inserted;
}


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
 *
 * textMax 控制单条文本上限（默认 150）：超长段落（商品描述、FAQ 正文、条款）
 * 若整条丢弃，长文本页会只剩标题却看不出原因，所以丢弃时在输出里记账。
 * 传 0 表示不限制（长正文页需要完整段落时用）。
 */
export function uiSkeleton(doc, { textMax = 150 } = {}) {
  stripNonContent(doc);
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
  let droppedLong = 0;
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
    if (t.length < 2 || /^[0-9\s%.,]+$/.test(t)) continue;
    if (textMax > 0 && t.length > textMax) {
      droppedLong++;
      continue;
    }
    dedupeInsert(uniqueTexts, t);
  }
  if (uniqueTexts.length) {
    out.push('', '## 文本');
    uniqueTexts.forEach((t) => out.push(`- ${t}`));
  }
  // 静默丢弃最容易导致"页面没有正文"的误判：长段落被上限挡掉时明说，并给出出路。
  if (droppedLong) {
    out.push(
      '',
      `> 已省略 ${droppedLong} 条超过 ${textMax} 字符的长文本（ui 清单的单条上限）。需要完整长正文改用 \`--mode markdown\` / \`--mode text\`，或加 \`--text-max 0\` 取消上限。`,
    );
  }
  return out.join('\n');
}

/** 纯 JS 语义回退：取 main/article/[role=main] 候选区的标题与叶子文本流。 */
export function semanticFallback(doc) {
  stripNonContent(doc);
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
export async function extractHtml(html, { url = 'about:blank', extractor = 'auto', contentType = null, attrs = 'semantic', format = 'compact', pruneEmpty = false, textMax = 150, fetchCss = false, proxy, pythonBin } = {}) {
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
      version: VERSION,
      contentType: contentType ?? null,
      content: text,
      stats: {
        inputChars: raw.length,
        outputChars: text.length,
        reductionPct: raw.length ? Math.round((1 - text.length / raw.length) * 1000) / 10 : 0,
        parseMs: Date.now() - t0,
        cssGenerated: 0,
      },
    };
  };

  if (extractor === 'passthrough') return finishPassthrough();
  if (!looksLikeHtml(raw, contentType)) return finishPassthrough();

  const tParse = Date.now();
  const document = parseOnce(raw);
  log.info('parse', `dom ${fmtMs(Date.now() - tParse)}`);

  // CSS 生成内容先并入 DOM，后续 textContent / Defuddle / ui 都能看到
  //（价格里用 ::before 画小数点这类页面的主要失真来源）。
  const cssGenerated = await inlineGeneratedContent(document, { baseUrl: url, fetchExternal: fetchCss, proxy });
  if (cssGenerated) log.debug('extract', `css-generated text +${cssGenerated}`);

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
      version: VERSION,
      content,
      stats: {
        inputChars: html.length,
        outputChars: content.length,
        reductionPct: html.length ? Math.round((1 - content.length / html.length) * 1000) / 10 : 0,
        parseMs: Date.now() - t0,
        cssGenerated,
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
    return finish(uiSkeleton(document, { textMax }), 'ui');
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

  return finish(uiSkeleton(document, { textMax }), 'ui', defuddle ?? {});
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

/**
 * 正文与 HTML 体积严重不成比例时，多半是客户端渲染的应用壳 / 加载页：
 * 静态抓取 200 但正文要等水合，或站点直接返回离线页。此时静默输出几十字节
 * 会让调用方把“壳”当成页面内容，所以默认报错并指向 --render=always；
 * title / skeleton 只取元数据或大纲，不受此检查约束。
 */
export function assertUsableResult(res, htmlChars, { allowEmpty = false, mode = 'markdown' } = {}) {
  if (allowEmpty || mode === 'title' || mode === 'skeleton') return;
  if (res.used === 'passthrough') return;
  const outChars = String(res.content ?? '').length;
  if (outChars >= 200 || htmlChars < 5000) return;
  if (outChars / htmlChars >= 0.015) return;
  const pct = ((outChars / htmlChars) * 100).toFixed(1);
  throw new Error(
    `extracted only ${outChars} B from ${fmtBytes(htmlChars)} HTML (${pct}%): the page looks like a client-rendered app shell or loading page. ` +
      'Retry with --render=always (MCP render:"always") so the body is hydrated before extraction; ' +
      'pass --allow-empty if the page really is this short.',
  );
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

export async function runExtract(source, mode = 'markdown', options = {}) {
  const { output } = await runExtractDetailed(source, mode, options);
  return output;
}

/**
 * 与 runExtract 相同，但把来源信息（URL、状态码、是否渲染、抓取时刻）一起返回，
 * 供调用方做来源标记或 JSON 字段；CLI 用它生成起止行。
 */
export async function runExtractDetailed(source, mode = 'markdown', { forceContent, extractor = 'auto', attrs = 'semantic', format = 'compact', pruneEmpty = false, textMax = 150, allowEmpty = false, timeoutMs, proxy, render = false, renderTimeoutMs, headful = false, chromeBin, browserBrand, pythonBin, renderEngine, cdpUrl, saveHtml } = {}) {
  if (!MODES.includes(mode)) {
    throw new Error(`unknown mode "${mode}"（可选: ${MODES.join(', ')}）`);
  }
  let html;
  let src;
  let sibling = null;
  let contentType = null;
  let rendered = false;
  let fetchStatus = null;
  let engine = null;
  let fetchedAt = null;
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
        ...(render ? { render } : {}),
        ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
        ...(headful ? { headful: true } : {}),
        ...(chromeBin == null ? {} : { chromeBin }),
        ...(browserBrand == null ? {} : { browserBrand }),
        ...(pythonBin == null ? {} : { pythonBin }),
        ...(renderEngine == null ? {} : { renderEngine }),
        ...(cdpUrl == null ? {} : { cdpUrl }),
        allowEmpty,
      },
    );
    html = r.html;
    src = r.source;
    contentType = r.contentType ?? guessContentTypeFromPath(src);
    rendered = r.rendered === true;
    fetchStatus = Number.isFinite(r.status) ? r.status : null;
    engine = r.engine ?? null;
    if (saveHtml) {
      // 落盘放在校验之前：即使随后被判挑战页/空壳而报错，抓到的原文仍可复用与诊断。
      const saved = await saveSourceHtml(html, { source: src, outPath: saveHtml, rendered, contentType });
      if (!saved) {
        log.info('write', `--save-html only applies to URL input (got ${src === 'stdin' ? 'stdin' : 'a local file'}); nothing written`);
      }
    }
    if (!/^https?:\/\//i.test(src) && src !== 'stdin') {
      sibling = await readSiblingMeta(src);
    }
  }
  const url = /^https?:/i.test(src)
    ? src
    : sibling && /^https?:/i.test(sibling.url)
      ? sibling.url
      : 'file:///' + (src === 'stdin' || src === 'content' ? src : src.replaceAll('\\', '/'));
  // 取到内容之后再记时刻：哨兵行的 fetched 表示"这份载荷什么时候拿到的"，不是命令启动时间。
  fetchedAt = timestamp();
  const res = await extractHtml(html, { url, extractor: mode === 'ui' ? 'ui' : mode === 'html' ? 'sanitize' : extractor, contentType, attrs, format, pruneEmpty, textMax, fetchCss: rendered || Boolean(sibling && /^https?:/i.test(sibling.url)), ...(proxy === undefined ? {} : { proxy }), ...(pythonBin == null ? {} : { pythonBin }) });
  assertUsableResult(res, html.length, { allowEmpty, mode });
  log.debug('extract', `mode=${mode} requested=${res.requested} used=${res.used} reduction=${res.stats.reductionPct}% title="${res.title ?? ''}"`);
  if (sibling) res.meta = sibling.meta;
  const info = { source: url, status: fetchStatus, rendered, engine, fetchedAt, mode };
  if (mode === 'json') {
    // JSON 模式下哨兵行会破坏可解析性，来源改由字段承载（与文本模式的起止行等价）。
    res.source = url;
    res.fetchStatus = fetchStatus;
    res.rendered = rendered;
    res.fetchedAt = fetchedAt;
    if (engine) res.engine = engine;
  }
  return { output: renderResult(res, mode), info };
}
