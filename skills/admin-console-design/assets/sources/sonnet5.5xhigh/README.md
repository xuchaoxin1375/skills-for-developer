# Nimbus Console · Cloudflare 风格控制台设计参考

参考 Cloudflare 控制台的 **侧边栏（折叠 / 悬停展开 / 自动收起）** 与 **表单页** 设计，给出规范文档、可交互的模拟设计稿与参考实现。

## 快速开始

```bash
npm install
npm run dev      # 开发
npm run build    # 产物：dist/index.html（单文件，可直接托管）
```

打开页面后：

1. 在「设计稿」中选择场景（推荐先看「DNS 记录」：可调列宽、表头排序、批量操作、行内 / 弹窗编辑），拖动底部浮层的宽度滑条，或点击「宽度扫描」做应力测试；
2. 点击「侧边栏行为演示」观察 固定展开 → 折叠 → 悬停展开 → 自动收起；
3. 切换「传统方案 / 并排对比」，对照反例；
4. 在右上角切换 浅色 / 深色 / 跟随系统；
5. 在「文档」页签阅读规范。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文档地图、术语、阅读路径 |
| [docs/01-design-principles.md](docs/01-design-principles.md) | 设计思路与原则 |
| [docs/02-sidebar-spec.md](docs/02-sidebar-spec.md) | 侧边栏规范（状态机、悬停意图、动画、无障碍） |
| [docs/03-form-spec.md](docs/03-form-spec.md) | 表单页规范（布局、校验、保存、离开保护） |
| [docs/04-responsive-a11y.md](docs/04-responsive-a11y.md) | 响应式与无障碍 |
| [docs/05-design-tokens.md](docs/05-design-tokens.md) | 设计令牌 |
| [docs/06-best-practices.md](docs/06-best-practices.md) | 实践指南：必须 / 应该 / 可以 / 避免 |
| [docs/07-usage-deploy.md](docs/07-usage-deploy.md) | 部署与使用说明 |
| [docs/08-data-table-spec.md](docs/08-data-table-spec.md) | 交互式表格与条目规范（列宽调节、排序、批量、粘性操作列、行内 / 弹窗编辑） |

## 技术栈

React 19 · Vite · Tailwind CSS v4 · Lucide 图标 · marked（文档渲染）。
