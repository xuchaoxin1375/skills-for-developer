// 可靠性回归：node tests/reliability.mjs（已接入 pnpm test）。
// 全内置合成输入 + 本地回环 HTTP/临时文件，无外部网络依赖。
import { strict as assert } from 'node:assert';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync, readdirSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  challengeSignals,
  decodeHtml,
  extractHtml,
  findCapablePython,
  findPython,
  findSolverPython,
  formOptionsSection,
  isInterpreterRetryable,
  pickStrongerPython,
  pickHydrationEngine,
  pythonBinOverride,
  resetEnvScanCache,
  resolveSavePageEngine,
  savePageArgs,
  scanPythonEnvironments,
  hostBypassed,
  maskProxy,
  pickPlaywrightChrome,
  proxyOrigin,
  readSiblingMeta,
  readSource,
  renderResult,
  renderViaBrowser,
  resolveProxy,
  runExtract,
  runExtractDetailed,
  wrapDetails,
  savePageUsable,
  skeletonFromMarkdown,
  tryTrafilatura,
} from '../src/extract.js';
import { setLogLevel } from '../src/log.js';
import { markSource, padPayload } from '../src/output.js';
// 进程内断言只看返回值；子进程 CLI 会各自按默认级别打日志（下面显式断言）。
setLogLevel('quiet');

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const CLI = path.join(ROOT, 'src', 'cli.js');

let n = 0;
const ok = (cond, msg) => {
  n++;
  assert.ok(cond, msg);
  console.log(`ok ${n} - ${msg}`);
};

/** 剥掉 CLI 加在载荷外的来源哨兵行（HTML 注释）与首尾留白，便于比对正文本身。 */
const stripMarks = (s) =>
  String(s)
    .replace(/^\n*<!-- htmlmini:source begin [^\n]*\n/, '')
    .replace(/\n*<!-- htmlmini:source end [^\n]*\n*$/, '');

// ---- 0. 载荷外围：来源哨兵行（HTML 注释）与终端留白 ----
{
  const info = { status: 200, source: 'https://example.com/app', rendered: false, fetchedAt: '2026-10-30 10:00:00,000' };
  const marked = markSource('# 标题\n', info);
  const [begin, ...rest] = marked.split('\n');
  ok(
    begin === '<!-- htmlmini:source begin status=200 url=https://example.com/app render=static fetched=2026-10-30 10:00:00,000 -->',
    '哨兵行是 HTML 注释，写明 url/状态码/抓取方式/时刻',
  );
  ok(rest.at(-1) === '<!-- htmlmini:source end url=https://example.com/app -->', '结尾哨兵行收口');
  ok(rest.slice(0, -1).join('\n') === '# 标题', '哨兵行之间正文一字不改');
  const rendered = markSource('x', { ...info, status: null, rendered: true });
  ok(rendered.includes('status=unknown') && rendered.includes('render=browser'), '无状态码的渲染结果记 unknown/browser');
  ok(markSource('', info).split('\n').length === 2, '空载荷只留起止两行');

  ok(padPayload('# 标题\n') === '\n# 标题\n\n', '终端留白：上下各一行空行');
  ok(padPayload('') === '' && padPayload('\n') === '\n', '空载荷不加留白');
}

// ---- 1. decodeHtml：BOM / GBK / 非法字节 ----
{
  const bom = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from('<p>hi</p>')]);
  ok(decodeHtml(bom) === '<p>hi</p>', 'BOM 被剥离');
  // “中文” 的 GBK 字节：UTF-8 解码必出 U+FFFD，从而走 GBK 路径。
  const gbk = Buffer.from([0xd6, 0xd0, 0xce, 0xc4]);
  ok(decodeHtml(gbk) === '中文', `GBK 回退解码（实得 ${decodeHtml(gbk)}）`);
  const bad = Buffer.from([0xff, 0xfe, 0xfd, 0x3c, 0x70, 0x3e]);
  ok(typeof decodeHtml(bad) === 'string', '非法字节不抛错');
}

// ---- 2. 空输入 / 脏输入不崩 ----
{
  const e = await extractHtml('');
  ok(typeof e.content === 'string' && e.stats != null, `空串不崩（used=${e.used}）`);
  const g = await extractHtml('<html><<<###');
  ok(typeof g.content === 'string', `脏 HTML 不崩（used=${g.used}）`);
  const d = await extractHtml('<!doctype html>');
  ok(typeof d.content === 'string', `纯 doctype 不崩（used=${d.used}）`);
  ok(renderResult(e, 'title') === '' || typeof renderResult(e, 'title') === 'string', '空标题渲染不崩');
  ok(skeletonFromMarkdown('').includes('SKELETON'), '空 skeleton 不崩');
}

