#!/usr/bin/env node
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { ATTR_POLICIES, EXTRACTORS, FORMAT_POLICIES, MODES, RENDER_ENGINE_CHOICES, runExtract, runExtractDetailed } from './extract.js';
import { VERSION } from './version.js';

const modeEnum = z.enum(MODES);
const extractorEnum = z.enum(EXTRACTORS);
const attrsEnum = z.enum(ATTR_POLICIES);
const formatEnum = z.enum(FORMAT_POLICIES);
const extractorDesc =
  '抽取引擎。默认 auto：非 HTML 原样透传 → Defuddle → Trafilatura（装了才用，否则静默跳过）→ semantic → ui 清单。非 HTML 输入原样透传；显式指定某引擎即返回它的原始结果，不再静默换引擎。';
const modeDesc =
  '输出样式。默认 markdown。"html" 返回清理后的 HTML：保留完整 DOM 结构与文字顺序，去掉脚本/样式/模板/图标/注释；比 markdown 或界面清单更费 token，但不截断——需要结构（表格、表单状态、嵌套）时用它。';
const attrsDesc =
  '属性策略，仅对 mode "html" 有效。semantic（默认）：保留 href/src/alt/title/colspan/rowspan/scope 与表格/表单状态，去掉 class/style/id/data-*/aria-*。none：清空全部属性（最小，但丢链接目标与合并单元格）。all：保留全部属性，只去掉脚本与样式。';
const formatDesc =
  '排版策略，仅对 mode "html" 有效。compact（默认）：压掉源码缩进与空行，行内元素间留一个空格（最小，不重排）。pretty：重新缩进便于人读。raw：保留源码原始空白。';
const pruneEmptyDesc =
  '仅对 mode "html" 有效。删掉清理后变空的容器（空 div/span/nav/header…），这些容器常占掉大部分字节；table/form/pre 结构会保留。默认 false：保留空壳容器。';
const textMaxDesc =
  '仅对 mode "ui"（或 extractor "ui"）有效：单条文本的字符上限。默认 150；更长的段落（商品描述、FAQ 正文、条款）会从清单里剔除，输出里会报告剔除了多少条。设 0 表示不限制——当界面清单是唯一视图、长段落本身重要时用它。';
const allowEmptyDesc =
  '即使结果像"客户端渲染应用壳"（正文不足 200 字符而 HTML 不小于 5 KB）也保留。默认 false：这类页面报错并提示改用 render:"always"，因为静态 HTML 里还没有正文。';
const keepOptionsDesc =
  '正文模式（markdown/text/skeleton）末尾追加"## 表单选项"：下拉框、optgroup、datalist、单选/多选的选项按页面顺序列成列表，显示文本与 value 不同时把 value 附在括号里。默认 false：正文模式不收控件值，页面若把清单放在表单里（镜像列表、地区、套餐）就会丢。';
const toTexts = (v) => (v == null ? undefined : Array.isArray(v) ? v : [v]);

/**
 * MCP 与 CLI 共用同一条抽取管线（runExtractDetailed）：两边各写一份的话，
 * 新增参数（如 --keep-options）只会在一侧生效，mode 与 extractor 的对应关系也会漂移。
 */
async function handleSource(src, options) {
  const { output } = await runExtractDetailed(src, options.mode ?? 'markdown', options);
  return output;
}

/** 工具参数（snake_case）→ 管线选项（camelCase）：三个工具与三个别名共用同一份映射。 */
const toOptions = (a) => ({
  mode: a.mode ?? 'markdown',
  extractor: a.extractor ?? 'auto',
  attrs: a.attrs ?? 'semantic',
  format: a.format ?? 'compact',
  pruneEmpty: a.prune_empty ?? false,
  textMax: a.text_max,
  allowEmpty: a.allow_empty ?? false,
  keepOptions: a.keep_options ?? false,
  proxy: a.proxy,
  render: a.render ?? false,
  renderTimeoutMs: a.render_timeout_ms,
  headful: a.headful ?? false,
  chromeBin: a.chrome_bin,
  browserBrand: a.browser_brand,
  pythonBin: a.python_bin,
  saveHtml: a.save_html,
  renderEngine: a.render_engine,
  cdpUrl: a.cdp_url,
  expectTexts: toTexts(a.expect_text),
  waitSelector: a.wait_selector,
  postWaitMs: a.post_wait_ms,
});

const server = new McpServer({
  name: 'htmlmini',
  version: VERSION,
});

