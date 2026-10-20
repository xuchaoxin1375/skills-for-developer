#!/usr/bin/env node
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { ATTR_POLICIES, EXTRACTORS, FORMAT_POLICIES, MODES, RENDER_ENGINE_CHOICES, assertUsableResult, extractHtml, readSiblingMeta, readWithRender, runExtract, renderResult, saveSourceHtml } from './extract.js';
import { log } from './log.js';
import { VERSION } from './version.js';

const modeEnum = z.enum(MODES);
const extractorEnum = z.enum(EXTRACTORS);
const attrsEnum = z.enum(ATTR_POLICIES);
const formatEnum = z.enum(FORMAT_POLICIES);
const extractorDesc =
  'Extraction engine. Default: auto (non-HTML passthrough -> Defuddle -> Trafilatura if installed, silently skipped otherwise -> semantic -> UI inventory). Non-HTML input is passed through untouched; force one to get its raw result without silent switching.';
const modeDesc =
  'Output style. Default: markdown. "html" returns cleaned HTML: full DOM structure and text order kept, scripts/styles/templates/icons/comments dropped. Higher token cost than markdown or the UI inventory, but nothing is truncated — use it when structure (tables, form state, nesting) matters.';
const attrsDesc =
  'Attribute policy, only meaningful for mode "html". semantic (default): keep href/src/alt/title/colspan/rowspan/scope and table/form state; drop class/style/id/data-*/aria-*. none: strip every attribute (smallest, but loses link targets and merged cells). all: keep every attribute, only drop scripts/styles.';
const formatDesc =
  'Layout policy, only meaningful for mode "html". compact (default): drop source indentation and blank lines, keeping a single space between inline elements (smallest; nothing is reordered). pretty: re-indent for readability. raw: keep the original source whitespace.';
const pruneEmptyDesc =
  'Only meaningful for mode "html". Drop containers left empty after cleaning (empty div/span/nav/header ...), which is often most of the bytes; table/form/pre structure is kept. Default false: empty wrappers are preserved.';
const textMaxDesc =
  'Only meaningful for mode "ui" (or extractor "ui"): max characters for a single text entry. Default 150. Longer paragraphs (product descriptions, FAQ bodies, terms) are dropped from the inventory and the output reports how many were skipped. Set 0 for no limit — use that when the UI inventory is the only view and long paragraphs matter.';
const allowEmptyDesc =
  'Keep the result even when it looks like a client-rendered app shell (extracted text under 200 chars from >= 5 KB HTML). Default false: such pages return an error telling you to use render:"always", because the static HTML has no body yet.';

async function handleSource(src, { mode, extractor, attrs, format, pruneEmpty, textMax, allowEmpty, proxy, render, renderTimeoutMs, headful, chromeBin, pythonBin, renderEngine, saveHtml }) {
  const { html, source, contentType, rendered } = await readWithRender(
    src,
    {
      ...(proxy === undefined ? {} : { proxy }),
      ...(render ? { render } : {}),
      ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
      ...(headful ? { headful: true } : {}),
      ...(chromeBin == null ? {} : { chromeBin }),
      ...(pythonBin == null ? {} : { pythonBin }),
      ...(renderEngine == null ? {} : { renderEngine }),
      allowEmpty: allowEmpty === true,
    },
  );
  if (saveHtml) {
    // 与 CLI 同口径：校验之前先落盘原文，挑战空壳报错时也留得下可复用的文件。
    const saved = await saveSourceHtml(html, { source, outPath: saveHtml, rendered: rendered === true, contentType });
    if (!saved) log.info('write', `save_html only applies to URL input (got ${source === 'stdin' ? 'stdin' : 'a local file'}); nothing written`);
  }
  const sibling = await readSiblingMeta(source);
  const url = /^https?:/i.test(source)
    ? source
    : sibling && /^https?:/i.test(sibling.url)
      ? sibling.url
      : 'file:///' + (source === 'stdin' ? 'stdin' : source.replaceAll('\\', '/'));
  const res = await extractHtml(html, { url, extractor, contentType, attrs, format, pruneEmpty, textMax, fetchCss: rendered === true, ...(proxy === undefined ? {} : { proxy }), ...(pythonBin == null ? {} : { pythonBin }) });
  assertUsableResult(res, html.length, { allowEmpty, mode });
  if (sibling) res.meta = sibling.meta;
  return renderResult(res, mode);
}