// ---- 3. readSiblingMeta：缺失 / 坏 JSON / 字段变体 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-meta-'));
  try {
    ok((await readSiblingMeta(path.join(dir, 'nope.html'))) === null, '无 meta 文件返回 null');
    const bad = path.join(dir, 'bad.html');
    await writeFile(bad, '<p>x</p>');
    await writeFile(`${bad}.meta.json`, '{not json');
    ok((await readSiblingMeta(bad)) === null, '坏 meta JSON 返回 null');
    const v = path.join(dir, 'v.html');
    await writeFile(v, '<p>x</p>');
    await writeFile(`${v}.meta.json`, JSON.stringify({ pageUrl: 'https://example.com/app' }));
    const m = await readSiblingMeta(v);
    ok(m && m.url === 'https://example.com/app', '兼容 pageUrl 字段');
    ok((await readSiblingMeta('https://example.com/a.html')) === null, 'URL 输入跳过 meta');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 4. 本地 HTTP：200 / 404 / 跳转 / GBK / 超时 ----
const ARTICLE_BODY = `<article><h1>本地文章</h1><p>${'正文内容足够长可以被识别为主体。'.repeat(10)}</p></article>`;
let server;
let base;
{
  server = http.createServer((req, res) => {
    if (req.url === '/article') {
      res.writeHead(200, { 'content-type': 'text/html' });
      res.end(`<!doctype html><html><head><title>本地页</title></head><body>${ARTICLE_BODY}</body></html>`);
    } else if (req.url === '/redir') {
      res.writeHead(302, { location: '/article' });
      res.end();
    } else if (req.url === '/gbk') {
      res.writeHead(200, { 'content-type': 'text/html' }); // 故意不带 charset
      res.end(
        Buffer.concat([
          Buffer.from('<html><head><title>', 'latin1'),
          Buffer.from([0xd6, 0xd0, 0xce, 0xc4]),
          Buffer.from('</title><body><p>', 'latin1'),
          Buffer.from([0xb2, 0xe2, 0xca, 0xd4]),
          Buffer.from('</p></body></html>', 'latin1'),
        ]),
      );
    } else if (req.url === '/pickier') {
      // 简头 502，浏览器头 200：模拟按指纹拦截的站点。
      // 注意：undici 会把 fetch 的 sec-fetch-mode 强制改写为 cors，故门控不用它。
      if (req.headers['upgrade-insecure-requests'] === '1') {
        res.writeHead(200, { 'content-type': 'text/html' });
        res.end(`<!doctype html><html><head><title>浏览器页</title></head><body>${ARTICLE_BODY}</body></html>`);
      } else {
        res.writeHead(502, { 'content-type': 'text/plain' });
        res.end('error code: 502');
      }
    } else if (req.url === '/challenge403') {
      res.writeHead(403, {
        'content-type': 'text/html',
        server: 'cloudflare',
        'set-cookie': 'sct=xyz1792061208; Path=/; Max-Age=120; Domain=127.0.0.1; Secure',
        'x-robots-tag': 'noindex',
      });
      res.end('<html><head><title>Just a moment</title></head><body>challenge</body></html>');
    } else if (req.url === '/always502') {
      res.writeHead(502, { 'content-type': 'text/plain', server: 'cloudflare' });
      res.end('error code: 502');
    } else if (req.url === '/shell200') {
      // 200 但正文极短、HTML 很大: 客户端渲染的应用壳(静态抓取拿不到正文)。
      res.writeHead(200, { 'content-type': 'text/html' });
      res.end(
        `<!doctype html><html><head><title>壳页面</title></head><body data-filler="${'x'.repeat(
          6000,
        )}"><div id="app"></div><p>Loading…</p></body></html>`,
      );
    } else if (req.url === '/slow') {
      setTimeout(() => {
        try {
          res.writeHead(200, { 'content-type': 'text/html' });
          res.end('<p>late</p>');
        } catch {
          /* 客户端已断开 */
        }
      }, 1500);
    } else {
      res.writeHead(404, { 'content-type': 'text/plain' });
      res.end('nope');
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;

  const md = await runExtract(`${base}/article`, 'markdown');
  ok(md.includes('正文内容足够长'), '本地 200 页面提取正文');

  let e404 = null;
  try {
    await runExtract(`${base}/missing`, 'markdown');
  } catch (e) {
    e404 = e;
  }
  ok(e404 && /HTTP 404/.test(e404.message), `404 抛错（实得 ${e404 && e404.message}）`);

  const rd = await runExtract(`${base}/redir`, 'title');
  ok(rd.trim() === '本地页', '302 跳转被跟随');

  const gt = await runExtract(`${base}/gbk`, 'title');
  ok(gt.trim() === '中文', `无 charset 的 GBK 按 GBK 解（实得 ${gt.trim()}）`);

  const t0 = Date.now();
  let etimeout = null;
  try {
    await readSource(`${base}/slow`, { timeoutMs: 400 });
  } catch (e) {
    etimeout = e;
  }
  const elapsed = Date.now() - t0;
  ok(etimeout && /fetch timeout after 400ms/.test(etimeout.message), `慢响应被超时中断（实得 ${etimeout && etimeout.message}）`);
  ok(elapsed < 10000, `超时快速返回（${elapsed}ms < 10s）`);
}

// ---- 5. CLI：参数解析与退出码 ----
// 注：不用 execFile 的 input 选项喂 stdin——本机 Windows 上它连最小复现
// （`node -e` 读 stdin）都会挂起 20s 超时；改用 spawn 显式 write+end（已验证秒回）。
async function cli(args, { input, env } = {}) {
  const { spawn } = await import('node:child_process');
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [CLI, ...args], { windowsHide: true, ...(env ? { env: { ...process.env, ...env } } : {}) });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));
    child.on('error', (e) => resolve({ code: 1, stdout, stderr: String((e && e.message) || e) }));
    child.on('close', (code) => resolve({ code: code ?? 1, stdout, stderr }));
    if (input != null) child.stdin.write(input);
    child.stdin.end();
  });
}
{
  const h = await cli(['--help']);
  ok(h.code === 0 && h.stdout.includes('USAGE'), '--help 退出 0');
  // 默认给短版：一屏看完，并指明完整版入口。
  const briefLines = h.stdout.split('\n').length;
  ok(briefLines < 70, `--help 默认是短版（${briefLines} 行）`);
  ok(h.stdout.includes('--help full'), '短版写明完整版入口');
  const hf = await cli(['--help', 'full']);
  ok(hf.code === 0 && hf.stdout.includes('TROUBLESHOOTING'), '--help full 给完整版');
  ok(hf.stdout.split('\n').length > briefLines, '完整版比短版长');
  const hEq = await cli(['--help=full']);
  ok(hEq.code === 0 && hEq.stdout === hf.stdout, '--help=full 与 --help full 一致');
  // 内嵌帮助必须覆盖实现里真实存在的每个选项与每个取值。
  // 历史上帮助文本与实现脱过节（新增引擎/抽取器后帮助没跟上），这里用源码反查兜住。
  const cliSrc = await readFile(CLI, 'utf8');
  const optionNames = [...new Set(
    [...cliSrc.matchAll(/a === '(--[a-z-]+)'/g)].map((m) => m[1])
      .concat([...cliSrc.matchAll(/a\.startsWith\('(--[a-z-]+)=?'/g)].map((m) => m[1]))
      // 短选项映射表里的长选项名（'-m': 'markdown' -> --markdown）也是真实选项
      .concat([...cliSrc.matchAll(/'(-[a-zA-Z])':\s*'([a-z]+)'/g)].map((m) => `--${m[2]}`)),
  )];
  const missingOptions = optionNames.filter((o) => !hf.stdout.includes(o));
  ok(missingOptions.length === 0, `完整版覆盖全部 ${optionNames.length} 个选项（缺 ${missingOptions.join(', ') || '无'}）`);
  const shortFlags = [...new Set([...cliSrc.matchAll(/'(-[a-zA-Z])':\s*'/g)].map((m) => m[1]))];
  const missingShort = shortFlags.filter((o) => !hf.stdout.includes(o));
  ok(missingShort.length === 0, `完整版覆盖全部短选项（缺 ${missingShort.join(', ') || '无'}）`);
  // 短版只能出现真实存在的选项，且必须是完整版的子集（不许两版分叉出各自的选项）。
  const briefOptions = [...new Set([...h.stdout.matchAll(/--[a-z][a-z-]*/g)].map((m) => m[0]))];
  const bogus = briefOptions.filter((o) => !optionNames.includes(o) && o !== '--help' && !o.startsWith('--help='));
  ok(bogus.length === 0, `短版只出现真实选项（异常 ${bogus.join(', ') || '无'}）`);
  const notInFull = briefOptions.filter((o) => !hf.stdout.includes(o));
  ok(notInFull.length === 0, `短版是完整版的子集（多出 ${notInFull.join(', ') || '无'}）`);
  // 每个选项在选项清单里只占一行：长选项与短选项合写成一行（"-r, --render[...]"），
  // 不再另起一行写"同上（短选项）"——那属于重复登记，读者要自己对齐两份。
  // 只认行首的选项写法（可用 " / " 连写多个），描述正文里提到的选项名不算登记。
  const optionSpec = (line) => {
    const names = [];
    let s = line;
    for (;;) {
      const m = /^\s*((?:-[A-Za-z], )?--[a-z][a-z-]*(?:\[[^\]]+\])?(?: <[^>]+>)?)/.exec(s);
      if (!m) break;
      names.push(m[1].match(/--[a-z][a-z-]*/)[0]);
      s = s.slice(m[0].length);
      const sep = /^\s+\/\s+/.exec(s);
      if (!sep) break;
      s = s.slice(sep[0].length);
    }
    return names;
  };
  const dupInOptions = (text, from, to) => {
    const start = text.indexOf(from);
    const body = text.slice(start, to ? text.indexOf(to, start) : undefined);
    const seen = new Set();
    const dup = new Set();
    for (const line of body.split('\n')) {
      for (const name of optionSpec(line)) {
        if (seen.has(name)) dup.add(name);
        seen.add(name);
      }
    }
    return [...dup];
  };
  const briefDup = dupInOptions(h.stdout, '常用选项', '更多');
  ok(briefDup.length === 0, `短版选项清单里每个选项只写一行（重复 ${briefDup.join(', ') || '无'}）`);
  const fullDup = dupInOptions(hf.stdout, '选项 (OPTIONS)', '--attrs 取值');
  ok(fullDup.length === 0, `完整版选项清单里每个选项只写一行（重复 ${fullDup.join(', ') || '无'}）`);
  const valueSets = {
    mode: ['markdown', 'skeleton', 'text', 'json', 'title', 'ui', 'html'],
    extractor: ['auto', 'defuddle', 'trafilatura', 'semantic', 'ui', 'sanitize', 'passthrough'],
    'render-engine': ['auto', 'playwright', 'scrapling', 'cloak-cdp', 'chrome-late', 'nodriver'],
    'browser-brand': ['auto', 'chrome', 'edge', 'chromium'],
  };
  for (const [opt, values] of Object.entries(valueSets)) {
    const missing = values.filter((val) => !hf.stdout.includes(val));
    ok(missing.length === 0, `完整版列出 --${opt} 的全部取值（缺 ${missing.join(', ') || '无'}）`);
  }
  ok(hf.stdout.includes('EXAMPLES') && hf.stdout.includes('TROUBLESHOOTING'), '完整版带示例与常见症状两节');
  ok(hf.stdout.includes('EXIT CODES') && hf.stdout.includes('ENVIRONMENT'), '完整版带退出码与环境变量两节');
  // 补全脚本是独立文件（无法从 JS 常量派生），只能靠断言防漂移。
  for (const file of ['htmlmini.bash', 'htmlmini.ps1']) {
    const comp = await readFile(path.join(ROOT, 'completions', file), 'utf8');
    const missing = valueSets['render-engine'].filter((val) => !comp.includes(val));
    ok(missing.length === 0, `${file} 补全含全部渲染引擎（缺 ${missing.join(', ') || '无'}）`);
    const missingModes = valueSets.mode.filter((val) => !comp.includes(val));
    ok(missingModes.length === 0, `${file} 补全含全部输出模式（缺 ${missingModes.join(', ') || '无'}）`);
    const missingBrands = valueSets['browser-brand'].filter((val) => !comp.includes(val));
    ok(missingBrands.length === 0, `${file} 补全含全部浏览器品牌（缺 ${missingBrands.join(', ') || '无'}）`);
  }
  const lm = await cli(['--list-modes']);
  ok(lm.code === 0 && valueSets.mode.every((v) => lm.stdout.includes(v)) && lm.stdout.includes('正文 Markdown'), '--list-modes 给出模式与说明');
  const le = await cli(['--list-extractors']);
  ok(le.code === 0 && valueSets.extractor.every((v) => le.stdout.includes(v)), '--list-extractors 给出全部抽取引擎');
  const lre = await cli(['--list-render-engines']);
  ok(lre.code === 0 && valueSets['render-engine'].every((v) => lre.stdout.includes(v)), '--list-render-engines 给出全部渲染引擎');
  const lenv = await cli(['--list-env']);
  ok(lenv.code === 0 && lenv.stdout.includes('HTMLMINI_PYTHON') && lenv.stdout.includes('HTMLMINI_PROXY_REGISTRY'), '--list-env 给出环境变量清单');
  const v = await cli(['--version']);
  ok(v.code === 0 && /^htmlmini \d{4}\.\d{2}\.\d{2}\.\d{4}\n$/.test(v.stdout), `--version 输出日期时间版本（实得 ${v.stdout.trim()}）`);
  const vShort = await cli(['-V']);
  ok(vShort.code === 0 && vShort.stdout === v.stdout, '-V 与 --version 一致');
  const u = await cli(['--nope']);
  ok(u.code === 2 && u.stderr.includes('unknown option'), '未知选项退出 2');
  const m = await cli(['--mode', 'nope']);
  ok(m.code === 2 && m.stderr.includes('unknown mode'), '非法 mode 退出 2');
  const f = await cli([path.join(os.tmpdir(), 'htmlmini-不存在.html')]);
  ok(f.code === 1 && f.stderr.includes('htmlmini:'), '缺失文件退出 1 且有提示');
  const s = await cli(['-', '--title'], {
    input: '<html><head><title>管道标题</title></head><body><p>x</p></body></html>',
  });
  ok(s.code === 0 && stripMarks(s.stdout).trim() === '管道标题', 'stdin 管道正常');
  ok(!s.stdout.includes('htmlmini:source'), '默认不加来源哨兵行');

  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-cli-'));
  try {
    const dash = path.join(dir, 'dash.html');
    await writeFile(
      dash,
      '<html><head><title>面板</title></head><body><button>开始</button><table><tr><th>列</th></tr></table></body></html>',
    );
    const j = await cli([dash, '--mode=json', '--extractor=ui']);
    const p = JSON.parse(j.stdout);
    ok(j.code === 0 && p.used === 'ui' && p.content.includes('## 按钮'), '--mode= 形式与强制 ui 生效');
    const out = path.join(dir, 'out.md');
    const w = await cli([dash, '--ui', '-o', out]);
    const saved = await readFile(out, 'utf8');
    ok(w.code === 0 && saved.includes('## 按钮'), '-o 落盘');
    ok(!saved.startsWith('\n') && saved.endsWith('\n') && !saved.endsWith('\n\n'), '-o 落盘写纯载荷，不留首尾空行');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 5b. 日志：阶段进度只走 stderr，stdout 保持纯载荷；--quiet/--verbose 生效 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-log-'));
  try {
    const page = path.join(dir, 'p.html');
    await writeFile(page, '<html><head><title>日志</title></head><body>\n  <p>Run <b>3</b> tests</p>\n</body></html>');
    const d = await cli([page, '--mode', 'html', '--pretty']);
    ok(d.code === 0 && d.stderr.includes('htmlmini: [read]'), '默认把阶段进度打到 stderr');
    for (const stage of ['[parse]', '[extract]', '[format]', '[write]']) {
      ok(d.stderr.includes(`htmlmini: ${stage}`), `进度含 ${stage} 阶段`);
    }
    ok(!d.stdout.includes('[read]') && !d.stdout.includes('[write]'), 'stdout 不含日志');
    ok(d.stdout.includes('<p>Run <b>3</b> tests</p>'), 'stdout 仍是纯载荷');
    const q = await cli([page, '--mode', 'html', '--quiet']);
    ok(q.code === 0 && q.stderr.trim() === '', '--quiet 静默，仅保留错误');
    const v = await cli([page, '--mode', 'html', '--verbose']);
    ok(v.stderr.includes('source=') && v.stderr.includes('reduction='), '--verbose 追加细节行');

    // 状态码与来源哨兵：状态码进 [read] 行；哨兵行默认关，显式开启才是 HTML 注释。
    const live = await cli([`${base}/article`]);
    ok(live.code === 0 && /\[read\] status=200 /.test(live.stderr), '抓取状态码放在 [read] 行最前面');
    ok(!live.stdout.includes('htmlmini:source'), '默认输出不带来源哨兵行');
    ok(
      !live.stdout.startsWith('\n') && !live.stdout.endsWith('\n\n') && live.stdout.endsWith('\n'),
      '管道 stdout 写纯载荷，不留空行',
    );
    ok(live.stdout.includes('本地文章') && !live.stdout.includes('<!--'), '默认正文原样保留，无注释');
    const marked = await cli([`${base}/article`, '--source-marks']);
    const beginLine = marked.stdout.split('\n').find((l) => l.startsWith('<!-- htmlmini:source begin ')) ?? '';
    ok(
      beginLine.startsWith('<!-- htmlmini:source begin ') &&
        beginLine.endsWith(' -->') &&
        beginLine.includes(`url=${base}/article`) &&
        beginLine.includes('status=200') &&
        beginLine.includes('render=static') &&
        /fetched=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}/.test(beginLine),
      '--source-marks 用 HTML 注释写明 url/状态码/抓取方式/时刻',
    );
    ok(marked.stdout.includes(`<!-- htmlmini:source end url=${base}/article -->`), '结尾哨兵行收口');
    ok(stripMarks(marked.stdout).includes('本地文章'), '哨兵行之外正文原样保留');
    const envOn = await cli([`${base}/article`], { env: { HTMLMINI_SOURCE_MARKS: '1' } });
    ok(envOn.stdout.includes('<!-- htmlmini:source begin '), 'HTMLMINI_SOURCE_MARKS=1 开启哨兵行');
    const bare = await cli([`${base}/article`, '--no-source-marks']);
    ok(bare.code === 0 && !bare.stdout.includes('htmlmini:source'), '--no-source-marks 保持关闭');
    const asJson = await cli([`${base}/article`, '--json']);
    const parsed = JSON.parse(asJson.stdout);
    ok(!asJson.stdout.includes('htmlmini:source'), '--json 不掺哨兵行');
    ok(
      parsed.source === `${base}/article` && parsed.fetchStatus === 200 && typeof parsed.fetchedAt === 'string',
      '--json 用 source/fetchStatus/fetchedAt 字段承担来源，仍是合法 JSON',
    );

    // 代理来源必须写进 [read] 行：只设环境变量时旧日志谎报 proxy=none。
    // 抓 127.0.0.1:9（discard，必被拒）保证秒失败，只断言 stderr 文本，不看退出码。
    const dead = 'http://127.0.0.1:9/x';
    const envProxy = await cli([dead, '--mode', 'html'], { env: { HTTP_PROXY: 'http://127.0.0.1:18080' } });
    ok(envProxy.stderr.includes('[proxy: http://127.0.0.1:18080 (HTTP_PROXY)]'), '环境变量代理连来源一起写进 [read] 行');
    const bypass = await cli([dead, '--mode', 'html'], { env: { HTTP_PROXY: 'http://127.0.0.1:18080', NO_PROXY: '*' } });
    ok(bypass.stderr.includes('[proxy: direct (NO_PROXY)]'), 'NO_PROXY 命中显示为直连');
    const forced = await cli([dead, '--mode', 'html', '--noproxy'], { env: { HTTP_PROXY: 'http://127.0.0.1:18080' } });
    ok(forced.stderr.includes('[proxy: direct (--noproxy)]'), '--noproxy 覆盖环境显示为直连');
    const flag = await cli([dead, '--mode', 'html', '--proxy', 'http://user:pw@127.0.0.1:18080']);
    ok(flag.stderr.includes('[proxy: http://127.0.0.1:18080 (--proxy)]') && !flag.stderr.includes('user:pw'), '--proxy 显示且不泄凭据');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 5c. --save-html：落盘原文 + 同名 meta，供后续模式等价复用 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-save-'));
  try {
    const savedHtml = path.join(dir, 'saved.html');
    const directPath = path.join(dir, 'direct.md');
    const direct = await cli([`${base}/article`, '-m', '-o', directPath]);
    const withSave = await cli([`${base}/article`, '-m', '--save-html', savedHtml, '-o', path.join(dir, 'out.md')]);
    ok(direct.code === 0 && withSave.code === 0 && existsSync(savedHtml), '--save-html 写出原文');
    const meta = JSON.parse(await readFile(`${savedHtml}.meta.json`, 'utf8'));
    ok(meta.url === `${base}/article` && meta.rendered === false, 'meta 记下源 URL 与静态抓取');
    ok(withSave.stderr.includes('[write]') && withSave.stderr.includes('static fetch'), '日志写明落盘与来源');

    // 关键回归：复用文件必须与直抓等价（URL 基准与 fetchCss 都要跟过来）；首尾留白（stdout 专有）不比。
    const directMd = await readFile(directPath, 'utf8');
    const reuse = await cli([savedHtml, '-m']);
    ok(reuse.code === 0 && reuse.stdout.trim() === directMd.trim(), '复用文件与直抓结果一致');

    const local = path.join(dir, 'local.html');
    await writeFile(local, '<html><head><title>本地</title></head><body><p>x</p></body></html>');
    const loc = await cli([local, '--save-html', path.join(dir, 'copy.html')]);
    ok(
      loc.code === 0 && !existsSync(path.join(dir, 'copy.html')) && loc.stderr.includes('only applies to URL input'),
      '本地文件输入不写文件并提示',
    );

    const missing = await cli([`${base}/missing`, '--save-html', path.join(dir, 'nope.html')]);
    ok(missing.code === 1 && !existsSync(path.join(dir, 'nope.html')), '抓取失败不落盘（404 先抛错）');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 5d. 抓取失败时的本机代理登记提示（只提示，不自动改路线） ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-registry-'));
  const saved = process.env.HTMLMINI_PROXY_REGISTRY;
  // 本段要的是"没在用代理"那条提示文案；机器上若有全局 HTTP(S)_PROXY，
  // CLI 会走代理并给出另一种文案，断言会与本机环境耦合而偶发失败。
  const proxyEnv = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'];
  const savedProxyEnv = Object.fromEntries(proxyEnv.map((k) => [k, process.env[k]]));
  try {
    for (const k of proxyEnv) delete process.env[k];
    const registry = path.join(dir, 'proxy-resources.json');
    await writeFile(
      registry,
      JSON.stringify({ default: 'demo', proxies: [{ name: 'demo', url: 'http://user:pw@127.0.0.1:18080' }] }),
    );
    process.env.HTMLMINI_PROXY_REGISTRY = registry;
    // 127.0.0.1:9 是 discard 端口，连接必被拒绝 → 触发传输层失败。
    const dead = 'http://127.0.0.1:9/x';
    const hint = await cli([dead, '--title']);
    ok(hint.code === 1 && hint.stderr.includes('127.0.0.1:18080'), '传输失败时点名登记里的候选入口');
    ok(hint.stderr.includes('proxy registry'), '提示说明 htmlmini 不自动读登记');
    ok(!hint.stderr.includes('user:pw'), '登记提示不泄露凭据');

    const explicit = await cli([dead, '--title', '--proxy', 'http://127.0.0.1:9/']);
    ok(!explicit.stderr.includes('proxy registry'), '显式指定路线后不再提示登记');

    process.env.HTMLMINI_PROXY_REGISTRY = path.join(dir, '不存在.json');
    const none = await cli([dead, '--title']);
    ok(none.code === 1 && !none.stderr.includes('proxy registry'), '登记读不到时不加噪声');
  } finally {
    if (saved === undefined) delete process.env.HTMLMINI_PROXY_REGISTRY;
    else process.env.HTMLMINI_PROXY_REGISTRY = saved;
    for (const [k, v] of Object.entries(savedProxyEnv)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 6. trafilatura：缺席给安装提示（本机无模块，确定性覆盖） ----
{
  // 探针必须给真正可提取的正文：trafilatura 对无正文的短片段会以退出码 3 结束
  // （有模块也返回 ok:false），拿它判"模块是否可用"会误判成缺模块。
  const probeHtml = `<article><h1>探针</h1><p>${'这是一段足够长的正文内容，用于确认 trafilatura 引擎可用。'.repeat(6)}</p></article>`;
  const probe = await tryTrafilatura(probeHtml);
  ok(typeof probe.ok === 'boolean', 'tryTrafilatura 返回 ok 布尔');
  if (probe.missing) {
    let err = null;
    try {
      await extractHtml(`<p>${'x'.repeat(200)}</p>`, { extractor: 'trafilatura' });
    } catch (e) {
      err = e;
    }
    ok(err && /trafilatura 不可用/.test(err.message), '缺模块时强制引擎给出安装提示');
  } else {
    ok(probe.ok && probe.text.length > 0, '有模块时 trafilatura 可用');
  }
}

// ---- 7. UI 清单回退分支：label 优先级 / 无表头表格 / 长链接与无 alt 图 ----
{
  const html = `<html><head><title>回退</title></head><body>
<input aria-label="搜索框"><input placeholder="请输入"><input id="code">
<label><input type="checkbox">记住我</label>
<table><tr><td>a</td><td>b</td></tr></table>
<a href="http://x">超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本超长链接文本</a>
<img src="x.png"></body></html>`;
  const r = await extractHtml(html, { extractor: 'ui' });
  for (const want of ['搜索框', '请输入', '#code', '记住我']) {
    ok(r.content.includes(want), `字段名回退含 ${want}`);
  }
  ok(/1行×2列/.test(r.content), '无表头表格给行列数');
  ok(!r.content.includes('超长链接文本'), '超长链接文本被跳过');
  ok(!r.content.includes('## 图片'), '无 alt 图片不进清单');
}

// ---- 8. MCP 错误路径：坏文件不崩，服务保持可用 ----
{
  const { spawn } = await import('node:child_process');
  const child = spawn(process.execPath, [path.join(ROOT, 'src', 'mcp.js')], { stdio: ['pipe', 'pipe', 'inherit'] });
  let buf = '';
  const pending = new Map();
  let seq = 0;
  child.stdout.on('data', (d) => {
    buf += d.toString('utf8');
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      if (msg.id != null && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
    }
  });
  const rpc = (method, params) =>
    new Promise((resolve) => {
      const id = ++seq;
      pending.set(id, resolve);
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
    });
  await rpc('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 't', version: '0' } });
  child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' })}\n`);

  const bad = await rpc('tools/call', {
    name: 'htmlmini_extract_file',
    arguments: { path: path.join(os.tmpdir(), 'htmlmini-不存在.html') },
  });
  ok((bad.result && bad.result.isError === true) || bad.error != null, '坏文件返回工具错误而非崩溃');

  const good = await rpc('tools/call', {
    name: 'htmlmini_extract_html',
    arguments: { html_content: '<html><head><title>存活</title></head><body><button>按我</button></body></html>' },
  });
  ok(good.result && good.result.content[0].text.includes('按我'), '出错后服务仍可用');

  // save_html 是 handleSource 的另一条入口，MCP 侧同样要落盘原文 + meta。
  const mcpDir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-mcp-save-'));
  try {
    const savedPath = path.join(mcpDir, 'mcp.html');
    const murl = await rpc('tools/call', {
      name: 'htmlmini_extract_url',
      arguments: { url: `${base}/article`, save_html: savedPath },
    });
    ok(murl.result && murl.result.content[0].text.includes('正文内容足够长'), 'MCP extract_url 返回正文');
    ok(existsSync(savedPath) && existsSync(`${savedPath}.meta.json`), 'MCP save_html 落盘原文与 meta');
    ok(JSON.parse(await readFile(`${savedPath}.meta.json`, 'utf8')).url === `${base}/article`, 'MCP meta 记下源 URL');
  } finally {
    await rm(mcpDir, { recursive: true, force: true });
  }
  child.kill();
}

// ---- 9. 非 HTML 透传：markdown/纯文本/JSON 不硬抽 ----
{
  const md = '# skills-for-developer\n\n正文含 <skill-name> 占位符\n';
  const r = await extractHtml(md, { url: 'https://gitee.com/x/x', contentType: 'text/plain; charset=utf-8' });
  ok(r.used === 'passthrough' && r.content.includes('skills-for-developer'), 'text/plain markdown 透传');
  ok(r.title === 'skills-for-developer', `透传标题取首个#（实得 ${r.title}）`);
  const forced = await extractHtml(md, { url: 'file:///x', extractor: 'ui', contentType: 'text/plain' });
  ok(forced.used === 'passthrough', '强制 ui 遇非 HTML 仍透传，不给空标题');
  const j = await extractHtml('{"a":1}', { contentType: 'application/json' });
  ok(j.used === 'passthrough' && j.content.includes('"a"'), 'JSON 透传');
  const t = await runExtract(null, 'title', { forceContent: md });
  ok(t.trim() === 'skills-for-developer', 'title 模式取 markdown 首标题');
  const sk = await runExtract(null, 'skeleton', { forceContent: md });
  ok(sk.includes('skills-for-developer'), 'skeleton 模式兼容 markdown 透传');
}

// ---- 10. resolveProxy：显式覆盖 / direct / 环境 / NO_PROXY ----
{
  const t = 'http://example.com/a';
  const s = 'https://example.com/a';
  ok(resolveProxy(t, { proxy: 'http://127.0.0.1:18080', env: {} }) === 'http://127.0.0.1:18080', '显式代理覆盖环境');
  ok(resolveProxy(t, { proxy: 'direct', env: { HTTP_PROXY: 'http://127.0.0.1:18080' } }) === null, '"direct" 忽略环境强制直连');
  let bad = null;
  try {
    resolveProxy(t, { proxy: 'socks://x', env: {} });
  } catch (e) {
    bad = e;
  }
  ok(bad && /proxy 须是/.test(bad.message), '非法代理协议给出提示');
  ok(resolveProxy(s, { env: { HTTPS_PROXY: 'http://127.0.0.1:18080' } }) === 'http://127.0.0.1:18080', 'https 走 HTTPS_PROXY');
  ok(resolveProxy(t, { env: { HTTP_PROXY: 'http://127.0.0.1:18080' } }) === 'http://127.0.0.1:18080', 'http 走 HTTP_PROXY');
  ok(resolveProxy(t, { env: {} }) === null, '无环境变量直连');
  ok(resolveProxy(s, { env: { ALL_PROXY: 'http://127.0.0.1:18080' } }) === 'http://127.0.0.1:18080', 'ALL_PROXY 兜底');
  ok(
    resolveProxy('http://127.0.0.1:9/a', { env: { HTTP_PROXY: 'http://127.0.0.1:18080', NO_PROXY: '127.0.0.1' } }) === null,
    'NO_PROXY 精确主机豁免',
  );
  ok(
    resolveProxy('http://sub.example.com/a', { env: { HTTP_PROXY: 'http://127.0.0.1:18080', NO_PROXY: 'example.com' } }) === null,
    'NO_PROXY 后缀匹配子域',
  );
  ok(
    resolveProxy(t, { env: { HTTP_PROXY: 'http://127.0.0.1:18080', NO_PROXY: '*' } }) === null,
    'NO_PROXY 星号全豁免',
  );
  ok(hostBypassed('Example.COM', 'example.com') === true, 'NO_PROXY 大小写不敏感');
  ok(maskProxy('http://user:pass@127.0.0.1:18080/') === 'http://127.0.0.1:18080', '代理脱敏不泄凭据');

  // proxyOrigin：日志靠它说清"代理是谁给的"（resolveProxy 只给 URL，回答不了这个问题）。
  ok(proxyOrigin(s, { env: { HTTPS_PROXY: 'http://127.0.0.1:18080' } }).origin === 'env:HTTPS_PROXY', 'proxyOrigin 标出 HTTPS_PROXY 来源');
  ok(proxyOrigin(t, { env: { ALL_PROXY: 'http://127.0.0.1:18080' } }).origin === 'env:ALL_PROXY', 'proxyOrigin 标出 ALL_PROXY 兜底来源');
  ok(proxyOrigin(t, { proxy: 'http://127.0.0.1:18080', env: {} }).origin === 'flag', 'proxyOrigin 标出 --proxy 来源');
  ok(proxyOrigin(t, { proxy: 'direct', env: { HTTP_PROXY: 'http://127.0.0.1:18080' } }).origin === 'direct', 'proxyOrigin 标出 --noproxy');
  ok(proxyOrigin(t, { env: { HTTP_PROXY: 'http://127.0.0.1:18080', NO_PROXY: '*' } }).origin === 'noproxy', 'proxyOrigin 标出 NO_PROXY 豁免');
  ok(proxyOrigin(t, { env: {} }).origin === 'none' && proxyOrigin(t, { env: {} }).url === null, 'proxyOrigin 无代理时 none');
  ok(proxyOrigin('file:///tmp/a.html', { env: { HTTP_PROXY: 'http://127.0.0.1:18080' } }).origin === 'none', '非 http(s) 目标不走代理');
}

// ---- 11. 浏览器头重试与挑战识别 ----
{
  const md = await runExtract(`${base}/pickier`, 'markdown');
  ok(md.includes('正文内容足够长'), '简头 502 时浏览器头重试救回正文');

  let c403 = null;
  try {
    await runExtract(`${base}/challenge403`, 'markdown');
  } catch (e) {
    c403 = e;
  }
  ok(c403 && /HTTP 403/.test(c403.message), '挑战页 403 抛错带状态码');
  ok(c403 && /challenge suspected/.test(c403.message), '挑战信号被点名');
  ok(c403 && /resilient-browser-fetch/.test(c403.message), '挑战页指引渲染流水线');

  let e502 = null;
  try {
    await runExtract(`${base}/always502`, 'markdown');
  } catch (e) {
    e502 = e;
  }
  ok(e502 && /HTTP 502/.test(e502.message), '持续 502 抛错带状态码');
  ok(e502 && /both tried/.test(e502.message), '5xx 指引说明两种头都已试过');
}

// ---- 12. 代理跟随：显式 / 环境 / NO_PROXY / 黑洞 ----
// 说明：不用自造转发代理做集成测试——曾观察到其触发异常连接风暴；
// 选路逻辑只用测试内黑洞代理（秒拒）与直连成功/失败的可观测差异覆盖，不依赖外部网络。
{
  const savedEnv = {};
  for (const k of ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy']) {
    savedEnv[k] = process.env[k];
    delete process.env[k];
  }
  // 源站直连探针：黑洞代理秒拒，直连成功，二者差异即选路证据。
  try {
    process.env.HTTP_PROXY = 'http://127.0.0.1:1/';
    let viaProxy = null;
    try {
      await readSource(`${base}/article`, {});
    } catch (e) {
      viaProxy = e;
    }
    ok(viaProxy && /via proxy http:\/\/127\.0\.0\.1:1/.test(viaProxy.message), '环境代理被采用，失效时报错点名代理');

    const rDirect = await readSource(`${base}/article`, { proxy: 'direct' });
    ok(rDirect.html.includes('正文内容足够长'), '显式 direct 越过失效环境代理');

    process.env.NO_PROXY = '127.0.0.1';
    const rBypass = await readSource(`${base}/article`, {});
    ok(rBypass.html.includes('正文内容足够长'), 'NO_PROXY 豁免越过失效环境代理');
    delete process.env.NO_PROXY;

    delete process.env.HTTP_PROXY;
    process.env.HTTPS_PROXY = 'http://127.0.0.1:1/';
    const rScheme = await readSource(`${base}/article`, {});
    ok(rScheme.html.includes('正文内容足够长'), 'http 目标不受 HTTPS_PROXY 影响');
    delete process.env.HTTPS_PROXY;

    const cw = await cli([`${base}/article`, '--title', '--proxy', 'http://127.0.0.1:1/']);
    ok(cw.code === 1 && /via proxy/.test(cw.stderr), 'CLI --proxy 生效，失效时指引到代理');
    process.env.HTTP_PROXY = 'http://127.0.0.1:1/';
    const cn = await cli([`${base}/article`, '--title', '--noproxy']);
    ok(cn.code === 0 && stripMarks(cn.stdout).trim() === '本地页', 'CLI --noproxy 越过失效环境代理');
  } finally {
    for (const k of Object.keys(savedEnv)) {
      if (savedEnv[k] === undefined) delete process.env[k];
      else process.env[k] = savedEnv[k];
    }
  }
}

// ---- 13. --render 回退：静态优先 / 403·5xx 回退 / 404 不回退 / 渲染失败 ----
{
  let py = null;
  try {
    py = await findPython();
  } catch {
    py = null;
  }
  if (!py) {
    console.log('skip render tests (no python)');
  } else {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t13-'));
    try {
      const stub = path.join(dir, 'stub_save.py');
      await writeFile(
        stub,
        `import json, os, sys
argv = sys.argv[1:]
url = argv[0] if argv else ''
out = None
i = 1
while i < len(argv):
    if argv[i] == '--out' and i + 1 < len(argv):
        out = argv[i + 1]
        i += 2
    else:
        i += 1
if os.getenv('STUB_ARGV'):
    open(os.getenv('STUB_ARGV'), 'w').write(json.dumps(argv))
if os.getenv('STUB_RENDER_FAIL') == '1':
    sys.stderr.write('stub render failed: challenge unsolvable\\n')
if os.getenv('STUB_RESIDUE') == '1' and out:
    open(out + '.attempts.json', 'w').write('{}')
    open(out + '.fake.blocked.html', 'w').write('<p>blocked</p>')
if os.getenv('STUB_RENDER_FAIL') == '1':
    sys.exit(3)
marker = os.getenv('STUB_MARKER') or ''
if marker:
    open(marker, 'a').write(url + '\\n')
sys.stderr.write('stub log line: rendering ' + url + '\\n')
open(out, 'w', encoding='utf-8').write(
    '<!doctype html><html><head><title>渲染页</title></head><body>'
    '<article><h1>渲染标题</h1><p>' + '渲染正文内容足够长可以被识别为主体。' * 10 + '</p></article>'
    '</body></html>'
)
`,
        'utf8',
      );
      const marker = path.join(dir, 'calls.log');
      const argvLog = path.join(dir, 'argv.json');
      const saved = {};
      for (const k of ['HTMLMINI_RENDER_SCRIPT', 'STUB_RENDER_FAIL', 'STUB_MARKER', 'STUB_ARGV', 'STUB_RESIDUE']) {
        saved[k] = process.env[k];
      }
      process.env.HTMLMINI_RENDER_SCRIPT = stub;
      process.env.STUB_MARKER = marker;
      process.env.STUB_ARGV = argvLog;
      try {
        const ok1 = await runExtract(`${base}/article`, 'title', { render: true, renderTimeoutMs: 30000 });
        ok(ok1.trim() === '本地页', '静态成功时不走渲染');
        ok(!existsSync(marker), '静态成功未调用渲染脚本');

        const md = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        ok(md.includes('渲染正文内容足够长'), '静态 502 回退渲染取回正文');
        ok(existsSync(marker), '回退时调用了渲染脚本');

        let e404 = null;
        try {
          await runExtract(`${base}/missing`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          e404 = e;
        }
        ok(e404 && /HTTP 404/.test(e404.message), '404 不触发渲染回退');

        process.env.STUB_RENDER_FAIL = '1';
        let er = null;
        try {
          await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          er = e;
        }
        ok(er && /browser render failed/.test(er.message), '渲染失败报错点名渲染');
        delete process.env.STUB_RENDER_FAIL;

        const leftoversOf = () => readdirSync(os.tmpdir()).filter((e) => e.startsWith('htmlmini-render-'));
        process.env.STUB_RESIDUE = '1';
        const mdRes = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        ok(mdRes.includes('渲染正文内容足够长') && leftoversOf().length === 0, '成功时诊断残留一并清理');
        let erRes = null;
        process.env.STUB_RENDER_FAIL = '1';
        try {
          await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          erRes = e;
        }
        ok(erRes && /browser render failed/.test(erRes.message) && leftoversOf().length === 0, '失败时诊断残留一并清理');
        delete process.env.STUB_RENDER_FAIL;
        delete process.env.STUB_RESIDUE;

        process.env.HTMLMINI_RENDER_SCRIPT = path.join(dir, '不存在.py');
        process.env.HTMLMINI_CHROME_BIN = path.join(dir, '也没有-chrome');
        let en = null;
        try {
          await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          en = e;
        }
        ok(en && /neither save_page/.test(en.message), '双通路皆无给出安装指引');
        delete process.env.HTMLMINI_CHROME_BIN;

        process.env.HTMLMINI_RENDER_SCRIPT = stub;
        const cr = await cli([`${base}/always502`, '--title', '--render', '--render-timeout-ms', '30000']);
        ok(cr.code === 0 && stripMarks(cr.stdout).trim() === '渲染页', 'CLI --render 回退成功');
        ok(/status=unknown \(static 502\)/.test(cr.stderr), '静态 502 转渲染后日志保留静态状态码');
        ok(cr.stderr.includes('htmlmini: [render]'), '渲染日志透传到 stderr 供参考');

        const hf = await runExtract(`${base}/always502`, 'title', { render: true, headful: true, renderTimeoutMs: 30000 });
        ok(hf.trim() === '渲染页', '--headful 透传后仍取回正文');
        const gotArgv = JSON.parse(await readFile(argvLog, 'utf8'));
        ok(gotArgv.includes('--headful'), 'headful 透传给渲染脚本');

        const pxHtml = await renderViaBrowser(`${base}/always502`, { proxy: 'http://127.0.0.1:1/', renderTimeoutMs: 30000 });
        ok(pxHtml.includes('渲染标题'), '代理随渲染透传（直调 renderViaBrowser，不经过静态）');
        const gotArgv2 = JSON.parse(await readFile(argvLog, 'utf8'));
        ok(gotArgv2.includes('--proxy') && gotArgv2.includes('http://127.0.0.1:1/'), '代理 URL 透传给渲染脚本');

        const cb = await cli(['-', '--render-timeout-ms', '0']);
        ok(cb.code === 2 && /render-timeout-ms/.test(cb.stderr), '非法渲染超时退出 2');
      } finally {
        for (const k of Object.keys(saved)) {
          if (saved[k] === undefined) delete process.env[k];
          else process.env[k] = saved[k];
        }
      }
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  }
}

// ---- 13b. 解释器选择：--python-bin / HTMLMINI_PYTHON 显式即显式，指错不回退 ----
{
  let py = null;
  try {
    py = await findPython();
  } catch {
    py = null;
  }
  if (!py) {
    console.log('skip python-bin tests (no python)');
  } else {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t13b-'));
    const saved = {
      HTMLMINI_PYTHON: process.env.HTMLMINI_PYTHON,
      HTMLMINI_RENDER_SCRIPT: process.env.HTMLMINI_RENDER_SCRIPT,
      HTMLMINI_RENDER_ENGINES: process.env.HTMLMINI_RENDER_ENGINES,
      HTMLMINI_CHROME_BIN: process.env.HTMLMINI_CHROME_BIN,
    };
    try {
      const bad = path.join(dir, 'no-such-python.exe');
      ok(pythonBinOverride() === null, '默认没有解释器覆盖');
      ok((await findPython({ pythonBin: py })) === py, '--python-bin 指定可用解释器即采用');
      ok((await savePageUsable(py)) !== null, '显式解释器可探测 save_page 通路');

      process.env.HTMLMINI_PYTHON = py;
      ok(pythonBinOverride() === py, 'HTMLMINI_PYTHON 作为覆盖候选');
      ok(pythonBinOverride(path.join(dir, 'flag')) === path.join(dir, 'flag'), '--python-bin 优先于环境变量');
      delete process.env.HTMLMINI_PYTHON;

      let err = null;
      try {
        await findPython({ pythonBin: bad });
      } catch (e) {
        err = e;
      }
      ok(err && /not usable/.test(err.message) && err.message.includes(bad), '显式解释器不可用即报错，不回退到 python/python3');

      let renderErr = null;
      try {
        await renderViaBrowser(`${base}/always502`, { pythonBin: bad, renderTimeoutMs: 5000 });
      } catch (e) {
        renderErr = e;
      }
      ok(renderErr && /not usable/.test(renderErr.message), '渲染通路把解释器配置错误抛给调用方');

      // 环境变量指错时，--render 失败信息要能指名用了哪个解释器。
      process.env.HTMLMINI_PYTHON = bad;
      let envErr = null;
      try {
        await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 5000 });
      } catch (e) {
        envErr = e;
      }
      ok(envErr && envErr.message.includes(bad), 'HTMLMINI_PYTHON 指错时错误信息包含该路径');
      delete process.env.HTMLMINI_PYTHON;

      // 默认通路不可用时，错误里要提示实际探测的解释器与 --python-bin。
      // 用测试钩子声明"只有层 0 引擎"，并把零依赖 Chrome 也指错，逼出双通路皆无的分支。
      // 注意：不能同时设 HTMLMINI_RENDER_SCRIPT——显式自备渲染器按契约视为可用。
      process.env.HTMLMINI_RENDER_ENGINES = 'static';
      process.env.HTMLMINI_CHROME_BIN = path.join(dir, 'no-such-chrome');
      let hintErr = null;
      try {
        await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 5000 });
      } catch (e) {
        hintErr = e;
      }
      ok(hintErr && /neither save_page/.test(hintErr.message), '渲染不可用时给出安装指引');
      ok(hintErr && /--python-bin|HTMLMINI_PYTHON/.test(hintErr.message), '渲染不可用时提示如何指定解释器');
      ok(hintErr && /probed interpreter: /.test(hintErr.message), '渲染不可用时点名实际探测的解释器');
      for (const k of ['HTMLMINI_RENDER_ENGINES', 'HTMLMINI_CHROME_BIN']) delete process.env[k];
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
      await rm(dir, { recursive: true, force: true });
    }
  }
}

// ---- 13c. 环境扫描：HTMLMINI_PYTHON=auto 与失败路径上的备用解释器建议 ----
{
  let py = null;
  try {
    py = await findPython();
  } catch {
    py = null;
  }
  if (!py) {
    console.log('skip env-scan tests (no python)');
  } else {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t13c-'));
    const saved = {
      HTMLMINI_PYTHON: process.env.HTMLMINI_PYTHON,
      HTMLMINI_ENV_SCAN_SCRIPT: process.env.HTMLMINI_ENV_SCAN_SCRIPT,
      HTMLMINI_ENV_SCAN: process.env.HTMLMINI_ENV_SCAN,
      HTMLMINI_RENDER_SCRIPT: process.env.HTMLMINI_RENDER_SCRIPT,
      HTMLMINI_RENDER_ENGINES: process.env.HTMLMINI_RENDER_ENGINES,
      HTMLMINI_CHROME_BIN: process.env.HTMLMINI_CHROME_BIN,
    };
    const scanStub = async (target, engines) => {
      const stubDir = path.join(dir, target);
      await mkdir(stubDir, { recursive: true });
      const file = path.join(stubDir, 'check_environment.py');
      await writeFile(
        file,
        'def scan_environments(required, scripts_dir):\n'
          + '    return [\n'
          + `        {"ok": True, "path": ${JSON.stringify(engines.recommended)}, "engines": ${JSON.stringify(engines.of)}, "manager": "conda:fake", "satisfies": []},\n`
          + '        {"ok": True, "path": "C:/fake/system/python.exe", "engines": ["static"], "manager": "system", "satisfies": list(required)},\n'
          + '    ]\n',
        'utf8',
      );
      return file;
    };
    try {
      // 1) 扫描能挑出具备层的解释器（推荐项指向真实可用的 python）
      const goodScan = await scanStub('scan-good', { recommended: py, of: ['static', 'playwright'] });
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = goodScan;
      resetEnvScanCache();
      const found = await findCapablePython(['playwright']);
      ok(found && found.recommended === py, '环境扫描返回具备层 >= 1 的解释器');
      ok((found.engines ?? []).includes('playwright'), '扫描结果带上该解释器的引擎列表');

      // 2) HTMLMINI_PYTHON=auto：渲染自动改用扫描到的解释器
      const saveStub = path.join(dir, 'stub_save.py');
      await writeFile(
        saveStub,
        `import sys
argv = sys.argv[1:]
out = argv[argv.index('--out') + 1]
open(out, 'w', encoding='utf-8').write(
    '<!doctype html><html><head><title>自动解释器</title></head><body>'
    '<article><h1>自动解释器标题</h1><p>' + '自动选择的解释器渲染内容足够长可以被识别。' * 10 + '</p></article>'
    '</body></html>'
)
`,
        'utf8',
      );
      process.env.HTMLMINI_RENDER_SCRIPT = saveStub;
      process.env.HTMLMINI_PYTHON = 'auto';
      ok((await findPython()) === py, 'HTMLMINI_PYTHON=auto 解析成扫描到的解释器');
      const autoTitle = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
      ok(autoTitle.trim() === '自动解释器', 'auto 选择的解释器完成了 save_page 渲染');
      delete process.env.HTMLMINI_PYTHON;
      delete process.env.HTMLMINI_RENDER_SCRIPT;

      // 3) 扫描不可用时，auto 给出明确错误而不是静默失败
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = path.join(dir, 'missing-scan.py');
      resetEnvScanCache();
      ok((await findCapablePython(['playwright'])) === null, '扫描脚本缺失时返回 null 而不抛错');
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = goodScan;
      process.env.HTMLMINI_ENV_SCAN = '0';
      resetEnvScanCache();
      let disabled = 'unset';
      try {
        disabled = await findPython({ pythonBin: 'auto' });
      } catch (e) {
        disabled = e.message;
      }
      ok(/仍未找到|not usable|未找到/.test(String(disabled)), '关闭扫描时 auto 明确报错');
      delete process.env.HTMLMINI_ENV_SCAN;

      // 4) 双通路皆无时，错误信息建议扫描到的备用解释器
      process.env.HTMLMINI_RENDER_ENGINES = 'static';
      process.env.HTMLMINI_CHROME_BIN = path.join(dir, 'no-such-chrome');
      const scanHint = await scanStub('scan-hint', {
        recommended: 'C:/fake/conda/envs/scrapling/python.exe',
        of: ['static', 'scrapling'],
      });
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = scanHint;
      resetEnvScanCache();
      let hintErr = null;
      try {
        await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 5000 });
      } catch (e) {
        hintErr = e;
      }
      ok(hintErr && hintErr.message.includes('C:/fake/conda/envs/scrapling/python.exe'), '渲染不可用时点名另一台环境的解释器');
      ok(hintErr && /HTMLMINI_PYTHON=auto/.test(hintErr.message), '并给出 auto 这条快捷方式');
      for (const k of ['HTMLMINI_RENDER_ENGINES', 'HTMLMINI_CHROME_BIN', 'HTMLMINI_ENV_SCAN_SCRIPT']) delete process.env[k];
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
      await rm(dir, { recursive: true, force: true });
    }
  }
}

// ---- 13d. 渲染失败自动升档：扫描到更强解释器，显式指定时不换 ----
{
  let py = null;
  try {
    py = await findPython();
  } catch {
    py = null;
  }
  if (!py) {
    console.log('skip env-scan escalation tests (no python)');
  } else {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t13d-'));
    const saved = {
      HTMLMINI_PYTHON: process.env.HTMLMINI_PYTHON,
      HTMLMINI_ENV_SCAN_SCRIPT: process.env.HTMLMINI_ENV_SCAN_SCRIPT,
      HTMLMINI_ENV_SCAN: process.env.HTMLMINI_ENV_SCAN,
    };
    const strong = 'C:/fake/conda/envs/scrapling/python.exe';
    const weak = 'C:/fake/system/python.exe';
    try {
      delete process.env.HTMLMINI_PYTHON;
      const stubDir = path.join(dir, 'scan');
      await mkdir(stubDir, { recursive: true });
      await writeFile(
        path.join(stubDir, 'check_environment.py'),
        'def scan_environments(required, scripts_dir):\n'
          + '    return [\n'
          + `        {"ok": True, "path": ${JSON.stringify(strong)}, "engines": ["static", "playwright", "scrapling"], "levels": [0, 1, 2], "manager": "conda:scrapling", "satisfies": []},\n`
          + `        {"ok": True, "path": ${JSON.stringify(weak)}, "engines": ["static", "playwright"], "levels": [0, 1], "manager": "system", "satisfies": []},\n`
          + '    ]\n',
        'utf8',
      );
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = path.join(stubDir, 'check_environment.py');
      resetEnvScanCache();

      const list = await scanPythonEnvironments(['playwright']);
      ok(list.length === 2 && list[0].path === strong, '扫描返回按能力排序的候选列表');
      ok((await findCapablePython(['playwright'])).recommended === strong, 'findCapablePython 仍取扫描首选');

      const picked = await pickStrongerPython({ pythonBin: undefined, current: weak });
      ok(picked && picked.recommended === strong && picked.level >= 2, '未显式指定时挑出层 >= 2 的更强解释器');
      ok((await pickStrongerPython({ pythonBin: weak, current: weak })) === null, '显式指定解释器后不再自动升档');
      ok((await pickStrongerPython({ pythonBin: undefined, current: strong })) === null, '当前已是扫描首选时不重复升档');

      process.env.HTMLMINI_ENV_SCAN = '0';
      resetEnvScanCache();
      ok((await pickStrongerPython({ pythonBin: undefined, current: weak })) === null, 'HTMLMINI_ENV_SCAN=0 时关闭自动升档');
      delete process.env.HTMLMINI_ENV_SCAN;

      ok(isInterpreterRetryable(new Error('rendered page still looks like a challenge (cloudflare)')), '挑战判定可触发升档');
      ok(isInterpreterRetryable(new Error('save_page: 所有引擎均失败')), '引擎失败可触发升档');
      ok(!isInterpreterRetryable(new Error('HTTP 404 not found')), '404 不触发升档');
      ok(!isInterpreterRetryable(new Error('--python-bin/HTMLMINI_PYTHON interpreter is not usable: x')), '解释器配置错误不触发升档');
      ok(!isInterpreterRetryable(new Error('no python found (tried python/python3)')), '没有 python 时不触发升档');

      // 5) 求解环境的挑选：只认装了 scrapling/cloak-cdp 的解释器
      const solverFound = await findSolverPython();
      ok(solverFound && solverFound.path === strong, '挑出带挑战求解引擎的解释器');
      ok((solverFound?.engines ?? []).includes('scrapling'), '求解环境带上引擎列表');
      const noSolverScan = path.join(dir, 'scan-nosolver');
      await mkdir(noSolverScan, { recursive: true });
      await writeFile(
        path.join(noSolverScan, 'check_environment.py'),
        'def scan_environments(required, scripts_dir):\n'
          + '    return [\n'
          + `        {"ok": True, "path": ${JSON.stringify(weak)}, "engines": ["static", "playwright"], "levels": [0, 1], "manager": "system", "satisfies": []},\n`
          + '    ]\n',
        'utf8',
      );
      process.env.HTMLMINI_ENV_SCAN_SCRIPT = path.join(noSolverScan, 'check_environment.py');
      resetEnvScanCache();
      ok((await findSolverPython()) === null, '没有求解引擎时不给推荐环境');
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
      resetEnvScanCache();
      await rm(dir, { recursive: true, force: true });
    }
  }
}

// ---- 13e. 求解引擎的 60s 预算下限：预算不够时不进求解层 ----
{
  ok(resolveSavePageEngine({ solver: true, renderTimeoutMs: 300000 }) === 'auto', '预算够时 auto 阶梯照旧（求解层可用）');
  ok(resolveSavePageEngine({ solver: true, renderTimeoutMs: 9000 }) === 'playwright', '预算不够求解引擎时钉到层 1');
  ok(resolveSavePageEngine({ solver: false, renderTimeoutMs: 9000 }) === 'auto', '没有求解引擎时不受预算影响');
  ok(resolveSavePageEngine({ renderEngine: 'scrapling', solver: true, renderTimeoutMs: 300000 }) === 'scrapling', '显式钉引擎优先于预算');
  ok(resolveSavePageEngine({ renderEngine: 'auto', solver: true, renderTimeoutMs: 300000 }) === 'auto', '显式 auto 等同默认');
}

// ---- 13f. render=always 不能由 save_page 的 static 层交差（那是没执行 JS 的页面） ----
{
  let py = null;
  try {
    py = await findPython();
  } catch {
    py = null;
  }
  if (!py) {
    console.log('skip hydration-retry tests (no python)');
  } else {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t13f-'));
    const saved = {};
    try {
      const calls = path.join(dir, 'calls.log');
      const stub = path.join(dir, 'stub_hydrate.py');
      // 模拟 save_page 的真实阶梯：--engine auto 先由 static 层"成功"，交回未水合 HTML；
      // 只有浏览器层才给执行过 JS 的正文。
      await writeFile(
        stub,
        `import json, os, sys
argv = sys.argv[1:]
out = argv[argv.index('--out') + 1]
engine = argv[argv.index('--engine') + 1] if '--engine' in argv else 'auto'
open(os.environ['STUB_CALLS'], 'a', encoding='utf-8').write(json.dumps({
    'engine': engine,
    'wait_selector': argv[argv.index('--wait-selector') + 1] if '--wait-selector' in argv else None,
    'post_wait_ms': argv[argv.index('--post-wait-ms') + 1] if '--post-wait-ms' in argv else None,
    'expect_texts': [argv[i + 1] for i, a in enumerate(argv) if a == '--expect-text'],
}) + '\\n')
if engine == 'auto':
    html = ('<!doctype html><html><head><title>静态壳</title></head><body><article><h1>静态壳</h1><p>'
            + '静态抓取拿到正文但下拉列表是空的。' * 20 + '</p></article></body></html>')
else:
    html = ('<!doctype html><html><head><title>水合页</title></head><body><article><h1>水合页</h1><p>'
            + '水合后的正文包含异步加载的清单。' * 20
            + '</p><select id="nodeSelector"><option>gh-proxy.com</option></select></article></body></html>')
open(out, 'w', encoding='utf-8').write(html)
json.dump({'status': 200, 'engine': 'static' if engine == 'auto' else engine,
          'proxy': 'http://127.0.0.1:7897'},
          open(out + '.meta.json', 'w', encoding='utf-8'))
`,
        'utf8',
      );
      const fakeChrome = path.join(dir, 'fake-chrome.mjs');
      const chromeMarker = path.join(dir, 'chrome.log');
      await writeFile(
        fakeChrome,
        `import { appendFileSync } from 'node:fs';
if (process.env.CHROME_MARKER) appendFileSync(process.env.CHROME_MARKER, 'chrome-invoked\\n');
process.stdout.write('<!doctype html><html><head><title>Chrome页</title></head><body>'
  + '<article><h1>Chrome标题</h1><p>' + 'Chrome正文内容足够长可以被识别为主体。'.repeat(10) + '</p></article>'
  + '</body></html>');
`,
        'utf8',
      );
      for (const k of ['HTMLMINI_RENDER_SCRIPT', 'STUB_CALLS', 'HTMLMINI_CHROME_BIN', 'CHROME_MARKER']) saved[k] = process.env[k];
      process.env.HTMLMINI_RENDER_SCRIPT = stub;
      process.env.STUB_CALLS = calls;
      process.env.HTMLMINI_CHROME_BIN = fakeChrome;
      process.env.CHROME_MARKER = chromeMarker;

      const hydrated = await runExtract(`${base}/article`, 'markdown', { render: 'always', renderTimeoutMs: 90000 });
      const first = (await readFile(calls, 'utf8')).trim().split('\n').map((l) => JSON.parse(l));
      ok(hydrated.includes('水合后的正文'), 'render=always 拿到执行过 JS 的正文');
      ok(first.length === 2 && first[1].engine === 'playwright', 'static 层交差后改用 playwright 重渲染');

      await writeFile(calls, '');
      await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 90000 });
      const fallback = (await readFile(calls, 'utf8')).trim().split('\n').map((l) => JSON.parse(l));
      ok(fallback.length === 1 && fallback[0].engine === 'auto', '非 always 的回退路径不为水合多跑一次');

      // 等待参数只能由 save_page 执行：给了就不许退到 chrome dump-dom。
      await writeFile(calls, '');
      await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 90000, waitSelector: '#nodeSelector option', postWaitMs: 1500 });
      const waited = (await readFile(calls, 'utf8')).trim().split('\n').map((l) => JSON.parse(l));
      ok(waited.length === 1 && waited[0].wait_selector === '#nodeSelector option' && waited[0].post_wait_ms === '1500', '等待参数透传到 save_page');
      ok(!existsSync(chromeMarker), '给了 --wait-selector 时不退到 chrome dump-dom');

      // 没传 --proxy 时 save_page 自己发现代理；实际出口要从 meta 回读，不能报成 none。
      const meta = {};
      await renderViaBrowser(`${base}/always502`, { info: meta, pythonBin: py, renderTimeoutMs: 90000 });
      ok(meta.proxy === 'http://127.0.0.1:7897', '回读 save_page meta 的实际出口');
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
      await rm(dir, { recursive: true, force: true });
    }
  }
}

// ---- 13g. 水合重试的引擎挑选：静态清单为空时不静默交差 ----
{
  ok(pickHydrationEngine({ engines: ['static', 'playwright'] }) === 'playwright', '有 playwright 时用它重渲染');
  ok(pickHydrationEngine({ engines: null }) === 'playwright', '旧版脚本不报引擎清单时按层 1 试');
  ok(pickHydrationEngine({ engines: ['static', 'scrapling'], renderTimeoutMs: 90000 }) === 'scrapling', '没有纯渲染层时用求解引擎');
  ok(pickHydrationEngine({ engines: ['static', 'scrapling'], renderTimeoutMs: 9000 }) === null, '求解引擎预算不够时明确失败');
  ok(pickHydrationEngine({ engines: ['static'] }) === null, '没有浏览器层时明确失败');
}

// ---- 13h. 目标断言：抓到了页面但没有目标块，不能算成功 ----
{
  const hit = await runExtract(`${base}/article`, 'text', { expectTexts: ['正文内容足够长'] });
  ok(hit.includes('正文内容足够长'), '目标文本命中时正常返回');

  let missing = null;
  try {
    await runExtract(`${base}/article`, 'text', { expectTexts: ['正文内容足够长', '不存在的标记'] });
  } catch (e) {
    missing = e;
  }
  ok(missing && /missing expected text/.test(missing.message) && missing.expectedTextMissing === true, '目标文本缺失时明确失败');
  ok(!isInterpreterRetryable(missing), '目标文本缺失不触发解释器升档');
  ok(/--render=always/.test(missing.message), '静态缺文本时提示先渲染');
}

// ---- 13i. 断言命中但输出里没有：提示换模式，而不是让人以为抓取失败 ----
{
  const html = '<!doctype html><html><head><title>清单页</title></head><body><article><h1>清单页</h1>'
    + `<p>${'这是一段足够长的正文，用来确保抽取结果不会被判定成空壳页面。'.repeat(4)}</p>`
    + '<select id="nodeSelector"><option>only-in-select.example</option></select></article></body></html>';
  const md = await runExtractDetailed('content', 'markdown', { forceContent: html, expectTexts: ['only-in-select.example'] });
  ok(!md.output.includes('only-in-select.example'), 'markdown 输出不含 select 选项');
  ok(md.info.expectTextsNotInOutput?.length === 1, '断言命中但不在输出里时记到 info');
  const ui = await runExtractDetailed('content', 'ui', { forceContent: html, expectTexts: ['only-in-select.example'] });
  ok(ui.output.includes('only-in-select.example') && !ui.info.expectTextsNotInOutput, 'ui 收下控件值后不再提示');
}

// ---- 14. Chrome 直渲通路：零依赖回退 / headful 限制 / save_page 优先 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t14-'));
  try {
    const fakeChrome = path.join(dir, 'fake-chrome.mjs');
    await writeFile(
      fakeChrome,
      `import { appendFileSync } from 'node:fs';
const marker = process.env.CHROME_MARKER;
if (marker) appendFileSync(marker, 'chrome-invoked\\n');
process.stdout.write('<!doctype html><html><head><title>Chrome页</title></head><body>'
  + '<article><h1>Chrome标题</h1><p>' + 'Chrome正文内容足够长可以被识别为主体。'.repeat(10) + '</p></article>'
  + '</body></html>');
`,
      'utf8',
    );
    const chromeMarker = path.join(dir, 'chrome.log');
    const saveMarker = path.join(dir, 'save.log');
    const stub = path.join(dir, 'stub_save.py');
    await writeFile(
      stub,
      `import os, sys
argv = sys.argv[1:]
out = None
i = 1
while i < len(argv):
    if argv[i] == '--out' and i + 1 < len(argv):
        out = argv[i + 1]
        i += 2
    else:
        i += 1
open(os.getenv('STUB_MARKER'), 'a').write('save-page\\n')
open(out, 'w', encoding='utf-8').write(
    '<!doctype html><html><head><title>Save页</title></head><body>'
    '<article><h1>Save标题</h1><p>' + 'Save正文内容足够长可以被识别为主体。' * 10 + '</p></article>'
    '</body></html>'
)
`,
      'utf8',
    );
    const saved = {};
    for (const k of ['HTMLMINI_RENDER_SCRIPT', 'HTMLMINI_CHROME_BIN', 'HTMLMINI_CHROME_EXTRA_ARGS', 'CHROME_MARKER', 'STUB_MARKER']) {
      saved[k] = process.env[k];
    }
    try {
      process.env.HTMLMINI_RENDER_SCRIPT = path.join(dir, '不存在.py');
      process.env.HTMLMINI_CHROME_BIN = process.execPath;
      process.env.HTMLMINI_CHROME_EXTRA_ARGS = fakeChrome;
      process.env.CHROME_MARKER = chromeMarker;
      const t = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
      ok(t.trim() === 'Chrome页', 'save_page 不可用时回退 Chrome 直渲');
      ok(existsSync(chromeMarker), 'Chrome 通路被实际调用');

      let eh = null;
      try {
        await runExtract(`${base}/always502`, 'title', { render: true, headful: true, renderTimeoutMs: 30000 });
      } catch (e) {
        eh = e;
      }
      ok(eh && /--headful needs the save_page/.test(eh.message), 'Chrome 通路下 headful 给出明确限制');

      const cbad = await cli([`${base}/always502`, '--title', '--render', '--chrome-bin', path.join(dir, '不存在.exe')]);
      ok(cbad.code === 1 && /chrome binary not found/.test(cbad.stderr), 'CLI --chrome-bin 不存在给出提示');

      process.env.HTMLMINI_CHROME_EXTRA_ARGS = fakeChrome;
      const cexp = await cli([`${base}/always502`, '--title', '--render', '--chrome-bin', process.execPath]);
      ok(cexp.code === 0 && stripMarks(cexp.stdout).trim() === 'Chrome页', 'CLI --chrome-bin 显式指定生效');
      delete process.env.HTMLMINI_CHROME_EXTRA_ARGS;

      process.env.HTMLMINI_RENDER_SCRIPT = stub;
      process.env.STUB_MARKER = saveMarker;
      if (existsSync(chromeMarker)) await rm(chromeMarker, { force: true });
      let py14 = null;
      try {
        py14 = await findPython();
      } catch {
        py14 = null;
      }
      if (!py14) {
        console.log('skip save_page-preferred (no python)');
      } else {
        const s = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
        ok(s.trim() === 'Save页', 'save_page 可用时优先走 save_page');
        ok(existsSync(saveMarker) && !existsSync(chromeMarker), '优先顺序下 Chrome 未被调用');
      }
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 14b. 渲染后的挑战空壳判据 + --render-engine 钉层 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t14b-'));
  const saved = {};
  for (const k of [
    'HTMLMINI_RENDER_SCRIPT',
    'HTMLMINI_CHROME_BIN',
    'HTMLMINI_CHROME_EXTRA_ARGS',
    'HTMLMINI_RENDER_ENGINES',
    'STUB_ARGV',
    'CHROME_MARKER',
  ]) {
    saved[k] = process.env[k];
  }
  try {
    const argvLog = path.join(dir, 'argv.json');
    const chromeMarker = path.join(dir, 'chrome.log');
    const stub = path.join(dir, 'stub_save.py');
    // 桩按 STUB_BODY 选择输出：challenge（挑战空壳）/ article（长正文，含挑战字样但不该误判）。
    await writeFile(
      stub,
      `import json, os, sys
argv = sys.argv[1:]
out = argv[argv.index('--out') + 1]
open(os.getenv('STUB_ARGV'), 'w').write(json.dumps(argv))
mode = os.getenv('STUB_BODY') or 'article'
if mode == 'challenge':
    html = ('<!doctype html><html><head><title>Just a moment...</title></head><body>'
            '<div id="cf-chl-widget">Enable JavaScript and cookies to continue</div></body></html>')
elif mode == 'short-mention':
    html = ('<!doctype html><html><head><title>联系表单</title></head><body><form><p>'
            '本站用 challenges.cloudflare.com 与 turnstile 做验证。'
            '</p></form></body></html>')
elif mode == 'block':
    html = ('<!doctype html><html><head><title>Access Denied</title></head><body>'
            '<p>You do not have permission to access this resource.</p></body></html>')
else:
    html = ('<!doctype html><html><head><title>挑战机制</title></head><body><article><h1>挑战机制</h1><p>'
            + '正文提到 challenges.cloudflare.com 与 turnstile 的机制。' * 30
            + '</p></article></body></html>')
open(out, 'w', encoding='utf-8').write(html)
`,
      'utf8',
    );
    const fakeChrome = path.join(dir, 'fake-chrome.mjs');
    await writeFile(
      fakeChrome,
      `import { appendFileSync } from 'node:fs';
const marker = process.env.CHROME_MARKER;
if (marker) appendFileSync(marker, 'chrome-invoked\\n');
process.stdout.write('<!doctype html><html><head><title>Chrome页</title></head><body>'
  + '<article><h1>Chrome标题</h1><p>' + 'Chrome正文内容足够长可以被识别为主体。'.repeat(10) + '</p></article>'
  + '</body></html>');
`,
      'utf8',
    );
    process.env.HTMLMINI_RENDER_SCRIPT = stub;
    process.env.STUB_ARGV = argvLog;
    process.env.HTMLMINI_CHROME_BIN = process.execPath;
    process.env.HTMLMINI_CHROME_EXTRA_ARGS = fakeChrome;
    process.env.CHROME_MARKER = chromeMarker;

    // 1) 渲染后仍是挑战空壳：报挑战而不是"像客户端渲染壳"，并给可行下一步。
    process.env.STUB_BODY = 'challenge';
    let guardErr = null;
    try {
      await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
    } catch (e) {
      guardErr = e;
    }
    ok(guardErr && /looks like a challenge/.test(guardErr.message), `挑战空壳被判为挑战（实得 ${guardErr && guardErr.message.slice(0, 80)}）`);
    ok(guardErr && /--python-bin auto/.test(guardErr.message), '挑战判定给出求解引擎的下一步');
    ok(guardErr && !/app shell/.test(guardErr.message), '不再误报成客户端渲染壳');
    const kept = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000, allowEmpty: true });
    ok(typeof kept === 'string', '--allow-empty 仍可取回挑战 HTML 供排查');

    // 2) 正文里出现挑战字样不该误判：长正文、以及"短但有内容"的页面都不算空壳。
    process.env.STUB_BODY = 'article';
    const long = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
    ok(long.includes('正文提到'), '长正文提到挑战机制不被误判');
    process.env.STUB_BODY = 'short-mention';
    const shortMention = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
    ok(typeof shortMention === 'string' && shortMention.includes('验证'), '短页面提到挑战域名不被误判（判据是内部标识而非裸词）');

    // 2b) WAF 拒绝页（标题 "Access Denied"）：不能当成正文交出去，也不能报成"挑战页"。
    //     它是终局，下一步是换引擎/换出口，与"挑战还在跑"的下一步不同。
    process.env.STUB_BODY = 'block';
    let blockErr = null;
    try {
      await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000 });
    } catch (e) {
      blockErr = e;
    }
    ok(blockErr && /block page/.test(blockErr.message), `WAF 拒绝页被判为拒绝页（实得 ${blockErr && blockErr.message.slice(0, 80)}）`);
    ok(blockErr && /chrome-late/.test(blockErr.message), '拒绝页给出晚接入引擎的下一步');
    ok(blockErr && !/looks like a challenge/.test(blockErr.message), '拒绝页不误报成挑战页');
    const blockKept = await runExtract(`${base}/always502`, 'markdown', { render: true, renderTimeoutMs: 30000, allowEmpty: true });
    ok(typeof blockKept === 'string', '--allow-empty 仍可取回拒绝页 HTML 供排查');

    // 3) --render-engine 钉住时强制 save_page，不让零依赖 Chrome 顶掉选择。
    process.env.STUB_BODY = 'article';
    if (existsSync(chromeMarker)) await rm(chromeMarker, { force: true });
    const pinned = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000, renderEngine: 'playwright' });
    ok(pinned.trim() === '挑战机制', '钉层后走 save_page 取得正文');
    const pinnedArgv = JSON.parse(await readFile(argvLog, 'utf8'));
    ok(pinnedArgv.includes('--engine') && pinnedArgv.includes('playwright'), '钉层透传给 save_page');
    ok(!existsSync(chromeMarker), '钉层时零依赖 Chrome 未被调用');

    const bad = await cli([`${base}/always502`, '--render', '--render-engine', 'static']);
    ok(bad.code === 2 && /render-engine/.test(bad.stderr), '非渲染层取值退出 2');

    // 4) 参数顺序回归: --render=always 后面跟 --headful 不能把"总是渲染"降级成"仅 403/5xx 回退"。
    //    降级后静态 200 的应用壳不会触发渲染, 直接报"像客户端渲染壳"。
    process.env.STUB_BODY = 'article';
    const forced = await cli([
      `${base}/shell200`,
      '--render=always',
      '--headful',
      '--render-timeout-ms',
      '30000',
    ]);
    ok(
      forced.code === 0 && stripMarks(forced.stdout).includes('正文提到'),
      `--render=always --headful 仍然强制渲染（退出 ${forced.code}）`
        + ` | stdout=${JSON.stringify(stripMarks(forced.stdout).slice(0, 80))}`,
    );
    ok(
      !/app shell|客户端渲染壳/.test(String(forced.stderr)),
      '强制渲染时不再退化成"像客户端渲染壳"的报错',
    );
    const forcedArgv = JSON.parse(await readFile(argvLog, 'utf8'));
    ok(forcedArgv.includes('--headful'), '强制渲染时把 --headful 透传给 save_page');

    process.env.HTMLMINI_RENDER_ENGINES = 'static';
    process.env.HTMLMINI_CHROME_BIN = path.join(dir, '没有-chrome');
    delete process.env.HTMLMINI_RENDER_SCRIPT;
    let pinErr = null;
    try {
      await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 5000, renderEngine: 'scrapling' });
    } catch (e) {
      pinErr = e;
    }
    ok(pinErr && /--render-engine scrapling needs the save_page renderer/.test(pinErr.message), '钉层但缺 save_page 通路时直说原因');
  } finally {
    delete process.env.STUB_BODY;
    for (const [k, v] of Object.entries(saved)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 15. Playwright 缓存探测：三平台布局 / 版本排序 / 无头壳兜底 ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-pw-'));
  try {
    const touch = async (...parts) => {
      const f = path.join(dir, ...parts);
      await import('node:fs/promises').then((m) => m.mkdir(path.dirname(f), { recursive: true }));
      await writeFile(f, 'x');
      return f;
    };
    const winFull = await touch('win', 'chromium-1200', 'chrome-win64', 'chrome.exe');
    const winFull1210 = await touch('win', 'chromium-1210', 'chrome-win64', 'chrome.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win'), 'win32') === winFull1210, 'win 取版本最大者');
    ok(pickPlaywrightChrome(path.join(dir, 'empty'), 'win32') === null, '空缓存返回 null');
    const winShell = await touch('win-shell', 'chromium-1200', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win-shell'), 'win32') === winShell, 'win 无完整版时用无头壳兜底');

    // 旧布局（chrome-win/chrome-linux/chrome-mac）仍需命中：两个版本的新旧目录并存时优先取版本大者。
    const winLegacy = await touch('win-legacy', 'chromium-1100', 'chrome-win', 'chrome.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win-legacy'), 'win32') === winLegacy, 'win 旧布局 chrome-win 仍命中');
    const winMixed = await touch('win-mixed', 'chromium-1130', 'chrome-win', 'chrome.exe');
    const winMixedNew = await touch('win-mixed', 'chromium-1200', 'chrome-win64', 'chrome.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win-mixed'), 'win32') === winMixedNew, 'win 新旧布局并存取版本大者');

    const linFull = await touch('lin', 'chromium-1180', 'chrome-linux64', 'chrome');
    ok(pickPlaywrightChrome(path.join(dir, 'lin'), 'linux') === linFull, 'linux 新布局命中');
    const linLegacy = await touch('lin-legacy', 'chromium-1180', 'chrome-linux', 'chrome');
    ok(pickPlaywrightChrome(path.join(dir, 'lin-legacy'), 'linux') === linLegacy, 'linux 旧布局命中');
    const macFull = await touch('mac', 'chromium-1190', 'chrome-mac-arm64', 'Chromium.app', 'Contents', 'MacOS', 'Chromium');
    ok(pickPlaywrightChrome(path.join(dir, 'mac'), 'darwin') === macFull, 'mac 新布局命中');
    ok(pickPlaywrightChrome(path.join(dir, 'lin'), 'win32') === null, '平台布局错配不命中');
    void winFull;
    void winMixed;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 16. save_page 可用性口径：层 >= 1 才走 save_page，层 0 退化到零依赖 Chrome ----
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-t16-'));
  try {
    const fakeChrome = path.join(dir, 'fake-chrome.mjs');
    await writeFile(
      fakeChrome,
      `import { appendFileSync } from 'node:fs';
const marker = process.env.CHROME_MARKER;
if (marker) appendFileSync(marker, 'chrome-invoked\\n');
process.stdout.write('<!doctype html><html><head><title>Chrome页</title></head><body>'
  + '<article><h1>Chrome标题</h1><p>' + 'Chrome正文内容足够长可以被识别为主体。'.repeat(10) + '</p></article>'
  + '</body></html>');
`,
      'utf8',
    );
    const chromeMarker = path.join(dir, 'chrome.log');
    const saved = {};
    for (const k of [
      'HTMLMINI_RENDER_SCRIPT',
      'HTMLMINI_CHROME_BIN',
      'HTMLMINI_CHROME_EXTRA_ARGS',
      'HTMLMINI_RENDER_ENGINES',
      'CHROME_MARKER',
    ]) {
      saved[k] = process.env[k];
    }
    try {
      delete process.env.HTMLMINI_RENDER_SCRIPT; // 用真实同级脚本，让引擎探测生效
      process.env.HTMLMINI_CHROME_BIN = process.execPath;
      process.env.HTMLMINI_CHROME_EXTRA_ARGS = fakeChrome;
      process.env.CHROME_MARKER = chromeMarker;
      process.env.HTMLMINI_RENDER_ENGINES = 'playwright';
      const probeOk = (await savePageUsable()) !== null;
      if (!probeOk) {
        console.log('skip save_page engine-floor (renderer not installed beside htmlmini)');
      } else {
        ok((await savePageUsable()) !== null, '层 1 引擎被判为 save_page 可用');
        process.env.HTMLMINI_RENDER_ENGINES = 'scrapling,cloak-cdp';
        ok((await savePageUsable()) !== null, '层 2/3 引擎被判为 save_page 可用');
        process.env.HTMLMINI_RENDER_ENGINES = 'static';
        ok((await savePageUsable()) === null, '只有层 0 时不判 save_page 可用');
        const degraded = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
        ok(degraded.trim() === 'Chrome页', '只有层 0 时退化到零依赖 Chrome 通路');
        ok(existsSync(chromeMarker), '退化路径确实调用了 Chrome');

        // 层 1 与零依赖 Chrome 同能力（都只渲染、不求解挑战）：有 Chrome 时仍走 Chrome，避免为渲染再启 python 通路。
        process.env.HTMLMINI_RENDER_ENGINES = 'playwright';
        await rm(chromeMarker, { force: true });
        const parity = await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
        ok(parity.trim() === 'Chrome页', '层 1 与 Chrome 同能力时仍走零依赖通路');
        ok(existsSync(chromeMarker), '同能力场景下 save_page 未被优先调用');

        // 没有求解引擎、又没有 Chrome 时，层 1 仍是最后兜底（此处 save_page 真实执行并按其校验失败）。
        process.env.HTMLMINI_CHROME_BIN = path.join(dir, '不存在-chrome.exe');
        let fallbackErr = null;
        try {
          await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          fallbackErr = e;
        }
        ok(fallbackErr && /browser render failed/.test(fallbackErr.message), '无 Chrome 时层 1 兜底走 save_page');
        process.env.HTMLMINI_CHROME_BIN = process.execPath;

        // 零依赖通路崩溃但同能力引擎仍在时，再试一次 save_page（错误里两段都要出现）。
        const brokenChrome = path.join(dir, 'broken-chrome.mjs');
        await writeFile(brokenChrome, 'process.exit(21);\n', 'utf8');
        process.env.HTMLMINI_CHROME_EXTRA_ARGS = brokenChrome;
        let doubleErr = null;
        try {
          await runExtract(`${base}/always502`, 'title', { render: true, renderTimeoutMs: 30000 });
        } catch (e) {
          doubleErr = e;
        }
        ok(
          doubleErr && /chrome render failed/.test(doubleErr.message) && /save_page 回退也失败/.test(doubleErr.message),
          'Chrome 通路失败后回退 save_page 并合并报错',
        );
        process.env.HTMLMINI_CHROME_EXTRA_ARGS = fakeChrome;
      }
    } finally {
      for (const [k, v] of Object.entries(saved)) {
        if (v === undefined) delete process.env[k];
        else process.env[k] = v;
      }
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// 短选项：长选项是主名，短选项给高频开关（条件允许时同时给，不能冲突、不能歧义）。
{
  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-short-'));
  try {
    const page = path.join(dir, 'p.html');
    await writeFile(page, '<html><head><title>短选项页</title></head><body><h1>短选项页</h1></body></html>');
    const viaShort = await cli(['-b', 'edge', '-p', 'direct', '--title', page]);
    ok(viaShort.code === 0 && viaShort.stdout.includes('短选项页'), '短选项 -b / -p 生效');
    const badBrand = await cli(['-b', 'safari', '--title', page]);
    ok(badBrand.code === 2 && /browser-brand/.test(badBrand.stderr), '短选项 -b 非法值退出 2');
    const badEngine = await cli(['-e', 'nope', '--title', page]);
    ok(badEngine.code === 2, '短选项 -e 非法引擎退出 2');
    // -r 允许带可选值：-r always 表示总是渲染
    const renderAlways = await cli(['-r', 'always', '--title', page]);
    ok(renderAlways.code === 0, '短选项 -r always 生效');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// save_page 的浏览器路径必须真的传下去：WAF 可能按客户端品牌判负
// （实测同一出口、同一协议 Chrome 被拒、Edge 放行）。早先 --chrome-bin
// 只喂给零依赖的 chrome dump-dom 通路，走 save_page(chrome-late) 时被静默丢掉。
{
  const base = {
    script: 'C:/skill/scripts/resilient_fetch.py',
    url: 'https://example.com/item',
    out: 'C:/tmp/out.html',
    engine: 'chrome-late',
    renderTimeoutMs: 300000,
  };
  const withBin = savePageArgs({
    ...base,
    chromeBin: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  });
  const idx = withBin.indexOf('--executable-path');
  ok(idx >= 0 && withBin[idx + 1].includes('msedge.exe'), '浏览器路径透传到 save_page 的 --executable-path');

  const withBrand = savePageArgs({ ...base, browserBrand: 'edge' });
  const brandIdx = withBrand.indexOf('--browser-brand');
  ok(brandIdx >= 0 && withBrand[brandIdx + 1] === 'edge', '浏览器品牌透传到 save_page 的 --browser-brand');

  const withoutBin = savePageArgs(base);
  ok(!withoutBin.includes('--executable-path'), '未指定浏览器时不传 --executable-path');
  ok(!withoutBin.includes('--browser-brand'), '未指定品牌时不传 --browser-brand');
  ok(withoutBin.includes('--discover-proxy'), '未指定代理时让渲染脚本自己发现代理');
  ok(!withoutBin.includes('--headful'), '未开窗时不带 --headful');
  ok(withBin[withBin.indexOf('--render-timeout-ms') + 1] === '60000', '渲染预算上限压到 60s');

  const guarded = savePageArgs({ ...base, expectTexts: ['甲清单', '乙清单'], waitSelector: '#nodeSelector option', postWaitMs: 1500 });
  const textAt = guarded.indexOf('--expect-text');
  ok(textAt >= 0 && guarded[textAt + 1] === '甲清单' && guarded.filter((a) => a === '--expect-text').length === 2, '目标断言逐条透传 --expect-text');
  ok(guarded[guarded.indexOf('--wait-selector') + 1] === '#nodeSelector option', '选择器等待透传 --wait-selector');
  ok(guarded[guarded.indexOf('--post-wait-ms') + 1] === '1500', '额外等待透传 --post-wait-ms');
  ok(guarded[guarded.indexOf('--timeout-ms') + 1] === '60000', '等选择器时页面超时压到渲染预算');
  ok(withoutBin[withoutBin.indexOf('--timeout-ms') + 1] === '300000', '不等选择器时保留原页面超时');
  ok(!savePageArgs(base).includes('--expect-text'), '未给断言时不带 --expect-text');
}

// ---- 17. --keep-options / --keep-details：控件值与被压平的折叠块 ----
{
  const FORM = `<html><head><title>表单</title></head><body>
    <p>正文</p>
    <label for="city">城市</label>
    <select id="city">
      <option value="">请选择</option>
      <optgroup label="华北"><option value="bj">北京</option></optgroup>
      <optgroup label="华东"><option value="sh">上海</option></optgroup>
    </select>
    <fieldset><legend>套餐</legend>
      <label><input type="radio" name="plan" value="1">基础版</label>
      <label><input type="radio" name="plan" value="2" checked>专业版</label>
    </fieldset>
    <datalist id="browsers"><option value="Chrome"></option></datalist>
    <select aria-label="镜像"><option value="https://gh-proxy.com">gh-proxy.com</option></select>
    <select aria-label="图片选项"><option value="red"><img src="red.png" alt=""></option></select>
  </body></html>`;
  const section = formOptionsSection(FORM);
  ok(section.startsWith('## 表单选项\n\n- 城市（3 项）'), '选项清单以组名 + 条数起头');
  ok(section.includes('  - 华北\n    - 北京'), 'optgroup 缩进一层，列表只写显示文本');
  ok(!section.includes('（bj）') && !section.includes('（sh）'), '列表默认不输出 value');
  ok(section.includes('  - 请选择\n'), '空 value 的选项照常列文本');
  ok(section.includes('- 套餐（2 项）\n  - 基础版\n  - 专业版 [已选]'), '单选组取 fieldset legend 并标注已选');
  ok(section.includes('- #browsers（1 项）\n  - Chrome'), 'datalist 候选也算可选项');
  ok(section.includes('- 图片选项（1 项）\n  - red'), '选项没有文本时退回 value（图片选项）');
  ok(section.indexOf('- 城市') < section.indexOf('- 套餐'), '按文档顺序输出，不按控件类型分组');
  ok(formOptionsSection('<html><body><p>没有表单</p></body></html>') === '', '没有可选项时不追加空章节');

  const asHtml = formOptionsSection(FORM, { format: 'html' });
  ok(asHtml.includes('<select aria-label="镜像">\n<option>gh-proxy.com</option>\n</select>'), 'html 形式把下拉框写成 <select>，默认不带 value');
  ok(asHtml.includes('<optgroup label="华北">\n  <option>北京</option>\n</optgroup>'), 'html 形式保留 optgroup 分组');
  ok(asHtml.includes('- 套餐（2 项）') && !asHtml.includes('<input'), 'html 形式只改下拉框，单选仍按列表');

  // value 与格式正交：--keep-values 在列表里补 "文本（value）"，html 形式补 value 属性。
  const withValues = formOptionsSection(FORM, { values: true });
  ok(withValues.includes('    - 北京（bj）') && withValues.includes('  - 基础版（1）'), '--keep-values 在列表里补 value（option 与单选都算）');
  ok(!withValues.includes('  - 请选择（'), '空 value 不补空括号');
  const htmlValues = formOptionsSection(FORM, { format: 'html', values: true });
  ok(htmlValues.includes('<option value="bj">北京</option>') && htmlValues.includes('<option value="https://gh-proxy.com">gh-proxy.com</option>'), 'html 形式加 values 才带 value 属性');

  // details：抽取器把它压平成"摘要 + 正文"，--keep-details 按文本比对包回原位。
  const DETAILS = `<html><head><title>折叠</title></head><body>
    <p>开头。</p>
    <details><summary>问题一</summary><p>答案一。</p></details>
    <details open><summary>问题二</summary><ul><li>要点甲</li><li>要点乙</li></ul></details>
    <p>结尾。</p></body></html>`;
  const flat = '开头。\n\n问题一\n\n答案一。\n\n问题二\n- 要点甲\n- 要点乙\n\n结尾。';
  const wrapped = wrapDetails(flat, DETAILS);
  ok(wrapped.wrapped === 2 && wrapped.skipped === 0, '定位成功时两个 details 都被包回');
  ok(wrapped.markdown.includes('<details>\n<summary>问题一</summary>\n\n答案一。\n\n</details>'), '包回原位，摘要进 <summary>，内容留在块内');
  ok(wrapped.markdown.includes('<details open>\n<summary>问题二</summary>'), 'open 状态保留');
  ok(wrapped.markdown.indexOf('<details>') < wrapped.markdown.indexOf('结尾。'), '块位置不变，不挪到末尾');
  const lost = wrapDetails('开头。\n\n结尾。', DETAILS);
  ok(lost.wrapped === 0 && lost.skipped === 2 && lost.markdown === '开头。\n\n结尾。', '正文里定位不到时保持纯文本，不乱包');

  const dir = await mkdtemp(path.join(os.tmpdir(), 'htmlmini-opts-'));
  try {
    const file = path.join(dir, 'form.html');
    await writeFile(file, FORM);
    // 强制 semantic：auto 遇到表单页会回退 ui 清单，自己就把选项列了一部分，看不出追加效果。
    const plain = await cli([file, '-m', '--extractor', 'semantic']);
    ok(!plain.stdout.includes('表单选项') && !plain.stdout.includes('gh-proxy.com'), '默认不追加选项清单');
    const kept = await cli([file, '-m', '--extractor', 'semantic', '--keep-options']);
    ok(kept.code === 0 && kept.stdout.includes('## 表单选项') && kept.stdout.includes('  - 北京'), '--keep-options 追加选项清单');
    ok(/--keep-options 追加 \d+ 条/.test(kept.stderr), '追加时日志写明条数');
    const keptHtml = await cli([file, '-m', '--extractor', 'semantic', '--keep-options=html']);
    ok(keptHtml.code === 0 && keptHtml.stdout.includes('<select aria-label="镜像">'), '--keep-options=html 输出真正的 <select>');
    ok(!keptHtml.stdout.includes('value='), 'html 形式默认不带 value');
    const keptHtmlValues = await cli([file, '-m', '--extractor', 'semantic', '--keep-options=html', '--keep-values']);
    ok(keptHtmlValues.stdout.includes('<option value="https://gh-proxy.com">gh-proxy.com</option>'), 'html + --keep-values 才带 value 属性');
    const keptValues = await cli([file, '-m', '--extractor', 'semantic', '--keep-options', '--keep-values']);
    ok(keptValues.code === 0 && keptValues.stdout.includes('  - 北京（bj）'), '--keep-values 让列表带上 value');
    const valuesAlone = await cli([file, '-m', '--keep-values']);
    ok(valuesAlone.stderr.includes('只配合 --keep-options'), '单独用 --keep-values 时说明它不生效');
    const bad = await cli([file, '--keep-options=xml']);
    ok(bad.code === 2 && bad.stderr.includes('list 或 html'), '非法取值退出 2');
    const htmlMode = await cli([file, '--mode', 'html', '--keep-options']);
    ok(htmlMode.code === 0 && !htmlMode.stdout.includes('表单选项') && htmlMode.stderr.includes('只作用于'), 'html 模式不追加，并说明原因');
    const asJson = await cli([file, '--json', '--keep-options']);
    ok(asJson.code === 0 && JSON.parse(asJson.stdout).content.includes('正文'), '--json 不受影响，仍是合法 JSON');

    const detailsFile = path.join(dir, 'details.html');
    await writeFile(detailsFile, DETAILS);
    // 用 defuddle：它把 details 压平成"摘要 + 正文"，正是这个开关要修的状态。
    const details = await cli([detailsFile, '-m', '--extractor', 'defuddle', '--keep-details']);
    ok(details.code === 0 && /--keep-details 原位保留 2 个/.test(details.stderr), '--keep-details 在 CLI 上生效并记账');
    ok(details.stdout.includes('<details open>\n<summary>问题二</summary>'), 'CLI 输出里 details 是 HTML 块');
    const detailsText = await cli([detailsFile, '-t', '--keep-details']);
    ok(detailsText.code === 0 && detailsText.stderr.includes('只作用于 markdown'), 'text 模式忽略并说明原因');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

await new Promise((resolve) => server.close(resolve));
console.log(`\nPASS ${n} assertions`);
