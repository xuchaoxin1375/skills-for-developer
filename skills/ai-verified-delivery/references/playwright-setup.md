## Playwright 环境准备与下载排障

浏览器缺失、启动失败、下载受阻或 CI 首次配置时读取。先按 [工具准备](verify-and-templates.md)核对已有依赖与授权，再选择补齐方案；本文件不固定版本、公共镜像地址或本机路径。

### 先证明可运行

1. 确认项目锁定的 Playwright 包版本、实际运行时和配置所需浏览器，不用可能自动下载的命令当探测。
2. 用项目已有 runner 启动目标浏览器并完成最小页面断言。包版本命令、缓存目录或可执行文件存在都不足以证明可运行。
3. 缺二进制时安装该包版本匹配的浏览器；缺系统库时单独列明系统依赖与权限，不把系统级安装混在普通下载里。
4. 安装后复跑启动与断言，记录实际版本、OS、字体和运行证据；后续升级包时重新核对二进制兼容。

项目已有依赖且安装已授权时，可通过项目实际包管理器执行浏览器安装。以下命令以 pnpm 项目为例，不适用于尚未安装 Playwright 的环境：

```powershell
pnpm exec playwright install chromium
```

只安装产品支持范围所需浏览器；不能用“只装 Chromium”静默删掉必需 Firefox/WebKit 验收。Linux 的 `--with-deps` 可能安装系统依赖，先核对权限与影响。

### 网络与可信来源

优先官方源、已授权代理或受控制品库。浏览器制品和 npm 包是不同下载链路，修改 npm registry 不等于解决浏览器下载。公共镜像的路径、版本覆盖与可用性必须现场核验，不把某个地址永久写为推荐默认。

Playwright 可用 `HTTPS_PROXY` 和 `PLAYWRIGHT_DOWNLOAD_HOST` 指定下载条件；后者必须是已确认兼容的制品来源。以下是语法示例，尖括号由实际授权配置替换：

```powershell
$env:HTTPS_PROXY = '<approved-proxy-url>'
$env:PLAYWRIGHT_DOWNLOAD_HOST = '<approved-artifact-base-url>'
```

```bash
export HTTPS_PROXY='<approved-proxy-url>'
export PLAYWRIGHT_DOWNLOAD_HOST='<approved-artifact-base-url>'
```

这些变量仅在需要的进程/会话中使用，避免无意改变其他任务。企业 CA 按下载器支持方式配置；不通过关闭 TLS 验证解决下载失败。下载设超时，保留真实错误，记录来源与匹配的构建身份。

### 已有浏览器与手动缓存

已有系统浏览器可以作为有条件的替代：确认项目支持对应 channel，用最小用例验证，再明确其版本与证明范围。它不能默认替代产品承诺的其他浏览器或原视觉基线环境。`playwright install chrome` 本身会安装浏览器，不属于“免下载探测”。

必须手动准备缓存时，从可信来源取得包版本匹配的制品，核对构建、目录布局、平台和解压完整性，再实际启动。若配置了 `PLAYWRIGHT_BROWSERS_PATH`，以其值为准；常见默认位置如下：

| 系统 | 默认缓存位置 |
|---|---|
| Windows | `%LOCALAPPDATA%\ms-playwright\` |
| macOS | `$HOME/Library/Caches/ms-playwright/` |
| Linux | `$HOME/.cache/ms-playwright/` |

不要假设 macOS 与 Linux 缓存相同。目录存在不证明匹配版本或系统依赖齐备，手动缓存仍须启动验证。

### 诊断与验收边界

- 包管理器或浏览器垫片可能注入额外参数；查真实可执行文件与启动参数，优先走受支持的 runner/channel。
- 关键流程用脚本化浏览器操作、自动等待和结果断言；手工截图或临时 CDP 探索可作诊断，不冒充持续回归。
- 定位器来自实际 DOM/可访问树，优先角色与名称；稳定 test id 可辅助定位，另验必要可访问名称，不能用 test id 掩盖错误。
- 中文截图先确认字体实际渲染，视觉回归固定 OS、字体、浏览器与配置。
- 受阻时可继续独立工作，但缺失的必需检查保持 `BLOCKED`/`NOT_RUN`；等效替代须满足同一 AC 并记录环境差异。

具体参数与平台要求以 [Playwright 浏览器文档](https://playwright.dev/docs/browsers)和项目锁定版本为准，环境特例留在项目文档。
