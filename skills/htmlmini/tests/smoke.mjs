// 自检：node tests/smoke.mjs（需先 npm install）。无外部 fixture，全内置合成 HTML。
import { strict as assert } from 'node:assert';
import { extractHtml, runExtract } from '../src/extract.js';

const ARTICLE = `<!doctype html><html><head><title>测试文章</title>
<style>.x{color:red}</style><script>var a=1;</script></head>
<body><nav>导航</nav><article><h1>主标题</h1>
<p>这是正文第一段，内容足够长，可以被 Defuddle 识别为文章主体。</p>
<p>这是正文第二段，继续补充一些文字，保证总长度超过回退阈值。</p>
</article><footer>页脚</footer></body></html>`;

const DASHBOARD = `<!doctype html><html><head><title>报表面板</title></head>
<body><header><h1>销售日报</h1></header>
<form><label for="city">城市</label>
<select id="city"><option>北京</option><option>上海</option></select>
<label>日期<input type="date" name="day" required></label>
<button type="submit" aria-label="查询数据">查询</button>
<span class="btn">样式按钮（不应进按钮清单）</span>
</form>
<table><caption>明细</caption><tr><th>城市</th><th>金额</th></tr>
<tr><td>北京</td><td>100</td></tr></table>
</body></html>`;

let n = 0;
const ok = (cond, msg) => {
  n++;
  assert.ok(cond, msg);
  console.log(`ok ${n} - ${msg}`);
};

// 1. 文章页：Defuddle 命中，去掉 CSS/JS，保留正文。
{
  const r = await extractHtml(ARTICLE, { url: 'file:///test.html' });
  ok(r.used === 'defuddle', `文章页 used=defuddle（实得 ${r.used}）`);
  ok(r.content.includes('正文第一段'), '正文保留');
  ok(!r.content.includes('var a=1') && !r.content.includes('color:red'), 'CSS/JS 已剥离');
  ok(r.stats.reductionPct > 0, `reductionPct=${r.stats.reductionPct}`);
}

// 2. 面板页：自动切 UI 清单。
{
  const r = await extractHtml(DASHBOARD, { url: 'file:///dash.html' });
  ok(r.used === 'ui', `面板页自动切 ui（实得 ${r.used}）`);
  ok(r.content.includes('## 按钮') && r.content.includes('查询'), '按钮清单含查询');
  ok(r.content.includes('## 表格') && r.content.includes('城市'), '表格清单含表头');
  const btnSection = r.content.split('## 按钮')[1].split('## ')[0];
  ok(!btnSection.includes('样式按钮'), 'class="btn" 的 span 不进按钮清单');
  ok(r.content.includes('城市') && r.content.includes('北京'), '表单字段/下拉选项保留');
}

// 3. 强制 extractor：semantic / ui 按指定返回。
{
  const s = await extractHtml(ARTICLE, { extractor: 'semantic' });
  ok(s.used === 'semantic', '强制 semantic 返回 semantic');
  const u = await extractHtml(ARTICLE, { extractor: 'ui' });
  ok(u.used === 'ui' && u.content.includes('## 标题'), '强制 ui 返回清单');
}

// 4. 未知 extractor 抛错（中英文提示）。
{
  let err = null;
  try {
    await extractHtml(ARTICLE, { extractor: 'nope' });
  } catch (e) {
    err = e;
  }
  ok(err && /unknown extractor/.test(err.message), '未知 extractor 抛错');
}

// 5. 输出模式：json / title / text / skeleton。
{
  const j = JSON.parse(await runExtract(null, 'json', { forceContent: ARTICLE }));
  ok(j.used === 'defuddle' && typeof j.stats.reductionPct === 'number', 'json 含 used 与 reductionPct');
  const t = await runExtract(null, 'title', { forceContent: ARTICLE });
  ok(t.trim() === '测试文章', `title 模式（实得 ${t.trim()}）`);
  const txt = await runExtract(null, 'text', { forceContent: ARTICLE });
  ok(!/[*_`~]/.test(txt), 'text 模式无 markdown 符号');
  const sk = await runExtract(null, 'skeleton', { forceContent: ARTICLE });
  ok(sk.includes('SKELETON'), 'skeleton 模式含大纲头');
}

// 6. 无 trafilatura 环境下 auto 不崩（本机未安装即覆盖此分支）。
{
  const r = await extractHtml(ARTICLE);
  ok(['defuddle', 'trafilatura', 'semantic', 'ui'].includes(r.used), `auto 收敛到已知引擎（实得 ${r.used}）`);
}

console.log(`\nPASS ${n} assertions`);
