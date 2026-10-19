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
  pythonBinOverride,
  resetEnvScanCache,
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
  savePageUsable,
  skeletonFromMarkdown,
  tryTrafilatura,
} from '../src/extract.js';
import { setLogLevel } from '../src/log.js';

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

await new Promise((resolve) => server.close(resolve));
console.log(`\nPASS ${n} assertions`);
