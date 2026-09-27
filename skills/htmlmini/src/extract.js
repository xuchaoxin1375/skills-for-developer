import { readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { parseHTML } from 'linkedom';
import { Defuddle } from 'defuddle/node';

const execFileAsync = promisify(execFile);

export const MODES = ['markdown', 'skeleton', 'text', 'json', 'title', 'ui'];
export const EXTRACTORS = ['auto', 'defuddle', 'trafilatura', 'semantic', 'ui'];

export const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15 htmlmini/0.2';

const MIN_ARTICLE_CHARS = 50;
const UI_SWITCH_CHARS = 300;
const TRAFILATURA_TIMEOUT_MS = 15000;

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

export async function readSource(source) {
  if (source === '-' || source == null) {
    return { html: decodeHtml(await readStdin()), source: 'stdin' };
  }
  if (/^https?:\/\//i.test(source)) {
    const res = await fetch(source, {
      headers: { 'user-agent': DEFAULT_UA, 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8' },
      redirect: 'follow',
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${source}`);
    return { html: decodeHtml(Buffer.from(await res.arrayBuffer())), source };
  }
  return { html: decodeHtml(await readFile(source)), source };
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

/** 去重：完全相同或互相包含时保留较长者（输入已截断，O(n^2) 可接受）。 */
function dedupe(items) {
  const unique = [];
  for (const t of items) {
    const i = unique.findIndex((u) => u === t || u.includes(t) || t.includes(u));
    if (i >= 0) {
      if (t.length > unique[i].length) unique[i] = t;
    } else {
      unique.push(t);
    }
  }
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
 * UI 组件清单（v2：按可访问语义重写）。
 * 只认语义标签/ARIA，不再用 class*="btn" 之类正则猜，避免样式类误伤。
 */
export function uiSkeleton(doc) {
  const out = [];
  const title = doc.title || '(no title)';
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

  const links = [];
  for (const a of doc.querySelectorAll('a[href]')) {
    if (links.length >= CAP.links) break;
    if (typeof a.getAttribute === 'function' && a.getAttribute('role') === 'button') continue;
    const t = collectText(a);
    if (!t || t.length > 80) continue;
    const href = truncate(a.getAttribute('href') || '', 80);
    links.push(href && href !== t ? `${t} (${href})` : t);
  }
  if (links.length) {
    out.push('', '## 链接');
    dedupe(links).slice(0, CAP.links).forEach((l) => out.push(`- ${truncate(l, 160)}`));
  }

  const texts = [];
  for (const el of doc.querySelectorAll('p,li,td,th,div,span')) {
    if (texts.length >= CAP.texts) break;
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
    if (t.length >= 2 && t.length <= 150 && !/^[0-9\s%.,]+$/.test(t)) texts.push(t);
  }
  const uniqueTexts = dedupe(texts);
  if (uniqueTexts.length) {
    out.push('', '## 文本');
    uniqueTexts.slice(0, CAP.texts).forEach((t) => out.push(`- ${t}`));
  }
  return out.join('\n');
}

/** 纯 JS 语义回退：取 main/article/[role=main] 候选区的标题与叶子文本流。 */
export function semanticFallback(doc) {
  const root =
    doc.querySelector('main,article,[role="main"]') || doc.querySelector('body') || doc;
  const out = [`# ${doc.title || '(no title)'}`];
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
  return parseHTML(html).document;
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
 * 可选的 Trafilatura 增强：本机有 Python + trafilatura 模块时才生效，
 * 否则静默返回 { ok: false }，调用方继续走下一级回退。
 */
export async function tryTrafilatura(html) {
  for (const bin of ['python3', 'python']) {
    try {
      const { stdout } = await execFileAsync(bin, ['-c', TRAFILATURA_PY], {
        input: html,
        timeout: TRAFILATURA_TIMEOUT_MS,
        maxBuffer: 32 * 1024 * 1024,
        windowsHide: true,
      });
      const text = (stdout || '').trim();
      return text ? { ok: true, text } : { ok: false };
    } catch (e) {
      if (e && typeof e.code === 'number') {
        // 进程已启动：2 = 缺模块，3 = 抽不出正文。
        return { ok: false, missing: e.code === 2 };
      }
      // ENOENT 等启动失败：换下一个候选解释器。
    }
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

/**
 * 回退链：auto = Defuddle -> Trafilatura(可选) -> semantic -> ui。
 * 强制指定 extractor 时返回该引擎的原始结果（不静默切换），便于排查。
 */
export async function extractHtml(html, { url = 'about:blank', extractor = 'auto' } = {}) {
  if (!EXTRACTORS.includes(extractor)) {
    throw new Error(`unknown extractor "${extractor}"（可选: ${EXTRACTORS.join(', ')}）`);
  }
  const t0 = Date.now();
  const document = parseOnce(html);

  const finish = (content, used, base = {}) => ({
    title: base.title ?? document.title ?? '',
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
  });

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
    const alt = await tryTrafilatura(html);
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

  const alt = await tryTrafilatura(html);
  if (alt.ok && alt.text.length >= MIN_ARTICLE_CHARS) {
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

export async function runExtract(source, mode = 'markdown', { forceContent, extractor = 'auto' } = {}) {
  if (!MODES.includes(mode)) {
    throw new Error(`unknown mode "${mode}"（可选: ${MODES.join(', ')}）`);
  }
  let html;
  let src;
  let sibling = null;
  if (forceContent != null) {
    html = forceContent;
    src = 'content';
  } else {
    const r = await readSource(source);
    html = r.html;
    src = r.source;
    if (!/^https?:\/\//i.test(src) && src !== 'stdin') {
      sibling = await readSiblingMeta(src);
    }
  }
  const url = /^https?:/i.test(src)
    ? src
    : sibling && /^https?:/i.test(sibling.url)
      ? sibling.url
      : 'file:///' + (src === 'stdin' || src === 'content' ? src : src.replaceAll('\\', '/'));
  const res = await extractHtml(html, { url, extractor: mode === 'ui' ? 'ui' : extractor });
  if (sibling) res.meta = sibling.meta;
  return renderResult(res, mode);
}
