## 受托管的截图工作流

首屏和滚动多屏统一用 `scripts/shot_scroll.py`，默认只拍首屏。`shot-quick.ps1` 是同一入口的 PowerShell 兼容包装，不再直接创建 Chrome 进程。截图触发、取景和实际查看按 [视觉验收](../../ai-verified-delivery/references/visual-acceptance.md)，资源政策按 [测试资源预算与回收](../../web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)。

### 使用

目标 Python 环境需已有 Playwright；先复用项目环境，不自动安装依赖。`<skill-dir>` 指本 skill 目录：

```powershell
# 首屏，指定输出文件
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --out page.png

# 一次浏览器会话拍两屏；使用已安装的 Edge，免下载浏览器制品
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --screens 2 --channel msedge --out-dir shots

# PowerShell 7 兼容入口；-Python 可指定虚拟环境解释器
& <skill-dir>/scripts/shot-quick.ps1 -Url 'https://example.com' -Channel msedge -Out page.png
```

未指定输出时，每轮使用独立的系统临时目录 `opencode/shots/<run-id>`，成功图片作为结果保留。指定同一输出文件时，仅成功采集并回收浏览器后才替换文件；失败不会预先删除旧图片。多张图片逐文件原子替换，不承诺整批事务，未收到本轮全部 `SHOT` 行不能将旧文件或部分结果当本轮成功证据。

默认视口 `1440×900`，单次操作超时 30 秒，整个 worker 总期限 60 秒，收尾另留最多约 8 秒。可用 `--width`、`--height`、`--timeout-ms`、`--wall-timeout-ms` 调整；最多 20 屏、宽高各不超过 8192。`--settle-ms` / `--step-wait-ms` 默认 500 毫秒，只是采集等待，不是业务就绪断言；需要交互、登录或精确状态等待时使用项目的受管测试 runner。

代理按 `--proxy` → `SCRAPE_PROXY` →（指定 `--discover-proxy` 时）机外登记解析；没有代理设置且未要求发现时直连。只验证登记端点监听，不据此宣称出口可用。日志不打印代理凭据和页面查询参数。`--channel chrome/msedge` 与 `--executable-path` 互斥，后者必须指向真实浏览器文件，不传包装脚本或垫片。

国内安装按 [浏览器安装与国内网络](../../network-access/references/browser-installation.md) 区分包源和制品源。本机有 Edge/Chrome 时可只补目标环境的 Playwright 包；拒绝安装且没有可用 runner 时记录未执行，不回退到无期限的裸浏览器命令。

### 生命周期与托管边界

`managed_browser.py` 提供独立的本地守护进程（guardian）；没有常驻服务、浏览器池或远程浏览器依赖。Windows 作业对象（Job Object）约束本轮进程树；Linux 的 subreaper 负责接收失去父进程的后代，pidfd 是绑定进程身份的文件描述符。

1. 调用端创建独立 guardian，持有通信管道作为存活信号。guardian 持有操作系统文件锁，同一用户、同一临时目录默认只允许一轮任务；第二轮返回忙，不排队、不自动重试。
2. worker 先等待启动配置。Windows 中，guardian 将其加入启用 `KILL_ON_JOB_CLOSE` 的 Job Object 后才放行；Chromium、Playwright 驱动与后代继承约束，不凭全机进程数认领资源。
3. Playwright 显式关闭 context 和 browser；总期限覆盖启动、导航、截图和正常关闭。到期或调用端管道断开时，guardian 终止本轮进程树。
4. 即使 worker 正常返回，也清理残留后代，核验作业内活动进程归零，再发布截图并删除本轮 profile、浏览器临时文件。worker 原始输出丢弃，避免无界日志增长及凭据回显；失败仅返回异常类型与已知排查提示。
5. 调用端被强制结束时，guardian 通过管道 EOF 收尾。Windows 中 guardian 自身被强制结束，Job Object 仍负责终止成员，但文件清理无法继续；下次运行检测遗留目录并拒绝启动。

Linux 使用独立进程组及 subreaper，回收被重新托管的后代；用 pidfd 确认并终止进程，涵盖另建 session 的浏览器，不只终止原进程组。要求内核和 Python 支持 pidfd。其他平台启动前明确拒绝，交给项目已有受管 runner；不宣称 macOS 具有同等保障。Windows 已实测，Linux 分支需在目标环境另验。

成功必须同时得到本轮 `SHOT` 行和 `CLEANUP verified`，并实际查看图片；文件存在仅证明采集，不证明视觉符合预期。资源收尾不明时禁止叠加失败轮。

| 退出码 | 含义与处理 |
|---|---|
| `0` | 截图及清理成功 |
| `1` | 启动、导航、截图或 worker 失败；检查环境与页面，不盲目重试 |
| `2` | 参数、代理发现或平台能力不满足；修正条件再执行 |
| `3` | 已有任务持锁；等待本轮收尾，不绕过锁并发启动 |
| `4` | 清理未确认或 guardian 异常；停止新增任务，核对资源 |
| `124` | worker 超过总期限，已完成收尾；页面未验收 |
| `130` | 用户取消或调用端退出；guardian 执行收尾 |

状态目录为系统临时目录中的 `opencode/browser-tasks`；Linux 使用 `opencode-<uid>` 隔离用户，截图结果目录同样采用这个前缀。失败清理会保留 `cleanup-failed.json` 与本轮目录，后续运行拒绝继续。恢复时先确认锁已释放、本轮进程资源已终止，再只处理该记录指向的本轮目录与标记；不要按 Chrome 名称或端口杀进程，不删整个共享临时目录。仅 guardian 意外退出留下目录时也适用。系统关机、整个容器被销毁或宿主强杀全部相关进程后，不能指望应用继续清文件；下一轮保守阻断。

### 迁移与复用

- `shot_scroll.py` 的默认屏数由 2 改为 1；多屏显式传 `--screens 2`。
- `shot-quick.ps1` 现在需要 Python Playwright，移除按 PATH/最大缓存版本猜浏览器、隐式环境浏览器覆盖及裸 Chrome 回退。`-Chrome` 映射到 `--executable-path`，推荐 `-Channel msedge/chrome` 或匹配项目版本的缓存。
- 旧 `-VirtualBudget` 已移除，改用 `-TimeoutMs` 与 `-WallTimeoutMs`。页面虚拟时间不能作为进程总期限。
- 其他 skill 的单次视口截图可引用本入口。复杂测试沿用项目 runner；`resilient-browser-fetch` 的挑战处理、持久会话及 `htmlmini` 渲染回退不因本次改动自动获得相同托管保障。

### 验证

```powershell
python -X utf8 -m unittest discover -s <skill-dir>/tests -v
```

生命周期用例使用真实 worker 和持有监听端口的后代，验证成功残留、失败、超时、取消、调用端强制退出、并发拒绝及清理失败阻断，同时保留不相关监听实例。Windows 另验 guardian 强制退出的 Job Object 回收；浏览器用例需要可启动的匹配 Chromium，验证本地两屏、失败不替换旧结果及含空格中文路径。公共网站、代理出口和视觉质量不在这些测试的证明范围。
