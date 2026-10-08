# 构建快照与截图

三工程Vite单文件构建，JS/CSS内联，可直接打开各目录index.html预览。gpt文档依赖HTTP fetch，需读取Markdown原文件或在本地HTTP服务下预览；“单HTML可打开”不等于所有文档在file协议下都能加载。

源码与构建配置已归档到[assets/sources](../../assets/sources/README.md)，不再依赖缺失的SKILL“素材来源”章节或外部本机路径。版本校验见[manifest](../../assets/sources/manifest.json)。

| 目录 | 当前快照 | 用途 |
|---|---|---|
| `fable5.1-high/` | 2026-10-08同步外部侧栏修复与后续OpenCode修复，重新构建并归档 | 主图标、焦点保持/Esc、分组节点、按住点击与实际导航已复测；其余边界见对照表 |
| `gpt6astra-max/` | 2026-10-08核对，与参考目录dist哈希相同，含docs | 文档/导入/验收案例；不是已全面执行测试的报告 |
| `sonnet5.5xhigh/` | 2026-10-08重新构建并刷新 | 包含用户更新后的Stage底部dock与尺寸行为 |

## 截图状态

`shots/`原九张WebP为 **历史截图，原拍摄日期未记录**；没有把它们写成当前版本已验证证据。尤其sonnet-add/legacy的展示舞台不是新dock状态，旧fable Rail图也不能代表侧栏修复后的版本。未变的gpt产物也不意味着旧图覆盖所有状态。

| 文件组 | 用途 |
|---|---|
| `fable-dns-1440/390`、`fable-dns-edit-1440`、`fable-dns-rail-1440` | DNS布局、编辑、Rail历史状态 |
| `fable-form-create-1440` | 长表单分组与辅助大纲 |
| `gpt-dns-1440` | DNS预览；导入原子性无法从图证明 |
| `sonnet-dns-1440`、`sonnet-add-1440`、`sonnet-legacy-1440` | 表格/表单/对照历史状态 |
| `sonnet-stage-2026-10-08.webp` | 新Stage默认dock收起状态，2026-10-08实拍 |
| `fable-dns-1440-2026-10-08.webp`、`fable-dns-390-2026-10-08.webp` | 外部侧栏修复及后续OpenCode修复最终构建的DNS页面 |
| `fable-rail-1440-2026-10-08.webp`、`fable-peek-1440-2026-10-08.webp` | 修复后Rail与peek对照；主图标x保持不变，回焦/目标身份另见对照表 |

本轮1440/390和舞台截图及浏览器日志在真源仓库的本地`.workspaces/admin-console-design-workspace/2026-10-08-review/`，属于评估证据，不随skill分发。上表新Stage截图随快照归档。

fable修复证据在本地`.workspaces/admin-console-design-workspace/2026-10-08-fable-refresh/`；最终版本在`after-opencode/`，包括构建哈希、7项侧栏检查、4条路径、八视口记录与对应PNG。初轮结果只代表各自版本，不混作最终证据；上表带日期的四张fable WebP来自最终版本，随快照分发。

## 打开相关页面

- fable：`index.html#/dns/records`，具体页面路由查源码router/App。
- gpt：`index.html?preview=1`；文档在本地HTTP服务下查看。
- sonnet：`index.html`为展示壳，`index.html#/dashboard/dns?embed=1`为控制台DNS页；variant=legacy为刻意反例。

自动化直接导航到对应URL并操作即可，不要求再双击一遍。产物用来观察，源码用来复用，截图用来对照外观；三者证据范围不同。

更新时归档源码/产物、记录manifest、重拍受影响截图或注明历史状态。具体交互与已知缺口查[对照表](../builds-comparison.md)。
