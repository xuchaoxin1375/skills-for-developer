#!/usr/bin/env node
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { EXTRACTORS, MODES, extractHtml, readSiblingMeta, readWithRender, runExtract, renderResult } from './extract.js';

const modeEnum = z.enum(MODES);
const extractorEnum = z.enum(EXTRACTORS);
const extractorDesc =
  'Extraction engine. Default: auto (non-HTML passthrough -> Defuddle -> Trafilatura if installed, silently skipped otherwise -> semantic -> UI inventory). Non-HTML input is passed through untouched; force one to get its raw result without silent switching.';
const modeDesc = 'Output style. Default: markdown';

async function handleSource(src, mode, extractor, proxy, render, renderTimeoutMs, headful, chromeBin) {
  const { html, source, contentType } = await readWithRender(
    src,
    {
      ...(proxy === undefined ? {} : { proxy }),
      ...(render ? { render: true } : {}),
      ...(renderTimeoutMs == null ? {} : { renderTimeoutMs }),
      ...(headful ? { headful: true } : {}),
      ...(chromeBin == null ? {} : { chromeBin }),
    },
  );
  const sibling = await readSiblingMeta(source);
  const url = /^https?:/i.test(source)
    ? source
    : sibling && /^https?:/i.test(sibling.url)
      ? sibling.url
      : 'file:///' + (source === 'stdin' ? 'stdin' : source.replaceAll('\\', '/'));
  const res = await extractHtml(html, { url, extractor, contentType });
  if (sibling) res.meta = sibling.meta;
  return renderResult(res, mode);
}

const server = new McpServer({
  name: 'htmlmini',
  version: '0.2.0',
});

const fileDesc =
  'Extract the core content of a local HTML file, stripping CSS/JS/boilerplate. Works for static files, design mockups, and browser-rendered pages saved by resilient-browser-fetch (a "<file>.meta.json" next to the HTML is auto-used for the page URL). Article pages use Defuddle; dashboards/UI design pages automatically fall back to a UI-component inventory (headings, landmarks, fields, buttons, tables). Use mode "json" when you need metadata + which extractor was used + token-savings stats.';
const urlDesc =
  'Fetch a URL then extract its core content as Markdown, stripping CSS/JS/ads/nav (built on Defuddle + schema.org metadata). Static fetch only by default: follows HTTP(S)_PROXY env (NO_PROXY exempt) unless "proxy" overrides; retries once with browser headers on 403/5xx and names challenge signs in the error. Set "render" to fall back to browser rendering (resilient-browser-fetch save_page, same proxy) on static 403/5xx — needs its Python env installed. For JS-heavy pages you can also render first yourself, then feed the saved HTML to htmlmini_extract_file. Use "skeleton" for huge pages or "json" when you need metadata + token-savings stats.';
const htmlDesc =
  'Clean raw HTML given as a string (e.g. page source a harness already fetched): returns only the core content as Markdown so the model can summarize it without burning tokens on CSS/JS.';

const shapeFile = {
  path: z.string().describe('Absolute path to a local .html file'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
};
const shapeUrl = {
  url: z.string().describe('http(s) URL'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
  proxy: z
    .string()
    .optional()
    .describe('Proxy override for this fetch: http(s) URL, or "direct" to bypass env proxy. Omit to follow HTTP_PROXY/HTTPS_PROXY/NO_PROXY env.'),
  render: z
    .boolean()
    .optional()
    .describe('On static 403/5xx, fall back to browser rendering via resilient-browser-fetch save_page (same proxy as this fetch), then extract. Needs its Python env installed; bounded by its own timeout.'),
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
};
const shapeHtml = {
  html_content: z.string().describe('Raw HTML source code string'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
};

// 正确命名（v2）。旧拼写 htmmini_* 保留为别名以兼容已配置的客户端。
server.tool('htmlmini_extract_file', fileDesc, shapeFile, async ({ path, mode, extractor }) => ({
  content: [{ type: 'text', text: await handleSource(path, mode ?? 'markdown', extractor ?? 'auto') }],
}));

server.tool('htmlmini_extract_url', urlDesc, shapeUrl, async ({ url, mode, extractor, proxy, render, render_timeout_ms, headful, chrome_bin }) => ({
  content: [{ type: 'text', text: await handleSource(url, mode ?? 'markdown', extractor ?? 'auto', proxy, render ?? false, render_timeout_ms, headful ?? false, chrome_bin) }],
}));

server.tool('htmlmini_extract_html', htmlDesc, shapeHtml, async ({ html_content, mode, extractor }) => ({
  content: [{ type: 'text', text: await runExtract(null, mode ?? 'markdown', { forceContent: html_content, extractor: extractor ?? 'auto' }) }],
}));

const aliasNote = 'Deprecated alias of the htmlmini_* tool (kept for backward compatibility).';
server.tool('htmmini_extract_file', `${aliasNote} ${fileDesc}`, shapeFile, async ({ path, mode, extractor }) => ({
  content: [{ type: 'text', text: await handleSource(path, mode ?? 'markdown', extractor ?? 'auto') }],
}));

server.tool('htmmini_extract_url', `${aliasNote} ${urlDesc}`, shapeUrl, async ({ url, mode, extractor, proxy, render, render_timeout_ms, headful, chrome_bin }) => ({
  content: [{ type: 'text', text: await handleSource(url, mode ?? 'markdown', extractor ?? 'auto', proxy, render ?? false, render_timeout_ms, headful ?? false, chrome_bin) }],
}));

server.tool('htmmini_extract_html', `${aliasNote} ${htmlDesc}`, shapeHtml, async ({ html_content, mode, extractor }) => ({
  content: [{ type: 'text', text: await runExtract(null, mode ?? 'markdown', { forceContent: html_content, extractor: extractor ?? 'auto' }) }],
}));

await server.connect(new StdioServerTransport());
