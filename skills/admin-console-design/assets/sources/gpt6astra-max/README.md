# EdgeLab | 界面设计实验室

参考 Cloudflare 控制台设计理念的独立交互原型。通过 DNS 管理综合案例，演示可折叠导航、悬停预览、规范化表单、深浅主题和真实响应式重排。

**重要：本项目不是 Cloudflare 官方产品，不连接 Cloudflare API。所有数据均为本地演示。**

## 快速运行

```bash
npm install
npm run dev
```

```bash
npm run build
npm run preview
```

Node.js 需要满足项目所使用的 Vite 7 要求：20.19+ 或 22.12+，推荐使用当前受支持的 Node.js LTS。

## 推荐体验路径

1. 打开默认的 DNS 管理案例，悬停预览内部的图标导航。
2. 收起左侧工作台导航，再通过鼠标悬停或键盘聚焦展开。
3. 添加记录，先留空提交，再尝试不合法的 IP 地址。
4. 取消新增后重新打开，检查草稿；成功保存后检查记录和导出文件。
5. 在“表单与校验”页面打开“模拟保存失败”，体验重试。
6. 切换手机预设、拖动宽度滑条或播放自动演示。
7. 阅读“设计要点”“实现指南”及“交付文档”。

## 文档地图

| 文档 | 内容 |
| --- | --- |
| [00 设计规划](public/docs/00-design-plan.md) | 目标、范围、线框、信息架构 |
| [01 设计规范](public/docs/01-design-guidelines.md) | MUST / SHOULD / MAY / NEVER |
| [02 交互说明](public/docs/02-interaction-spec.md) | 导航状态机、表单、数据操作 |
| [03 开发部署](public/docs/03-development.md) | 代码结构、运行、部署、生产化 |
| [04 验收清单](public/docs/04-acceptance.md) | 浏览器用例、截图、人工验收 |
| [05 来源边界](public/docs/05-reference.md) | 官方参考与独立设计决策 |

应用内可以阅读文档、下载单份 Markdown，或合并下载全部指南。

## 页面入口

- `/`：DNS 综合案例。
- `/?page=navigation`：侧边栏交互。
- `/?page=forms`：单列表单与失败模拟。
- `/?page=responsive`：响应式实验。
- `/?page=guidelines`：可阅读规范与个人验收笔记。
- `/?page=tokens`：可复制的设计令牌。
- `/?page=docs`：完整文档地图。
- `/?preview=1`：独立控制台预览，适合真实视口验收。

## 验证

```bash
npx tsc --noEmit
npx playwright install chromium
npx playwright test
npx playwright show-report
```

Playwright 用例与配置已提供。浏览器用例和截图是否通过，以实际运行报告为准；构建成功不代表通过视觉、无障碍或交互验收。交付环境如不提供浏览器执行能力，不应声称完成浏览器验收。

## 技术与数据

React 19、TypeScript、Vite、Tailwind CSS v4、Lucide 图标、原生 dialog、CSS Container Queries。偏好与数据使用 `edgelab.*` 命名空间的 localStorage；存储不可用时仍可在当前挂载的页面内使用，但刷新或切换页面不保证保留。

不存放任何密钥，不发送 DNS 变更请求。请勿把本地存储用于生产凭证。