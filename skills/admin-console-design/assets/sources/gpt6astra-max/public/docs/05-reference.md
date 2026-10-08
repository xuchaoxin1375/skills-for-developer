# 参考来源与适用边界

## 1. 原始参考

用户提供的 Cloudflare DNS 管理界面截图，展示了以下值得研究的模式：

- 收起为图标栏的导航与覆盖式展开。
- 持续可见的域名上下文。
- 就近放置的搜索、筛选、显示设置、导入导出和新增入口。
- 字段式筛选浮层与表格行内编辑入口。
- 清晰的中性背景、边界和重点操作层级。

截图用于理解交互与布局，而不是宣称获得该产品的源码、内部令牌或完整规范。

## 2. 官方资料

### Project A11Y

[Project A11Y: how we upgraded Cloudflare's dashboard to adhere to industry accessibility standards](https://blog.cloudflare.com/project-a11y/)

参考内容：表单标签、必填标注、持久说明、校验与错误处理、语义表格、键盘访问，以及不能只依靠颜色传达信息。

文章描述的是 Cloudflare 自身的改进与合规工作，不应将其中的合规声明转移到本实验室。

### Dark Mode for the Cloudflare Dashboard

[Dark Mode for the Cloudflare Dashboard](https://blog.cloudflare.com/dark-mode/)

参考内容：语义颜色体系、浅色与深色的系统化映射、跟随系统的主题选择、非纯黑背景，以及对默认、悬停、聚焦、激活状态逐一检查。

### WCAG 与模式参考

[WCAG 2.2 标准](https://www.w3.org/TR/WCAG22/)

[WAI-ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)

用于继续核对回流、焦点、颜色对比度、控件目标尺寸与对话框等模式。采用原生组件可以降低实现成本，但不能免除实际辅助技术测试。

## 3. 本案例的独立设计决策

- EdgeLab 名称、实验室品牌、信息架构与中文文案。
- 224 / 64 / 56px 导航宽度。
- 120ms 进入、240ms 离开、220ms 宽度过渡。
- 1000px 工作台断点、960px 固定导航降级、640px 列表回流。
- 真实容器宽度滑条、自动往返演示和独立预览。
- 本地新增草稿、模拟保存失败、JSON 导入导出和验收笔记。
- 本项目全部颜色值、字号、间距、圆角与阴影令牌。

这些选择用于演示设计方法，不代表 Cloudflare 官方推荐、内部实现或逐像素还原。

## 4. 不属于交付范围

- 真实 DNS 解析与 Cloudflare API 集成。
- Cloudflare 账户、授权、账单、权限或组织管理。
- 完整 RFC 级别记录校验、DNSSEC 签名或证书配置。
- 实时流量分析。案例中的记录分布只统计本地记录。
- 经第三方认证的 WCAG 合规、正式安全审计或生产 SLA。

## 5. 使用建议

应参考状态、任务流程、错误恢复与可访问性，而不是把品牌资产和产品界面原样复制到自己的产品。实际交付前，根据自身用户、数据量、权限风险与浏览器范围重新验证全部设计选择。

本项目不附带对第三方商标、界面资产或资料的额外授权。对外发布时保持独立项目说明，不暗示 Cloudflare 的认可、合作或背书。