# 三参考工程构建产物快照

- 来源：三份 Cloudflare-inspired 参考工程的 `dist/`，Vite 单文件内联构建（JS/CSS 全部 inline，无 `/assets` 外链）。
  源码与 docs 在**本仓库外**的参考工程里，路径见 SKILL.md「素材来源」的 `<参考工程根>` 占位符。
- 用法：每个目录的 `index.html` 自包含，直接双击或 `file://` 打开即可离线预览，无需起服务、无依赖。

| 目录 | 对应工程 | 体积 | 产物里能看到什么 |
|---|---|---|---|
| `fable5.1-high/` | fable5.1-high | 605 KB | 侧栏状态机最完整实现（hover/kbFocus peek、suppressed、`[` 收起）、DNS 列表旗舰页、命令面板 |
| `gpt6astra-max/` | gpt6astra-max | 512 KB + `docs/` | 含 `docs/00-05` 规范快照（构建时随 public 拷入）、acceptance 测试对应实现 |
| `sonnet5.5xhigh/` | sonnet5.5xhigh | 524 KB | 含 Legacy 传统反例页（`references/anti-patterns.md` 的实物对照）、列宽拖拽与宽度实验室 |
| `shots/` | 区域截图 | 9 张视口 WebP | 下表：常用区域直达引用，免每次重开产物 |

## 区域截图对照（`shots/`，按引用频率排）

| 文件 | 对应区域 | 引用时看什么 |
|---|---|---|
| `fable-dns-1440.webp` | fable DNS 旗舰表 1440 | 骨架 9 层全貌：工具栏主操作最右、配额条、可排序表头、行末 Edit |
| `fable-dns-edit-1440.webp` | fable 行内展开编辑器 | 行内/弹窗共用同一表单：Type/Name 联动、Proxy 开关、TTL、Delete |
| `fable-dns-rail-1440.webp` | fable Rail 收起态 | 收起后图标列与内容补位，覆盖不推挤的对照 |
| `fable-dns-390.webp` | fable 窄屏 390 卡片 | 容器切卡片：三行式、操作可用、无横滚 |
| `fable-form-create-1440.webp` | fable 长表单 Create | 分组卡、右侧粘性大纲、RadioCards、Tags、保存不置灰 |
| `gpt-dns-1440.webp` | gpt DNS 表纯预览（`?preview=1`） | 筛选/显示设置、导入导出入口、分页（导入原子性见其 `docs/02`，截图看不出） |
| `sonnet-dns-1440.webp` | sonnet DNS 表纯页（`#/dashboard/dns?embed=1`） | 列宽调节、Details/Priority 列、末列 Actions 粘性 |
| `sonnet-add-1440.webp` | sonnet 添加记录单列表单（展示壳版，左侧要点同框） | 两级校验说明、保存不置灰、粘性操作栏（左侧本场景设计要点一并可读） |
| `sonnet-legacy-1440.webp` | sonnet 并排对比（改进 vs 传统反例，浮层已收起） | 评审先跑此图：传统表无排序/无复选/无批量，与改进逐项对照 |

复现：`shots/` 由 Chromium 离线渲染对应产物截取（fable 路由直达；gpt 用 `?preview=1`；sonnet 纯页用 iframe 同文档 hash `#/dashboard/dns?embed=1`，并排对比在展示壳内收起控制浮层后截取）。
存量格式：WebP，`quality=65, method=6`（pillow）；小字已验可读。新增截图沿用同参；字密图体积超标时 quality 可下探到 60，字糊时提到 70。
转码依赖 pillow（缺则 `pip install pillow`，需 WebP 支持）；截图复现依赖 Chromium（Playwright 直驱 file:// 产物）。

## 维护

- 刷新：源工程重新 `npx vite build` 后，把新 `dist/*` 覆盖到对应目录，并更新本文件的快照日期。
- 定位：这是**只读产物快照**，用于没有参考工程的机器上也能看到成品形态；
  对照实现细节（组件结构、CSS 变量名、注释）仍以 `<参考工程根>` 的源码为准，产物不含源码。