const fileDesc =
  '提取本地 HTML 文件的核心内容，剥掉 CSS/JS/样板。适用于静态文件、设计稿，以及 resilient-browser-fetch 渲染后落盘的页面（HTML 旁边的 "<file>.meta.json" 会自动被用来还原页面 URL）。文章页用 Defuddle；仪表盘/界面设计页自动回退为组件清单（标题、地标、字段、按钮、表格）。要元数据 + 实际用的抽取器 + 省下的 token 比例时用 mode "json"。';
const urlDesc =
  '抓取 URL 并提取核心正文为 Markdown，剥掉 CSS/JS/广告/导航（基于 Defuddle + schema.org 元数据）。默认只做静态抓取：跟随 HTTP(S)_PROXY 环境变量（NO_PROXY 豁免），除非用 "proxy" 覆盖；遇到 403/5xx 会用浏览器头重试一次并在错误里点名挑战特征。把 "render" 设为 true 可在静态 403/5xx 时回退浏览器渲染（走 resilient-browser-fetch 的 save_page，沿用同一代理），需要本机装有层 >= 1 引擎（playwright/patchright、scrapling、cloak-cdp、chrome-late、nodriver）。JS 很重的页面也可以自己先渲染、再把落盘的 HTML 交给 htmlmini_extract_file。超大页面用 "skeleton"；要元数据 + 省下的 token 比例用 "json"。';
const htmlDesc =
  '清理作为字符串给出的原始 HTML（例如测试框架已经抓到的页面源码）：只返回核心正文 Markdown，让模型能总结而不必为 CSS/JS 烧 token。';

