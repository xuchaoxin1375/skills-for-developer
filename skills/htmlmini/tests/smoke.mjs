// 自检：node tests/smoke.mjs（需先 pnpm install）。无外部 fixture，全内置合成 HTML。
import { strict as assert } from 'node:assert';
import { extractHtml, runExtract } from '../src/extract.js';
import { setLogLevel } from '../src/log.js';

// 测试只关心返回值；进度日志默认会打到 stderr，这里按静默跑，保持测试输出干净。
setLogLevel('quiet');

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

// 3b. ui / semantic 不把 script/style 源码当正文（叶子 div 包裹脚本时曾泄漏）。
{
  const NON_CONTENT = `<!doctype html><html><head><title>脚本泄漏</title></head><body>
<div id="wrap"><script>var SECRET_JS = "leak-marker";</script></div>
<div><style>.x{color:red}</style></div>
<p>正常段落</p>
</body></html>`;
  const u = await extractHtml(NON_CONTENT, { extractor: 'ui', textMax: 0 });
  ok(!u.content.includes('SECRET_JS') && !u.content.includes('color:red'), 'ui 不含 script/style 源码');
  ok(u.content.includes('正常段落'), 'ui 仍保留正常段落');
  const s = await extractHtml(NON_CONTENT, { extractor: 'semantic' });
  ok(!s.content.includes('SECRET_JS') && !s.content.includes('color:red'), 'semantic 不含 script/style 源码');
  const auto = await extractHtml(NON_CONTENT);
  ok(!auto.content.includes('SECRET_JS') && !auto.content.includes('color:red'), `auto 回退到 ${auto.used} 时也不漏`);
}

