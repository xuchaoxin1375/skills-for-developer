export interface Scenario {
  id: string;
  title: string;
  sub: string;
  to: string;
  doc: string;
  points: string[];
  tries: string[];
}

export const SCENARIOS: Scenario[] = [
  {
    id: "dns",
    title: "DNS 记录",
    sub: "交互式表格 · 列宽 · 排序 · 批量 · 行内编辑",
    to: "/dashboard/dns",
    doc: "08-data-table-spec",
    points: [
      "侧边栏三态：固定展开 / 折叠成图标栏（图标居中、文字不外露）/ 折叠后悬停覆盖式展开，并有手动按钮",
      "列宽可调：拖动表头右缘的分隔条，或聚焦后用 ←/→，双击恢复默认；宽度会被记住",
      "表头排序按钮（三态：升序 → 降序 → 无）；列再多也只在表格容器内横向滚动",
      "首列勾选与末列「Edit / Delete」粘性常驻：横向滚动时始终可见，并带滚动阴影提示",
      "编辑两种形式可切换（Display options → Edit style）：行内展开编辑区 / 弹出编辑窗口",
      "勾选 / 全选 / Shift 连选，底部悬浮批量条（代理状态、导出、删除），删除与批量修改均可撤销",
      "分页 + 跨页选择；容器 < 700px 转为卡片列表",
    ],
    tries: [
      "拖动 Content 列右缘改变宽度；再用 Tab 聚焦分隔条，按 ← / → / Shift+→",
      "Display options 勾选 Modified、Comment 等列，让表格变宽，然后横向滚动，观察最右侧 Edit 始终可见",
      "点击任意一行的 Edit：把 Name 清空后保存，观察首错聚焦；改成 www 并选 CNAME 触发冲突",
      "勾选一行，按住 Shift 点击另一行连选 → 点击底部的 Proxied / Delete → 点击通知里的 Undo",
      "按 [ 键折叠侧边栏，再把鼠标移到图标栏上，然后移开",
      "把宽度拖到 700px 以下，观察表格变卡片",
    ],
  },
  {
    id: "form",
    title: "添加 DNS 记录",
    sub: "单列表单 · 两级校验 · 粘性操作栏",
    to: "/dashboard/dns/new",
    doc: "03-form-spec",
    points: [
      "单列、分组（fieldset / legend）、可见标签 + 辅助说明，不依赖 placeholder",
      "两级校验：失焦即时校验；提交时汇总并自动聚焦首个错误，已填内容全部保留",
      "保存按钮不因校验而置灰；保存中显示进度并防止重复提交",
      "操作栏粘性固定在底部；有未保存修改时拦截离开",
      "容器 ≥ 1040px 时出现帮助侧栏——取决于内容区而非视口",
    ],
    tries: [
      "什么都不填，直接点 Save record",
      "在 Name 中粘贴 www.myexample.com（会自动缩写）",
      "Type 选 CNAME，Name 填 www 后保存（触发服务端冲突并映射回字段）",
      "输入一半后点击侧边栏的其他页面",
    ],
  },
  {
    id: "settings",
    title: "SSL/TLS 设置",
    sub: "设置页 · 即时生效 vs 显式保存",
    to: "/dashboard/settings",
    doc: "03-form-spec",
    points: [
      "设置页行布局：宽容器左说明右控件，窄容器自动上下堆叠",
      "开关类设置「即时生效」，其余表单「显式保存」，并在界面上明示",
      "出现修改后才显示粘性保存条，可一键放弃",
      "危险操作置于页面底部，输入域名二次确认（按钮不禁用，以校验反馈）",
    ],
    tries: [
      "切换 Encryption mode，观察底部保存条",
      "把邮箱改成无效值后保存",
      "点击 Remove site… 后不输入直接确认",
    ],
  },
  {
    id: "wizard",
    title: "添加站点",
    sub: "分步表单 · 向导",
    to: "/dashboard/sites/new",
    doc: "03-form-spec",
    points: [
      "字段较多时拆成 3 步，每步只做一件事",
      "窄屏下 Stepper 退化为 “Step 2 of 3” + 进度条",
      "切换步骤时焦点移动到步骤标题，读屏用户不迷路",
      "Review 汇总并允许逐项回改，最终提交前要求确认",
    ],
    tries: ["在域名中粘贴 https://www.example.com/path", "第 3 步不勾选直接提交"],
  },
  {
    id: "overview",
    title: "概览",
    sub: "仪表盘 · 清单",
    to: "/dashboard/overview",
    doc: "01-design-principles",
    points: ["指标卡片与清单并列，响应式网格", "进度使用 role=progressbar 并提供文字说明"],
    tries: ["拖动宽度观察指标卡片从 4 列到 1 列"],
  },
];