const server = new McpServer({
  name: 'htmlmini',
  version: VERSION,
});

const fileDesc =
  'Extract the core content of a local HTML file, stripping CSS/JS/boilerplate. Works for static files, design mockups, and browser-rendered pages saved by resilient-browser-fetch (a "<file>.meta.json" next to the HTML is auto-used for the page URL). Article pages use Defuddle; dashboards/UI design pages automatically fall back to a UI-component inventory (headings, landmarks, fields, buttons, tables). Use mode "json" when you need metadata + which extractor was used + token-savings stats.';
const urlDesc =
  'Fetch a URL then extract its core content as Markdown, stripping CSS/JS/ads/nav (built on Defuddle + schema.org metadata). Static fetch only by default: follows HTTP(S)_PROXY env (NO_PROXY exempt) unless "proxy" overrides; retries once with browser headers on 403/5xx and names challenge signs in the error. Set "render" to fall back to browser rendering (resilient-browser-fetch save_page, same proxy) on static 403/5xx — needs a layer >= 1 engine (playwright/patchright, scrapling, or cloak-cdp) installed. For JS-heavy pages you can also render first yourself, then feed the saved HTML to htmlmini_extract_file. Use "skeleton" for huge pages or "json" when you need metadata + token-savings stats.';
const htmlDesc =
  'Clean raw HTML given as a string (e.g. page source a harness already fetched): returns only the core content as Markdown so the model can summarize it without burning tokens on CSS/JS.';

