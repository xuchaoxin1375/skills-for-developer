import { test, expect, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { EMPTY_RECORD, validateRecord } from '../src/lib/data';

async function expectNoPageOverflow(page: Page) {
  const measurements = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(measurements.scroll).toBeLessThanOrEqual(measurements.viewport);
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '交互设计实验室' })).toBeVisible();
});

test('default view and both themes have no page-level overflow', async ({ page }, testInfo) => {
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('light.png'), fullPage: true, animations: 'disabled' });
  await page.getByRole('button', { name: '切换外观主题' }).click();
  await page.getByRole('button', { name: '深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expectNoPageOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('dark.png'), fullPage: true, animations: 'disabled' });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('system theme changes without overriding an explicit choice', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: '切换外观主题' }).click();
  await page.getByRole('button', { name: '浅色模式' }).click();
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('search, filter and empty-state recovery', async ({ page }) => {
  const search = page.getByRole('textbox', { name: '搜索 DNS 记录' });
  await search.fill('blog');
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(1);
  await search.fill('not-a-real-record');
  await expect(page.getByRole('heading', { name: '没有找到匹配记录' })).toBeVisible();
  await page.getByRole('button', { name: '清除搜索与筛选' }).click();
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(6);
  await page.getByRole('button', { name: '筛选', exact: true }).click();
  await page.getByRole('button', { name: '应用筛选' }).click();
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(2);
  await page.getByRole('button', { name: '清除筛选', exact: true }).click();
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(6);
});

test('invalid submit focuses the first field; valid data persists', async ({ page }) => {
  await page.getByRole('button', { name: '添加记录', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '添加 DNS 记录' });
  await dialog.getByRole('button', { name: '保存记录' }).click();
  await expect(dialog.locator('input[name="name"]')).toBeFocused();
  await dialog.locator('input[name="name"]').fill('api');
  await dialog.locator('input[name="content"]').fill('999.2.3.4');
  await dialog.getByRole('button', { name: '保存记录' }).click();
  await expect(dialog.locator('input[name="content"]')).toHaveAttribute('aria-invalid', 'true');
  await dialog.locator('input[name="content"]').fill('192.0.2.8');
  await dialog.getByRole('button', { name: '保存记录' }).click();
  await expect(dialog).not.toBeVisible();
  await page.reload();
  await page.getByRole('textbox', { name: '搜索 DNS 记录' }).fill('api');
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(1);
  await expect(page.locator('.dns-table tbody')).toContainText('192.0.2.8');
  await page.getByRole('button', { name: '添加记录', exact: true }).click();
  await expect(page.getByRole('dialog').locator('input[name="name"]')).toHaveValue('');
});

test('new-record draft survives cancellation', async ({ page }) => {
  await page.getByRole('button', { name: '添加记录', exact: true }).click();
  await page.getByRole('dialog').locator('input[name="name"]').fill('draft-record');
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click();
  await page.getByRole('button', { name: '添加记录', exact: true }).click();
  await expect(page.getByRole('dialog').locator('input[name="name"]')).toHaveValue('draft-record');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '添加记录', exact: true })).toBeFocused();
});

test('deletion is explicit and cancellable', async ({ page }) => {
  await page.getByRole('button', { name: '编辑 A www', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '删除记录', exact: true }).click();
  const confirmation = page.getByRole('alertdialog');
  await expect(confirmation).toBeVisible();
  await expect(confirmation.getByRole('button', { name: '保留记录' })).toBeFocused();
  await confirmation.getByRole('button', { name: '保留记录' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '删除记录', exact: true }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: '确认删除' }).click();
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(5);
});

