# 控制台响应式与验证

本页用于采用了相关能力的实现验收；咨询/局部修复按任务裁剪。通用布局选型可结合adaptive-responsive-guide，缺陷根因深查可结合frontend-ux-qa，不要求把所有协议叠加。

## 覆盖范围

默认1440/768/390 + 320回流，300按极窄支持要求做压力检查。改外壳断点补767/768、1023/1024；表切卡阈值按真实容器测两侧，不能把视口宽度当表宽。

| 改动范围 | 关键检查 |
|---|---|
| 外壳/侧栏 | 固定偏好、peek前后main left/width、同一点击目标、抑制/快速划过、Tab/Esc、触屏按钮、抽屉回焦 |
| 表格 | 长值、列显隐、横滚操作列、选择/排序/分页范围、拖拽与键盘、刷新、编辑断点切换 |
| 表单/设置 | 空/非法/合法提交、首错、失败保输入、一次提交、取消/离开、敏感草稿策略、危险确认 |
| 浮层 | 进焦/回焦、Esc、背景交互、视口夹取、嵌套与top layer、长内容可达 |
| 主题/动效 | 采用的主题模式、system变化、首屏、各状态真实对比、减少动态效果仍可操作 |

200%缩放查核心操作，400%检查320 CSS px等效回流；辅助技术另用实际读屏检查，不用DOM检查冒充NVDA/VoiceOver验收。桌面目标至少24 CSS px或满足间距/等效入口，触屏默认争取44px；不把8px列拖热区当完整触屏合格。

## 溢出与滚动

min-width:0/minmax(0,1fr)、长值overflow-wrap:anywhere/有完整查看入口的truncate、浮层max-inline-size约束；允许表自滚，避免页面横溢。先查原因，不在根上clip/hidden掩盖缺陷；Rail内裁剪标签是明确用途。

固定高度工作台不是自动缺陷，需尺寸约束和完整键盘路径。固定批量条/操作条有安全空间，不挡末行或焦点。粘性表头的滚动祖先与真实滚动区域一致。

Skip link聚焦立即可见，main可接焦；隐藏子项不可Tab，Rail主入口仍可Tab且有名称。语义按钮和控件优先，状态不只靠色，避免用全套ARIA装饰没有行为的元素。

## 浏览器探针示例

下例在Playwright中真正改变视口；把`url`换成目标应用地址。它只验页面级溢出，不证明关键控件可点、内容未被裁切或视觉通过。

```js
for (const width of [1440, 768, 390, 320]) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(url);
  await page.locator('main').waitFor();
  const size = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(size.scroll).toBeLessThanOrEqual(size.viewport);
}
```

异步应用等待实际稳定状态，另查主操作bounding rect与点击结果。peek先稳定Rail、记main和关键按钮rect，再触发并等待状态；断言页面没移动，并执行同一目标的真实点击。不要用固定坐标或全行offsetTop一致取代任务结果。

列宽测试读aria-valuenow/min/max，验证拖动、键盘、恢复、cancel、刷新；核对所采用模块的Home/End/Enter契约。[表格说明](tables.md)给出两稿差异。

gpt `assets/sources/gpt6astra-max/tests/acceptance.spec.ts`是样例，其URL、选择器、初始数据与视口配置需要适配，复制文件不等于目标已受CI保护。宽度实验室是开发预览辅助，不是每个生产控制台必须交付的页面；真实iframe宽度可触发查询，transform缩放只是展示尺寸，不等于新视口。

## 证据与门槛

阻断实际保存/删除、核心键盘路径、退出浮层或必要窄屏操作的问题不能标完成。非阻塞视觉差异记录范围和理由；静态可读、运行成功、截图已生成、截图已目检分别报告。

最小记录：输入版本/页面 + 浏览器/视口/主题/方式 + 预期/实际 + 通过/失败/未执行/不适用 + 截图或日志。无浏览器标未执行，有人工条件可手工，不把工具不足写成不适用。