const shapeFile = {
  path: z.string().describe('Absolute path to a local .html file'),
  mode: modeEnum.optional().describe(modeDesc),
  extractor: extractorEnum.optional().describe(extractorDesc),
  attrs: attrsEnum.optional().describe(attrsDesc),
  format: formatEnum.optional().describe(formatDesc),
  prune_empty: z.boolean().optional().describe(pruneEmptyDesc),
  text_max: z.number().optional().describe(textMaxDesc),
  allow_empty: z.boolean().optional().describe(allowEmptyDesc),
  keep_options: z.boolean().optional().describe(keepOptionsDesc),
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
  keep_options: z.boolean().optional().describe(keepOptionsDesc),
  proxy: z
    .string()
    .optional()
    .describe('这次抓取的代理覆盖：http(s) 地址，或 "direct" 表示绕过环境代理。省略则跟随 HTTP_PROXY/HTTPS_PROXY/NO_PROXY 环境变量。'),
  render: z
    .union([z.boolean(), z.literal('always')])
    .optional()
    .describe('浏览器渲染。false（默认）：只做静态抓取。true：静态 403/5xx 时回退浏览器渲染（走 resilient-browser-fetch 的 save_page，沿用本次抓取的同一代理）再抽取。"always"：静态 200 也渲染——用于 HTML 是 200 但正文要等水合才出现的客户端渲染页面。需要本机装有层 >= 1 引擎（playwright/patchright、scrapling、cloak-cdp、chrome-late、nodriver）；受 render_timeout_ms 约束。'),
  render_timeout_ms: z
    .number()
    .optional()
    .describe('浏览器渲染的超时毫秒数（默认 300000）。仅在 render 开启时生效。'),
  headful: z
    .boolean()
    .optional()
    .describe('渲染时弹出浏览器窗口（默认无头）。用于首次人工验证；日志仍会输出到 stderr。注意它只决定"要不要开窗"，不改变"什么时候渲染"。'),
  chrome_bin: z
    .string()
    .optional()
    .describe('渲染用的浏览器可执行文件（覆盖自动探测：PATH、常见路径、Playwright 缓存）。零依赖直渲与 save_page 渲染（chrome-late 等）都用它；WAF 可能按客户端品牌判负（实测同一出口 Chrome 被拒、Edge 放行），此时指向 msedge.exe 即可换客户端。'),
  browser_brand: z
    .enum(['auto', 'chrome', 'edge', 'chromium'])
    .optional()
    .describe('渲染用浏览器品牌偏好（默认 auto：Chrome→Edge→Chromium）。不用自己写路径，渲染脚本按品牌找已安装的浏览器；边缘封禁按客户端品牌判时用它换品牌。与 chrome_bin 同时给时路径优先。'),
  python_bin: z
    .string()
    .optional()
    .describe('渲染回退与可选 Trafilatura 用的 Python 解释器。默认是 PATH 上的 "python"/"python3"，它往往不是装了 playwright/scrapling 的那个环境；也读 HTMLMINI_PYTHON。用 "auto" 可扫描本机（conda/venv/uv/PATH）并挑一个装了层 >= 1 引擎的解释器。不显式指定时，渲染失败会再用扫描到的最强解释器（优先层 >= 2，即带挑战求解的）重试一次。'),
  save_html: z
    .string()
    .optional()
    .describe('绝对路径：把实际用于抽取的 HTML（静态抓取结果，或开渲染时的渲染结果）写到这个文件，并写一份兄弟 "<path>.meta.json" 记录页面 URL。之后换模式读这份文件即可，不必再抓一次或再渲染一次。内容是原始 HTML（不是 "html" 模式的清理结果），在校验之前写盘，所以挑战空壳报错时原文也留得下来。仅 URL 输入有效。'),
  render_engine: z
    .enum(RENDER_ENGINE_CHOICES)
    .optional()
    .describe('钉住 save_page 的引擎，不再自动升档："auto"（默认）从最低层逐个尝试已安装的层；显式指定（playwright | scrapling | cloak-cdp | chrome-late | nodriver）只跑该引擎——缺件直接报错而不回退。用在已知需要更高层的站点上，可省掉注定被拒的尝试。挑战站点选 "chrome-late"：它先让站点的挑战跑完再接入读取已渲染 DOM。'),
  cdp_url: z
    .string()
    .optional()
    .describe('接管你已经开着的浏览器（如 --remote-debugging-port 启动的 Chrome/Edge），复用它自己的 profile、cookie 与放行凭据，只读它里已渲染的 DOM，不会关闭它。适用：同一台机器、同一个出口，你的浏览器能打开而任何自建浏览器都被拒——决定放行的是客户端身份与网络路径，不是 IP 信誉时用它。浏览器里没有目标页时会报错并提示先手动打开。'),
  expect_text: z
    .union([z.string(), z.array(z.string())])
    .optional()
    .describe('目标断言：最终 HTML 必须包含这些文本（可重复/数组，全部命中才算成功）。缺失时直接报错，而不是把"渲染成功但没有目标块"当结果交出去；渲染时同时透传给 save_page，让它按引擎升档。用于下拉清单、商品名、价格这类"有没有真的抓到"的判据。命中的文本若不在当前 mode 的输出里（控件值/清单常被剔除），改用 mode:"html" 或 save_html 取原文。'),
  wait_selector: z
    .string()
    .optional()
    .describe('渲染时等该 CSS 选择器可见再取 DOM（走 save_page 通路；零依赖 chrome dump-dom 没有等待钩子，给了它会改用 save_page）。异步清单、懒加载区块用它替代盲等。'),
  post_wait_ms: z
    .number()
    .optional()
    .describe('取 DOM 前额外等待毫秒数（save_page 默认 1000）。数据在 load 之后才到的页面用它补齐，与 wait_selector 一起用更稳。'),
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
  keep_options: z.boolean().optional().describe(keepOptionsDesc),
};

// 正确命名（v2）。旧拼写 htmmini_* 保留为别名以兼容已配置的客户端。
// 参数映射只有 toOptions 一份：别名工具与正式名共用同一套 shape，行为不会分叉。
const toolResult = async (promise) => ({ content: [{ type: 'text', text: await promise }] });

server.tool('htmlmini_extract_file', fileDesc, shapeFile, async (args) => toolResult(handleSource(args.path, toOptions(args))));

server.tool('htmlmini_extract_url', urlDesc, shapeUrl, async (args) => toolResult(handleSource(args.url, toOptions(args))));

server.tool('htmlmini_extract_html', htmlDesc, shapeHtml, async (args) => toolResult(runExtract(null, args.mode ?? 'markdown', { ...toOptions(args), forceContent: args.html_content })));

const aliasNote = 'Deprecated alias of the htmlmini_* tool (kept for backward compatibility).';
server.tool('htmmini_extract_file', `${aliasNote} ${fileDesc}`, shapeFile, async (args) => toolResult(handleSource(args.path, toOptions(args))));

server.tool('htmmini_extract_url', `${aliasNote} ${urlDesc}`, shapeUrl, async (args) => toolResult(handleSource(args.url, toOptions(args))));

server.tool('htmmini_extract_html', `${aliasNote} ${htmlDesc}`, shapeHtml, async (args) => toolResult(runExtract(null, args.mode ?? 'markdown', { ...toOptions(args), forceContent: args.html_content })));

await server.connect(new StdioServerTransport());
