// 可靠性回归：node tests/reliability.mjs（已接入 pnpm test）。
// 全内置合成输入 + 本地回环 HTTP/临时文件，无外部网络依赖。
import { strict as assert } from 'node:assert';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  decodeHtml,
  extractHtml,
  readSiblingMeta,
  readSource,
  renderResult,
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

await new Promise((resolve) => server.close(resolve));
console.log(`\nPASS ${n} assertions`);