test('JSON import is atomic and export contains the current records', async ({ page }) => {
  await page.getByRole('button', { name: '导入记录', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '导入 DNS 记录' });
  await dialog.getByLabel('或粘贴 JSON 内容').fill('[{"type":"A","name":"dev","content":"192.0.2.10"},{"type":"A","name":"bad","content":"999.1.1.1"}]');
  await dialog.getByRole('button', { name: '校验并导入' }).click();
  await expect(dialog.getByRole('alert')).toBeVisible();
  await dialog.getByRole('button', { name: '填入示例' }).click();
  await dialog.getByRole('button', { name: '校验并导入' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.dns-table tbody tr')).toHaveCount(7);
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出记录', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('example.com-dns.json');
  const file = await download.path();
  expect(file).not.toBeNull();
  const data = JSON.parse(await readFile(file!, 'utf8'));
  expect(data.records).toHaveLength(7);
});

test('sidebar peek does not move content and keyboard can expand it', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-1440', 'Desktop hover behavior requires a fine-pointer desktop viewport.');
  await page.getByRole('button', { name: '收起侧边栏', exact: true }).click();
  await page.mouse.move(800, 100);
  const sidebar = page.locator('.desktop-sidebar .sidebar');
  await expect(sidebar).toHaveClass(/collapsed/);
  await expect.poll(() => page.locator('.workspace-main').evaluate(node => Math.round(node.getBoundingClientRect().left))).toBe(64);
  const leftBefore = await page.locator('.workspace-main').evaluate(node => node.getBoundingClientRect().left);
  await sidebar.hover();
  await expect(sidebar).toHaveClass(/expanded/);
  const leftAfter = await page.locator('.workspace-main').evaluate(node => node.getBoundingClientRect().left);
  expect(leftAfter).toBe(leftBefore);
  await page.mouse.move(800, 100);
  await expect(sidebar).toHaveClass(/collapsed/);
  await sidebar.getByRole('button', { name: '侧边栏导航', exact: true }).focus();
  await expect(sidebar).toHaveClass(/expanded/);
});

test('form failure preserves input and permits retry', async ({ page }) => {
  await page.goto('/?page=forms');
  await page.getByRole('switch', { name: '模拟保存失败' }).click();
  await page.locator('.record-form input[name="name"]').fill('retry');
  await page.locator('.record-form input[name="content"]').fill('192.0.2.20');
  await page.getByRole('button', { name: '保存记录' }).click();
  await expect(page.locator('.form-server-error')).toBeVisible();
  await expect(page.locator('input[name="name"]')).toHaveValue('retry');
  await page.getByRole('switch', { name: '模拟保存失败' }).click();
  await page.getByRole('button', { name: '重新保存' }).click();
  await expect(page.locator('.success-banner')).toBeVisible();
});

test('real container reflow and all critical pages fit 320px', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'narrow-300', 'Run the additional 320px sweep once.');
  await page.setViewportSize({ width: 320, height: 840 });
  for (const section of ['dns', 'forms', 'responsive', 'guidelines', 'tokens', 'docs']) {
    await page.goto(`/?page=${section}`);
    await expectNoPageOverflow(page);
  }
  await page.goto('/?preview=1');
  await expectNoPageOverflow(page);
  await page.getByRole('button', { name: '添加记录', exact: true }).click();
  await expectNoPageOverflow(page);
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('documentation loads and the command palette navigates', async ({ page }) => {
  await page.goto('/?page=docs');
  await page.getByRole('button', { name: '阅读界面设计规范', exact: true }).click();
  await expect(page.locator('.markdown-content')).toContainText('必须');
  await expect(page.locator('.markdown-content')).toContainText('推荐');
  await expect(page.locator('.markdown-content')).toContainText('避免');
  await page.keyboard.press('Control+k');
  const palette = page.getByRole('dialog', { name: '快速前往' });
  await palette.getByRole('textbox').fill('响应式');
  await palette.locator('.command-result').click();
  await expect(page).toHaveURL(/page=responsive/);
});

test('responsive playback can be paused and respects reduced motion', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-1440', 'A wide canvas is required to exercise the full range.');
  await page.locator('.device-controls button').nth(2).click();
  await expect.poll(() => page.locator('.preview-frame').evaluate(node => Math.round(node.getBoundingClientRect().width))).toBe(390);
  await expect(page.getByRole('button', { name: '打开站点导航', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '自动演示', exact: true }).click();
  await expect.poll(async () => Number(await page.locator('.width-control output strong').innerText())).not.toBe(390);
  await page.getByRole('button', { name: '暂停演示', exact: true }).click();
  const stopped = await page.locator('.width-control output').innerText();
  await page.waitForTimeout(300);
  expect(await page.locator('.width-control output').innerText()).toBe(stopped);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const transition = await page.locator('.preview-frame').evaluate(node => parseFloat(getComputedStyle(node).transitionDuration));
  expect(transition).toBeLessThan(0.001);
});

test('DNS validation rejects malformed owner names and IPv6 URL injection', () => {
  expect(validateRecord({ ...EMPTY_RECORD, name: 'www', content: '192.0.2.10' })).toEqual({});
  expect(validateRecord({ ...EMPTY_RECORD, name: '*.example.com', content: '192.0.2.10' })).toEqual({});
  expect(validateRecord({ ...EMPTY_RECORD, name: 'a..b', content: '192.0.2.10' }).name).toBeTruthy();
  expect(validateRecord({ ...EMPTY_RECORD, name: '-invalid', content: '192.0.2.10' }).name).toBeTruthy();
  expect(validateRecord({ ...EMPTY_RECORD, type: 'AAAA', name: 'ipv6', content: '2001:db8::1' })).toEqual({});
  expect(validateRecord({ ...EMPTY_RECORD, type: 'AAAA', name: 'ipv6', content: '::1]/path#' }).content).toBeTruthy();
});