const shapeFile = {
  path: z.string().describe('Absolute path to a local .html file'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
  attrs: attrsEnum.optional().describe(attrsDesc),
  format: formatEnum.optional().describe(formatDesc),
  prune_empty: z.boolean().optional().describe(pruneEmptyDesc),
  text_max: z.number().optional().describe(textMaxDesc),
  allow_empty: z.boolean().optional().describe(allowEmptyDesc),
};
const shapeUrl = {
  url: z.string().describe('http(s) URL'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
  attrs: attrsEnum.optional().describe(attrsDesc),
  format: formatEnum.optional().describe(formatDesc),
  prune_empty: z.boolean().optional().describe(pruneEmptyDesc),
  text_max: z.number().optional().describe(textMaxDesc),
  allow_empty: z.boolean().optional().describe(allowEmptyDesc),
  proxy: z
    .string()
    .optional()
    .describe('Proxy override for this fetch: http(s) URL, or "direct" to bypass env proxy. Omit to follow HTTP_PROXY/HTTPS_PROXY/NO_PROXY env.'),
  render: z
    .union([z.boolean(), z.literal('always')])
    .optional()
    .describe('Browser rendering. false (default): static fetch only. true: on static 403/5xx, fall back to browser rendering via resilient-browser-fetch save_page (same proxy as this fetch), then extract. "always": render even when the static fetch returns 200 — use it for client-rendered pages whose HTML is 200 but whose body only exists after hydration. Needs an installed engine at layer >= 1 (playwright/patchright, scrapling, or cloak-cdp); bounded by its own timeout.'),
  render_timeout_ms: z
    .number()
    .optional()
    .describe('Timeout in ms for the fallback browser render (default 300000). Only used when render is true.'),
  headful: z
    .boolean()
    .optional()
    .describe('Show the browser window during the fallback render (default headless). Useful for first-time manual verification; logs still stream to stderr.'),
  chrome_bin: z
    .string()
    .optional()
    .describe('Explicit Chrome/Chromium binary for the zero-dep chrome fallback (overrides auto-detection: PATH, common paths, Playwright cache).'),
  python_bin: z
    .string()
    .optional()
    .describe('Explicit Python interpreter for the render fallback and the optional Trafilatura pass. Default is "python"/"python3" on PATH, which is often not the environment that has playwright/scrapling installed; also read from HTMLMINI_PYTHON. Use "auto" to scan this machine (conda/venv/uv/PATH) and pick an interpreter that has a layer >= 1 engine. When no explicit value is given, a failed render is retried once with the strongest interpreter the scan finds (layer >= 2, i.e. a challenge solver, preferred).'),
  save_html: z
    .string()
    .optional()
    .describe('Absolute path: write the HTML actually used for extraction (static fetch, or the rendered page when render is on) plus a sibling "<path>.meta.json" holding the page URL. Reuse that file with htmlmini_extract_file for other modes instead of re-fetching or re-rendering. Raw HTML (not the cleaned "html" mode output), written before content validation so it survives a challenge-shell error. URL input only.'),
  render_engine: z
    .enum(RENDER_ENGINE_CHOICES)
    .optional()
    .describe('Pin the save_page engine instead of letting it auto-upgrade: "auto" (default) tries every installed layer from the lowest; an explicit layer (playwright | scrapling | cloak-cdp) runs that engine only — a missing layer fails instead of falling back. Use it on an origin you already know needs layer 2, to skip the attempts that are known to be rejected.'),
};
const shapeHtml = {
  html_content: z.string().describe('Raw HTML source code string'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
  attrs: attrsEnum.optional().describe(attrsDesc),
  format: formatEnum.optional().describe(formatDesc),
  prune_empty: z.boolean().optional().describe(pruneEmptyDesc),
  text_max: z.number().optional().describe(textMaxDesc),
  allow_empty: z.boolean().optional().describe(allowEmptyDesc),
};

// 正确命名（v2）。旧拼写 htmmini_* 保留为别名以兼容已配置的客户端。
server.tool('htmlmini_extract_file', fileDesc, shapeFile, async ({ path, mode, extractor, attrs, format, prune_empty, text_max, allow_empty }) => ({
  content: [{ type: 'text', text: await handleSource(path, { mode: mode ?? 'markdown', extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic', format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false }) }],
}));

server.tool('htmlmini_extract_url', urlDesc, shapeUrl, async ({ url, mode, extractor, attrs, format, prune_empty, text_max, allow_empty, proxy, render, render_timeout_ms, headful, chrome_bin, python_bin, save_html, render_engine }) => ({
  content: [{
    type: 'text',
    text: await handleSource(url, {
      mode: mode ?? 'markdown', extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic',
      format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false,
      proxy, render: render ?? false, renderTimeoutMs: render_timeout_ms, headful: headful ?? false, chromeBin: chrome_bin, pythonBin: python_bin, saveHtml: save_html, renderEngine: render_engine,
    }),
  }],
}));

server.tool('htmlmini_extract_html', htmlDesc, shapeHtml, async ({ html_content, mode, extractor, attrs, format, prune_empty, text_max, allow_empty }) => ({
  content: [{ type: 'text', text: await runExtract(null, mode ?? 'markdown', { forceContent: html_content, extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic', format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false }) }],
}));

const aliasNote = 'Deprecated alias of the htmlmini_* tool (kept for backward compatibility).';
server.tool('htmmini_extract_file', `${aliasNote} ${fileDesc}`, shapeFile, async ({ path, mode, extractor, attrs, format, prune_empty, text_max }) => ({
  content: [{ type: 'text', text: await handleSource(path, { mode: mode ?? 'markdown', extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic', format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false }) }],
}));

server.tool('htmmini_extract_url', `${aliasNote} ${urlDesc}`, shapeUrl, async ({ url, mode, extractor, attrs, format, prune_empty, text_max, allow_empty, proxy, render, render_timeout_ms, headful, chrome_bin, python_bin }) => ({
  content: [{
    type: 'text',
    text: await handleSource(url, {
      mode: mode ?? 'markdown', extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic',
      format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false,
      proxy, render: render ?? false, renderTimeoutMs: render_timeout_ms, headful: headful ?? false, chromeBin: chrome_bin, pythonBin: python_bin,
    }),
  }],
}));

server.tool('htmmini_extract_html', `${aliasNote} ${htmlDesc}`, shapeHtml, async ({ html_content, mode, extractor, attrs, format, prune_empty, text_max, allow_empty }) => ({
  content: [{ type: 'text', text: await runExtract(null, mode ?? 'markdown', { forceContent: html_content, extractor: extractor ?? 'auto', attrs: attrs ?? 'semantic', format: format ?? 'compact', pruneEmpty: prune_empty ?? false, textMax: text_max, allowEmpty: allow_empty ?? false }) }],
}));

await server.connect(new StdioServerTransport());
