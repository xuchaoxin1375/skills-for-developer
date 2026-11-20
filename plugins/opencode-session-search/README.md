# session-search（OpenCode TUI 插件）

在 TUI 里跨全部项目检索历史会话：`/session-search` 打开关键词输入框，结果放进可继续过滤的列表，选中后直接跳转到该会话。**不提交提示词，不调用模型。**

## 行为

- 输入关键词后调用 `session-search` CLI（来自 `skills/opencode-session-data`），检索标题与正文，覆盖所有工作目录。
- 关键词留空时列出最近会话；多个词用空格分隔，按 AND 匹配。
- 列表里可继续输入过滤标题、目录与片段；Enter 跳转，Esc 取消。
- 子会话会在列表里标注；选中子会话也能直接打开。
- CLI 不可用时退化为服务端标题检索（`/api/session`），只匹配标题与目录。

## 依赖与安装

- `session-search` 命令由 `skills/opencode-session-data` 的链接脚本安装；没有它时插件仍可用，但只能按标题找。
- 安装插件：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -Include opencode-session-search
```

```bash
./scripts/link-plugins.sh --include opencode-session-search
```

- 链接后**重启 TUI**，确保客户端加载新的 TUI 插件；只重载服务端插件不会更新已经在运行的终端界面。
- 插件目录结构：`index.ts`（空的服务端入口）+ `tui.ts`（TUI 入口）+ `package.json`（`exports["./tui"]`）。

## 验证

```shell
$ node --test test/plugin.test.ts
$ powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -VerifyOnly
```

真实 TUI 验收：

- 启动 TUI 后输入 `/`，列表里应出现 `session-search`；命令面板里也有“搜索历史会话（跨项目）”。
- 输入 `/session-search`，在弹窗里查一个只在正文出现的词（如 `PerimeterX`），应能看到带目录和片段的会话。
- 选中后应跳转到该会话，期间没有新的用户消息、没有模型调用。

装载失败时界面无提示，只能查日志：

```text
~/.local/share/opencode/log/opencode.log
```

找 `loading plugin` / `failed to load plugin`，以及 `opencode.session-search` / `opencode-session-search`。

TUI 插件自己还会往临时目录写一行诊断（`tui setup`、查询词与结果数）：

```text
<TMP>/opencode-session-search.log
```

看到 `tui setup runtime=bun ...` 说明 TUI 侧已经装载；没有这行而命令也不可见时，重启 TUI 或检查上面的服务端日志。

## 已知边界

- 正文检索依赖 CLI 的扫描范围：默认包含 V2 会话与未迁移的 V1 旧会话；已归档会话默认不显示。
- 列表只展示摘要，不渲染完整会话；进入会话后由 TUI 自己加载。
- 当前会话刚发出的内容可能尚未落库，检索会短暂落后。
- TUI 插件与新版本 API 绑定；升级 OpenCode 后先跑一次真实 TUI 验收。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File scripts\link-plugins.ps1 -Unlink -Include opencode-session-search
```

```bash
./scripts/link-plugins.sh --unlink --include opencode-session-search
```

卸载后重启 TUI；`session-search` CLI 与 skill 不受影响。
