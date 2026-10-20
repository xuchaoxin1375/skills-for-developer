# 检测层与引擎选择

本文件解释为什么“升到更高层”不等于“更不容易被识别”，以及什么时候该换控制面、换指纹、换出口，而不是继续叠加同类引擎。

## 三层模型

反爬通常交叉检查三类信号：

| 层 | 典型信号 | 能改变它的手段 |
| --- | --- | --- |
| 控制面 | `navigator.webdriver`、`Runtime.enable`、CDP 握手、Playwright/Patchright 的驱动痕迹 | 换驱动方式或不用 Playwright/WebDriver |
| 引擎/指纹 | canvas、WebGL、字体、GPU、屏幕、UA、插件、`window.chrome` | 定制 Chromium、指纹伪装、真实桌面浏览器 |
| 网络/身份/行为 | IP/ASN、TLS、DNS、地区、cookie、访问节奏、鼠标键盘 | 换出口、修 TLS、持久 profile、`humanize`、降频 |

## 当前引擎矩阵

| engine | 控制面 | 指纹/引擎 | 挑战求解 | auto |
| --- | --- | --- | --- | --- |
| `static` | 无（HTTP） | stdlib；可选 curl_cffi TLS/HTTP2 | 否 | 是 |
| `playwright` | Playwright，或显式选择的 Patchright | 安装的 Chromium / 系统 Chrome | 否 | 是 |
| `scrapling` | Patchright（Scrapling 0.5） | Patchright + Chromium | 是 | 是 |
| `cloak-cdp` | Patchright `connect_over_cdp` | CloakBrowser Chromium | 是 | 是 |
| `nodriver` | 直接 CDP | 系统 Chrome，不伪造指纹 | 否 | 仅 `--headful` |

关键事实：

- **层号是能力档位，不是隐蔽性排名。** 层 2/3 能解挑战、改指纹，但控制面仍是 Patchright；目标专门卡 Playwright/Patchright 时，层 3 不保证通过。
- **装层 2 会改变层 1 的实际 API。** `scrapling[fetchers]` 依赖 Patchright，而层 1 默认优先 Patchright。要做原版 Playwright 与 Patchright 的 A/B，显式使用 `--playwright-api playwright` 或 `--playwright-api patchright`。
- **`--playwright-api` 只影响层 1。** Scrapling 0.5 内部固定使用 Patchright；CloakBrowser 的 CDP 连接也由 Patchright 建立。
- **nodriver 换的是控制面，不是指纹。** 它不伪造 canvas/WebGL/字体/GPU，也不改 TLS；Linux 服务器上仍是 Linux。无头模式明显弱于有头，反检测场景优先 `--headful`。
- **IP、ASN、TLS、地区与行为节奏不属于引擎层。** 这些信号出问题时，换引擎通常无效，先按 `network-access` 核对出口并降低频率。

## 选择顺序

先判断失败发生在哪一层，再选引擎；不要只按层号机械升档。

1. **静态正文可取**：用层 0。TLS/客户端指纹拦截再试 `--impersonate`；不要为静态页启动浏览器。
2. **需要 JS 渲染**：层 1。真实桌面优先 `--real-chrome`；做驱动 A/B 时显式指定 `--playwright-api`。
3. **返回 Cloudflare/Turnstile 挑战**：层 2。仍失败时先 `--headful` 人工接管，再考虑层 3；不要跳过有头直接叠加同类引擎。
4. **指纹/环境不匹配**（canvas、WebGL、字体、Linux 服务器）：层 3；或改用真实桌面 + 系统 Chrome。
5. **层 2 和层 3 以同一挑战签名失败，且有头/真 Chrome 也失败**：更像控制面或 IP 问题。先换出口、核对 ASN/地区，再显式试 `--engine nodriver --headful`；不要继续在 Patchright 控制面里加层。
6. **间歇成功、换出口后结果明显变化**：按 IP 信誉/限流处理，不换引擎。
7. **所有浏览器层都失败，但层 0/curl_cffi 能拿到正文**：回到层 0 或检查是否根本不需要浏览器。

## nodriver 的边界

nodriver 是可选备用，不是层 2 的替代品：

- 只有 Python 异步接口，复用系统 Chrome/Chromium，不下载浏览器。
- 不启用 Network 域，因此结果里的 HTTP `status` 为 `None`；需要按状态码判定时改用 Playwright/Scrapling，或另做一次有界 HTTP 对照。
- 没有内置挑战求解；`verify_cf()` 只是复选框模板匹配，依赖 opencv 和英文模板，不能当通用求解器。
- 不支持 `--humanize`、`--geoip`、`--hide-canvas`、`--network-idle`、`--referer`/`--no-referer`；这些参数会被忽略。
- 默认临时 profile，退出即清理；需要登录态时用 `--profile-dir`。
- `expert=True` 会关闭站点隔离并强制打开 shadow root，官方明确更容易被检测；本 skill 不暴露该选项。
- 本地会开一个 `127.0.0.1` 的 CDP 调试端口；不要把端口暴露到公网，容器内注意网络隔离。
- 许可为 AGPL-3.0；商用或 SaaS 先评估，不要因为“免费”直接加入依赖。

本实现锁定 nodriver 0.50.6。zendriver 是 API 相近的社区 fork，未纳入本 skill 的依赖或 `auto`；确有需要时先评估维护状态、许可和 Docker/浏览器行为，再单独验证，不能假定可直接替换。

`auto` 只在 `--headful` 时把 nodriver 放到最后；无头 auto 不会尝试它。需要固定路线时显式 `--engine nodriver`。

以上矩阵按当前锁定的 Scrapling 0.5、CloakBrowser wrapper 和 nodriver 0.50.6 整理；这些项目的控制面、浏览器渠道和挑战行为会随版本变化，升级依赖后要重新核对，不能把本表当成永久结论。通过率也高度依赖目标站点、出口 IP 和访问频率，单次成功或失败都不构成通用保证。
