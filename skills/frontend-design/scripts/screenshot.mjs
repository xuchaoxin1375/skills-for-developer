#!/usr/bin/env node
// scripts/screenshot.mjs —— 基础宽度截图助手（验收范围见响应式专项 acceptance.md）
// 项目模板：放在已有总期限与进程回收的 runner 中运行；本文件自身不提供进程级托管。
// 独立首屏/滚动视口采集复用 ../../frontend-qa/references/screenshot-workflow.md。
//
// 用法:
//   先确认项目可导入 playwright；缺包时沿用项目包管理器安装，不用 dlx 临时版本代替。
//   pnpm exec playwright install chromium   # 使用项目版本安装匹配浏览器
//   国内下载见 ../../network-access/references/browser-installation.md（包源与浏览器源分别配置）。
//   node scripts/screenshot.mjs <URL> [--out shots] [--widths 320,390,768,1440]
//
// 产出: shots/320.png shots/390.png shots/768.png shots/1440.png（整页截图）
// 看法: 无横向滚动、导航可达、表格有降级、文字无截断重叠（见 assets/design-review-checklist.md）

import fs from 'node:fs';
import path from 'node:path';

const url = process.argv[2];
let out = 'shots';
let widths = [320, 390, 768, 1440];
for (let i = 3; i < process.argv.length; i++) {
  if (process.argv[i] === '--out' && process.argv[i + 1]) out = process.argv[++i];
  else if (process.argv[i] === '--widths') {
    const value = process.argv[++i];
    if (!value || !/^\d+(,\d+)*$/.test(value) ||
        value.split(',').some(width => !Number.isSafeInteger(Number(width)) || Number(width) < 1)) {
      console.error('--widths 需要逗号分隔的正整数CSS像素宽度');
      process.exit(2);
    }
    widths = [...new Set(value.split(',').map(Number))];
  }
}
if (!url) {
  console.error('用法: node scripts/screenshot.mjs <URL> [--out shots] [--widths 320,390,768,1440]');
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.error('缺 playwright：先跑 pnpm add -D playwright && pnpm exec playwright install chromium');
  process.exit(1);
}

const viewports = widths.map(width => ({
  name: String(width), width, height: width < 640 ? 844 : width < 1024 ? 1024 : 900,
})); // 高度仅为截图预设，不能当作页面设计断点。

fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
try {
  for (const v of viewports) {
    const page = await browser.newPage({ viewport: { width: v.width, height: v.height } });
    // 减少动态干扰：截图时停掉动画，便于比对
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(500);
    const geometry = await page.evaluate(() => ({
      width: innerWidth, height: innerHeight,
      page: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    if (geometry.width !== v.width || geometry.height !== v.height) {
      throw new Error(`实际视口 ${geometry.width}x${geometry.height} 与请求 ${v.width}x${v.height} 不符`);
    }
    const file = path.join(out, `${v.name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    console.log(`${file}  done  viewport=${geometry.width}x${geometry.height}${geometry.page ? '  [警告] 页面级横向溢出' : ''}`);
    await page.close();
  }
} finally {
  await browser.close();
}
console.log(`截图完成：查看${viewports.length}张图；容器、交互与正常动效按验收范围另验。`);