// 3c. CSS ::before/::after 的短标点并入文本（价格把小数点做成 content:"." 时不丢）。
{
  const SPLIT_PRICE = `<!doctype html><html><head><title>价格</title>
<style>.price > .cents::before, .price > .cents.alt::before{content:"."} .icon::before{content:"\\e900"}</style></head>
<body><article><h1>面包</h1><p>正文段落足够长，用于通过语义回退的阈值检查。</p>
<span class="price"><span class="currency">$</span><span class="units">1</span><span class="cents">00</span> each</span>
<span class="icon"></span></article></body></html>`;
  const r = await extractHtml(SPLIT_PRICE, { extractor: 'semantic' });
  ok(r.content.includes('$1.00'), `CSS 生成的小数点并入文本（实得含 $1.00=${r.content.includes('$1.00')}）`);
  ok(r.stats.cssGenerated === 1, `stats.cssGenerated 记账（实得 ${r.stats.cssGenerated}）`);
  ok(!/[\ue000-\uf8ff]/.test(r.content), '图标字体的私有区字符不并入');
  const u = await extractHtml(SPLIT_PRICE, { extractor: 'ui' });
  ok(u.content.includes('$1.00'), 'ui 清单同样并入 CSS 生成的小数点');
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

// 4b. 客户端渲染壳：正文与 HTML 体积严重不成比例时默认报错，并指向 --render=always。
{
  const SHELL = `<!doctype html><html><head><title>壳页面</title></head><body data-filler="${'x'.repeat(6000)}"><div id="app"></div><p>Loading…</p></body></html>`;
  let err = null;
  try {
    await runExtract(null, 'markdown', { forceContent: SHELL });
  } catch (e) {
    err = e;
  }
  ok(err && /--render=always/.test(err.message), `应用壳默认报错并指向 --render=always（实得 ${err && err.message.slice(0, 60)}…）`);
  const allowed = await runExtract(null, 'markdown', { forceContent: SHELL, allowEmpty: true });
  ok(allowed.includes('Loading'), '--allow-empty 保留原输出');
  const t = await runExtract(null, 'title', { forceContent: SHELL });
  ok(t.trim() === '壳页面', 'title 模式不受壳检测影响');
  const sk = await runExtract(null, 'skeleton', { forceContent: SHELL });
  ok(typeof sk === 'string', 'skeleton 模式不受壳检测影响');
}

// 5. 输出模式：json / title / text / skeleton。
{
  const j = JSON.parse(await runExtract(null, 'json', { forceContent: ARTICLE }));
  ok(j.used === 'defuddle' && typeof j.stats.reductionPct === 'number', 'json 含 used 与 reductionPct');
  ok(/^\d{4}\.\d{2}\.\d{2}\.\d{4}$/.test(j.version), `json 含日期时间版本号（实得 ${j.version}）`);
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
  ok(['defuddle', 'trafilatura', 'semantic', 'ui', 'passthrough'].includes(r.used), `auto 收敛到已知引擎（实得 ${r.used}）`);
}

// 7. html 模式：保守清洗（结构保留，剥脚本/样式与表观属性）。
{
  const h = await runExtract(null, 'html', { forceContent: ARTICLE });
  ok(!h.includes('var a=1') && !h.includes('color:red'), 'html 模式剥掉脚本与样式');
  ok(h.includes('<h1>主标题</h1>') && h.includes('<article>'), 'html 模式保留 DOM 结构与文本顺序');

  const sem = await runExtract(null, 'html', { forceContent: DASHBOARD });
  ok(sem.includes('<table>') && sem.includes('<th>城市</th>'), 'html 模式保留 table/th');
  ok(sem.includes('for="city"') && sem.includes('type="date"') && sem.includes('name="day"'), 'semantic 档保留语义属性');
  const semAttrs = sem.match(/\s[a-zA-Z-]+="/g) || [];
  ok(!sem.includes('class=') && !sem.includes('aria-label=') && !sem.includes('id='), 'semantic 档剥掉 class/id/aria-*');
  ok(semAttrs.length > 0, 'semantic 档并非清空全部属性');

  const none = await runExtract(null, 'html', { forceContent: DASHBOARD, attrs: 'none' });
  ok(!/\s[a-zA-Z-]+="/.test(none), 'attrs=none 清空全部属性');
  ok(none.includes('<table>'), 'attrs=none 仍保留标签结构');

  const all = await runExtract(null, 'html', { forceContent: DASHBOARD, attrs: 'all' });
  ok(all.includes('class="btn"') && all.includes('aria-label="查询数据"'), 'attrs=all 保留全部属性');
  ok(!all.includes('<script') && !all.includes('<style'), 'attrs=all 仍剥脚本与样式');

  // 排版：默认 compact 压掉源码缩进噪声又不破坏行内词距；raw 保原样；pretty 重排缩进。
  const SPACED = `<!doctype html><html><head><title>空格</title></head><body>
  <div></div>
  <p>Run <b>3</b> tests</p>
  <table><tr><td></td><td>A</td></tr></table>
  <pre>  keep   me
</pre>
</body></html>`;
  const compact = await runExtract(null, 'html', { forceContent: SPACED });
  ok(compact.includes('<p>Run <b>3</b> tests</p>'), 'compact 保留行内元素之间的单个空格');
  ok(!/>\s+</.test(compact), 'compact 压掉块级之间的源码缩进与空行');
  ok(compact.includes('<pre>  keep   me\n</pre>'), 'compact 不动 pre 的内容空白');
  const rawOut = await runExtract(null, 'html', { forceContent: SPACED, format: 'raw' });
  ok(/\n\s+<div><\/div>/.test(rawOut), 'raw 保留源码原有空白');
  const pretty = await runExtract(null, 'html', { forceContent: SPACED, format: 'pretty' });
  ok(/\n\s+<p>Run/.test(pretty), 'pretty 重新缩进');
  ok(!pretty.includes('\n\n'), 'pretty 不留空行');
  const pruned = await runExtract(null, 'html', { forceContent: SPACED, pruneEmpty: true });
  ok(!pruned.includes('<div></div>'), 'pruneEmpty 剪掉空 div');
  ok(pruned.includes('<td></td>'), 'pruneEmpty 保留空单元格（表格结构）');
  const bare = (s) => s.replace(/<[^>]+>/g, '').replace(/\s+/g, '');
  ok(bare(compact) === bare(pretty) && bare(compact) === bare(pruned), 'compact/pretty/prune 文本内容等价');

  // 文档级空白：doctype 之前与 </html> 之后不在 <html> 子树内，真源 HTML 常带这类换行，
  // 漏掉就会在输出首尾留下空行（cdn 页面首尾各留若干空行）。
  const DOCWS = `\n\n<!doctype html><html><head><title>文档级空白</title></head><body><p>hi</p></body></html>\n\n\n`;
  const docCompact = await runExtract(null, 'html', { forceContent: DOCWS });
  ok(/^<!doctype html>/i.test(docCompact), 'compact 去掉 doctype 之前的文档级空白');
  ok(/<\/html>$/i.test(docCompact), 'compact 去掉 </html> 之后的文档级空白');
  const docPruned = await runExtract(null, 'html', { forceContent: DOCWS, pruneEmpty: true });
  ok(/^<!doctype html>/i.test(docPruned) && /<\/html>$/i.test(docPruned), 'pruneEmpty 同样不带文档级空白');
  const docRaw = await runExtract(null, 'html', { forceContent: DOCWS, format: 'raw' });
  // 序列化把 doctype 提到最前，源码里 doctype 之前的空白落到其后；raw 应原样带出这些空白。
  ok(/^<!doctype html>\n\n<html>/i.test(docRaw) && docRaw.endsWith('</html>\n\n\n'), 'raw 仍原样保留文档级空白');

  const pt = await runExtract(null, 'html', { forceContent: '# 标题\n正文' });
  ok(pt.includes('# 标题'), 'html 模式对非 HTML 输入透传');

  let e2 = null;
  try {
    await extractHtml(ARTICLE, { extractor: 'sanitize', attrs: 'nope' });
  } catch (err) {
    e2 = err;
  }
  ok(e2 && /unknown attrs policy/.test(e2.message), '未知 attrs 策略抛错');

  let e3 = null;
  try {
    await extractHtml(ARTICLE, { extractor: 'sanitize', format: 'nope' });
  } catch (err) {
    e3 = err;
  }
  ok(e3 && /unknown format/.test(e3.message), '未知 format 策略抛错');
}

// 8. ui 清单的单条文本上限：默认丢弃超长段落，但要记账而不是静默消失；
//    textMax=0 取消上限（长正文页只跑 ui 时用）。
{
  const LONG = `<!doctype html><html><head><title>长文本页</title></head><body>
  <h1>长文本页</h1>
  <p>短文本条目。</p>
  <p>${'长段落内容。'.repeat(40)}</p>
  </body></html>`;

  const capped = await runExtract(null, 'ui', { forceContent: LONG });
  ok(capped.includes('短文本条目'), 'ui 保留短文本条目');
  ok(!capped.includes('长段落内容'), 'ui 默认丢弃超长段落');
  ok(/已省略 1 条超过 150 字符/.test(capped), `ui 记账被丢弃的长文本（实得片段 ${capped.split('\n').pop()}）`);

  const uncapped = await runExtract(null, 'ui', { forceContent: LONG, textMax: 0 });
  ok(uncapped.includes('长段落内容'), 'textMax=0 时保留超长段落');
  ok(!/已省略/.test(uncapped), 'textMax=0 时不再提示省略');

  const wider = await runExtract(null, 'ui', { forceContent: LONG, textMax: 400 });
  ok(wider.includes('长段落内容'), 'textMax=400 时保留中等长度段落');
}

console.log(`\nPASS ${n} assertions`);
