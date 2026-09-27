// MCP 自检：node tests/test-mcp.mjs
// 断言 6 个工具（3 个正式名 + 3 个旧拼写别名）存在，且 html/别名调用可用。
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const child = spawn('node', [join(root, 'src', 'mcp.js')], { stdio: ['pipe', 'pipe', 'inherit'] });

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

const send = (msg) => child.stdin.write(`${JSON.stringify(msg)}\n`);
const rpc = (method, params) =>
  new Promise((resolve) => {
    const id = ++seq;
    pending.set(id, resolve);
    send({ jsonrpc: '2.0', id, method, params });
  });

const DASH = `<!doctype html><html><head><title>MCP面板</title></head><body>
<h1>状态</h1><button>刷新</button>
<table><tr><th>项</th></tr><tr><td>CPU</td></tr></table></body></html>`;

await rpc('initialize', {
  protocolVersion: '2024-11-05',
  capabilities: {},
  clientInfo: { name: 'test', version: '0.0.1' },
});
send({ jsonrpc: '2.0', method: 'notifications/initialized' });

const tools = await rpc('tools/list', {});
const names = tools.result.tools.map((t) => t.name);
console.log(`tools: ${names.join(', ')}`);
for (const want of ['htmlmini_extract_file', 'htmlmini_extract_url', 'htmlmini_extract_html']) {
  if (!names.includes(want)) throw new Error(`missing tool ${want}`);
  if (!names.includes(want.replace('htmlmini_', 'htmmini_'))) throw new Error(`missing alias ${want}`);
}
console.log('ok - 正式名 + 别名齐全');

const call = await rpc('tools/call', {
  name: 'htmlmini_extract_html',
  arguments: { html_content: DASH, mode: 'json' },
});
const parsed = JSON.parse(call.result.content[0].text);
console.log(`extract_html: used=${parsed.used} title=${parsed.title} saved=${parsed.stats.reductionPct}%`);
if (parsed.used !== 'ui') throw new Error(`expected ui, got ${parsed.used}`);

const alias = await rpc('tools/call', {
  name: 'htmmini_extract_html',
  arguments: { html_content: DASH, mode: 'markdown' },
});
if (!alias.result.content[0].text.includes('刷新')) throw new Error('alias call failed');
console.log('ok - 别名调用可用');

child.kill();
process.exit(0);
