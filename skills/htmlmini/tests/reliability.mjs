// 可靠性回归：node tests/reliability.mjs（已接入 pnpm test）。
// 全内置合成输入 + 本地回环 HTTP/临时文件，无外部网络依赖。
import { strict as assert } from 'node:assert';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync, readdirSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  challengeSignals,
  decodeHtml,
  extractHtml,
  findPython,
  hostBypassed,
  maskProxy,
  pickPlaywrightChrome,
  readSiblingMeta,
  readSource,
  renderResult,
  renderViaBrowser,
  resolveProxy,
  runExtract,
  skeletonFromMarkdown,
  tryTrafilatura,
} from '../src/extract.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const CLI = path.join(ROOT, 'src', 'cli.js');

let n = 0;
const ok = (cond, msg) => {
  n++;
  assert.ok(cond, msg);
  console.log(`ok ${n} - ${msg}`);
};

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
async function cli(args, { input } = {}) {
  const { spawn } = await import('node:child_process');
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [CLI, ...args], { windowsHide: true });
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
  const u = await cli(['--nope']);
  ok(u.code === 2 && u.stderr.includes('unknown option'), '未知选项退出 2');
  const m = await cli(['--mode', 'nope']);
  ok(m.code === 2 && m.stderr.includes('unknown mode'), '非法 mode 退出 2');
  const f = await cli([path.join(os.tmpdir(), 'htmlmini-不存在.html')]);
  ok(f.code === 1 && f.stderr.includes('htmlmini:'), '缺失文件退出 1 且有提示');
  const s = await cli(['-', '--title'], {
    input: '<html><head><title>管道标题</title></head><body><p>x</p></body></html>',
  });
  ok(s.code === 0 && s.stdout.trim() === '管道标题', 'stdin 管道正常');

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
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- 6. trafilatura：缺席给安装提示（本机无模块，确定性覆盖） ----
{
  const probe = await tryTrafilatura('<p>hello</p>');
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
  ok(resolveProxy(t, { proxy: 'http://127.0.0.1:7897', env: {} }) === 'http://127.0.0.1:7897', '显式代理覆盖环境');
  ok(resolveProxy(t, { proxy: 'direct', env: { HTTP_PROXY: 'http://127.0.0.1:7897' } }) === null, '"direct" 忽略环境强制直连');
  let bad = null;
  try {
    resolveProxy(t, { proxy: 'socks://x', env: {} });
  } catch (e) {
    bad = e;
  }
  ok(bad && /proxy 须是/.test(bad.message), '非法代理协议给出提示');
  ok(resolveProxy(s, { env: { HTTPS_PROXY: 'http://127.0.0.1:7897' } }) === 'http://127.0.0.1:7897', 'https 走 HTTPS_PROXY');
  ok(resolveProxy(t, { env: { HTTP_PROXY: 'http://127.0.0.1:7897' } }) === 'http://127.0.0.1:7897', 'http 走 HTTP_PROXY');
  ok(resolveProxy(t, { env: {} }) === null, '无环境变量直连');
  ok(resolveProxy(s, { env: { ALL_PROXY: 'http://127.0.0.1:7897' } }) === 'http://127.0.0.1:7897', 'ALL_PROXY 兜底');
  ok(
    resolveProxy('http://127.0.0.1:9/a', { env: { HTTP_PROXY: 'http://127.0.0.1:7897', NO_PROXY: '127.0.0.1' } }) === null,
    'NO_PROXY 精确主机豁免',
  );
  ok(
    resolveProxy('http://sub.example.com/a', { env: { HTTP_PROXY: 'http://127.0.0.1:7897', NO_PROXY: 'example.com' } }) === null,
    'NO_PROXY 后缀匹配子域',
  );
  ok(
    resolveProxy(t, { env: { HTTP_PROXY: 'http://127.0.0.1:7897', NO_PROXY: '*' } }) === null,
    'NO_PROXY 星号全豁免',
  );
  ok(hostBypassed('Example.COM', 'example.com') === true, 'NO_PROXY 大小写不敏感');
  ok(maskProxy('http://user:pass@127.0.0.1:7897/') === 'http://127.0.0.1:7897', '代理脱敏不泄凭据');
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
// 说明：不用自造转发代理做集成测试——本机实测其会触发异常连接风暴；
// 生产代码已用真实代理（127.0.0.1:7897）验证：example.com 经代理 200 取回正常，
// britvanlife 经代理自动走浏览器头重试并点名挑战。测试内用黑洞代理（秒拒）与
// 直连成功/失败的可观测差异覆盖选路逻辑，不依赖外部网络。
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
    ok(cn.code === 0 && cn.stdout.trim() === '本地页', 'CLI --noproxy 越过失效环境代理');
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
        ok(cr.code === 0 && cr.stdout.trim() === '渲染页', 'CLI --render 回退成功');
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
      ok(cexp.code === 0 && cexp.stdout.trim() === 'Chrome页', 'CLI --chrome-bin 显式指定生效');
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
    const winFull1200 = await touch('win', 'chromium-1200', 'chrome-win', 'chrome.exe');
    const winFull1210 = await touch('win', 'chromium-1210', 'chrome-win', 'chrome.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win'), 'win32') === winFull1210, 'win 取版本最大者');
    ok(pickPlaywrightChrome(path.join(dir, 'empty'), 'win32') === null, '空缓存返回 null');
    const winShell = await touch('win-shell', 'chromium-1200', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
    ok(pickPlaywrightChrome(path.join(dir, 'win-shell'), 'win32') === winShell, 'win 无完整版时用无头壳兜底');

    const linFull = await touch('lin', 'chromium-1180', 'chrome-linux', 'chrome');
    ok(pickPlaywrightChrome(path.join(dir, 'lin'), 'linux') === linFull, 'linux 布局命中');
    const macFull = await touch('mac', 'chromium-1190', 'chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium');
    ok(pickPlaywrightChrome(path.join(dir, 'mac'), 'darwin') === macFull, 'mac 布局命中');
    ok(pickPlaywrightChrome(path.join(dir, 'lin'), 'win32') === null, '平台布局错配不命中');
    void winFull1200;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

await new Promise((resolve) => server.close(resolve));
console.log(`\nPASS ${n} assertions`);
