# 三参考工程构建产物快照

- 快照日期：2026-10-07（三工程 `dist/` 均晚于各自 `src/` 最新改动，fable 版已含当日侧栏图标居中修复）。
- 来源：三份 Cloudflare-inspired 参考工程的 `dist/`，Vite 单文件内联构建（JS/CSS 全部 inline，无 `/assets` 外链）。
  源码与 docs 在**本仓库外**的参考工程里，路径见 SKILL.md「素材来源」的 `<参考工程根>` 占位符。
- 用法：每个目录的 `index.html` 自包含，直接双击或 `file://` 打开即可离线预览，无需起服务、无依赖。

| 目录 | 对应工程 | 体积 | 产物里能看到什么 |
|---|---|---|---|
| `fable5.1-high/` | fable5.1-high | 605 KB | 侧栏状态机最完整实现（hover/kbFocus peek、suppressed、`[` 收起）、DNS 列表旗舰页、命令面板 |
| `gpt6astra-max/` | gpt6astra-max | 512 KB + `docs/` | 含 `docs/00-05` 规范快照（构建时随 public 拷入）、acceptance 测试对应实现 |
| `sonnet5.5xhigh/` | sonnet5.5xhigh | 524 KB | 含 Legacy 传统反例页（`references/anti-patterns.md` 的实物对照）、列宽拖拽与宽度实验室 |

## 维护

- 刷新：源工程重新 `npx vite build` 后，把新 `dist/*` 覆盖到对应目录，并更新本文件的快照日期。
- 定位：这是**只读产物快照**，用于没有参考工程的机器上也能看到成品形态；
  对照实现细节（组件结构、CSS 变量名、注释）仍以 `<参考工程根>` 的源码为准，产物不含源码。
