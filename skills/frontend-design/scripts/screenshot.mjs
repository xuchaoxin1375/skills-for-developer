#!/usr/bin/env node
// scripts/screenshot.mjs —— 三断点自动截图审核
//
// 用法:
//   npx playwright install chromium   # 一次性安装浏览器
//   node scripts/screenshot.mjs http://127.0.0.1:8787 [--out shots]
//
// 产出: shots/390.png shots/768.png shots/1440.png（整页截图）
// 看法: 无横向滚动、导航可达、表格有降级、文字无截断重叠（见 assets/design-review-checklist.md）

import fs from 'node:fs';
import path from 'node:path';

const url = process.argv[2];
let out = 'shots';
for (let i = 3; i < process.argv.length; i++) {
  if (process.argv[i] === '--out' && process.argv[i + 1]) out = process.argv[++i];
}
if (!url) {
  console.error('用法: node scripts/screenshot.mjs <URL> [--out shots]');
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.error('缺 playwright：先跑 npm i -D playwright && npx playwright install chromium');
  process.exit(1);
}

const viewports = [
  { name: '390', width: 390, height: 844 },
  { name: '768', width: 768, height: 1024 },
  { name: '1440', width: 1440, height: 900 },
];

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
try {
  for (const v of viewports) {
    const page = await browser.newPage({ viewport: { width: v.width, height: v.height } });
    // 减少动态干扰：截图时停掉动画，便于比对
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const file = path.join(out, `${v.name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    // 页面级横向滚动即 bug（表格区内部横滑除外），顺手检测并报告
    const overflow = await page.evaluate(() => ({
      page: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    console.log(`${file}  done${overflow.page ? '  [警告] 页面级横向溢出' : ''}`);
    await page.close();
  }
} finally {
  await browser.close();
}
console.log('截图完成：人工看一遍三张图再交付。');
