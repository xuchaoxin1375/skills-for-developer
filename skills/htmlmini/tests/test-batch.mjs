// 手工批量验证：node tests/test-batch.mjs <html目录>
// 逐文件输出 引擎 | 输入->输出 | 节省% | 耗时。fixture 不入库，本地有多少测多少。
import { readdir } from 'node:fs/promises';
import { extractHtml, readSource } from '../src/extract.js';

const dir = (process.argv[2] ?? '..').replace(/[\\/]+$/, '');

const names = (await readdir(dir)).filter((n) => /\.html?$/i.test(n) && !n.includes('node_modules'));
if (!names.length) {
  console.error(`no html files in ${dir}`);
  process.exit(1);
}
console.log('file | extractor | inputChars -> outputChars | saved% | parseMs');
for (const name of names) {
  try {
    const { html } = await readSource(`${dir}/${name}`);
    const r = await extractHtml(html, { url: `file:///${dir}/${name}`.replaceAll('\\', '/') });
    console.log(`${name} | ${r.used} | ${r.stats.inputChars} -> ${r.stats.outputChars} | ${r.stats.reductionPct}% | ${r.stats.parseMs}ms`);
  } catch (e) {
    console.log(`${name} | ERROR: ${e.message}`);
  }
}
