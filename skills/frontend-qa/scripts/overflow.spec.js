// tests/overflow.spec.js —— 多宽度断言无横向溢出（对应 catalog 验收动作一）。
// 初期可只取 [320, 768, 1180, 1440] 四档；另建议加一组 height:400 矮视口查 L-10。
import { test, expect } from '@playwright/test';

const WIDTHS = [320, 360, 390, 480, 600, 768, 834, 1024, 1180, 1280, 1440, 1920];
const PAGES = ['/', '/products', '/checkout', '/dashboard']; // 改为本项目关键页：覆盖表/长表单/仪表盘

for (const path of PAGES) {
  for (const width of WIDTHS) {
    test(`${path} @ ${width}px 无横向溢出`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path, { waitUntil: 'networkidle' }); // 长轮询页改显式等待选择器
      const hasHScroll = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      expect(hasHScroll, '页面出现横向滚动条').toBe(false);
      const offenders = await page.evaluate(() => {
        const w = document.documentElement.clientWidth;
        return [...document.querySelectorAll('*')]
          .filter((el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && (r.right > w + 1 || r.left < -1);
          })
          .slice(0, 10)
          .map((el) => `${el.tagName.toLowerCase()}.${el.className?.toString().slice(0, 30)}`);
      });
      expect(offenders, `溢出元素:${offenders.join(', ')}`).toHaveLength(0);
    });
  }
}
