# 检测层与引擎选择

本文件解释为什么“升到更高层”不等于“更不容易被识别”，以及什么时候该换控制面、换指纹、换出口，而不是继续叠加同类引擎。

## 三层模型

反爬通常交叉检查三类信号：

| 层 | 典型信号 | 能改变它的手段 |
| --- | --- | --- |
| 控制面 | `navigator.webdriver`、`Runtime.enable`、CDP 握手、Playwright/Patchright 的驱动痕迹 | 换驱动方式或不用 Playwright/WebDriver |
| 挑战窗口内的暴露 | WAF 先下发挑战页，挑战在页面加载早期采集环境与驱动会话；这个窗口里暴露了痕迹就判失败 | 让挑战先跑完（晚接入），或用不留痕迹的控制面（系统 Chrome、隐身栈） |
| 引擎/指纹 | canvas、WebGL、字体、GPU、屏幕、UA、插件、`window.chrome` | 定制 Chromium、指纹伪装、真实桌面浏览器 |
| 网络/身份/行为 | IP/ASN、TLS、DNS、地区、cookie、访问节奏、鼠标键盘 | 换出口、修 TLS、持久 profile、`humanize`、降频 |

**读正文之前先分清三件事**：被拒绝（Access Denied / 硬 403）、挑战进行中（挑战页，站点还没放行）、真正文。这三种页面在抓取里长得都像"拿到了东西"，判错一次就会把"再等几秒就能成功"的页面当成失败，或者把失败当成成功。实测的判别方式见下文"挑战窗口"。

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
- **nodriver 换的是控制面，不是指纹。** 它不伪造 canvas/WebGL/字体/GPU，也不改 TLS；Linux 服务器上仍是 Linux。无头模式明显弱于有头，反检测场景优先 `--headful`。非 Cloudflare 的 WAF（如 Akamai）通常只盯控制面与 IP，这类站点上 nodriver 有头常比层 2/3 更有效。
- **IP、ASN、TLS、地区与行为节奏不属于引擎层。** 这些信号出问题时，换引擎通常无效，先按 `network-access` 核对出口并降低频率。

## 选择顺序

先判断失败发生在哪一层，再选引擎；不要只按层号机械升档。

**注意这套顺序是手工选引擎的判据，与 `auto` 阶梯不是一回事**：`auto` 是机器跑的兜底阶梯，它按"会不会白跑一趟"排——先试零成本的 `static`，**装了求解引擎就直接从求解层起步**（层 1 过不了挑战页，先跑它只多花一次浏览器往返），层 1 降为阶梯末尾兜底。手工选层则按下面的判据走：先确认静态层够不够、失败发生在哪一层，再决定升不升。

1. **静态正文可取**：用层 0。TLS/客户端指纹拦截再试 `--impersonate`；不要为静态页启动浏览器。
2. **需要 JS 渲染**：层 1。真实桌面优先 `--real-chrome`；做驱动 A/B 时显式指定 `--playwright-api`。
3. **返回 Cloudflare/Turnstile 挑战**：层 2。仍失败时先 `--headful` 人工接管，再考虑层 3；不要跳过有头直接叠加同类引擎。
4. **指纹/环境不匹配**（canvas、WebGL、字体、Linux 服务器）：层 3；或改用真实桌面 + 系统 Chrome。
5. **层 2 和层 3 以同一挑战签名失败，且有头/真 Chrome 也失败**：更像控制面或 IP 问题。用户自己的浏览器能打开同一 URL 时，先换控制面试 `--engine nodriver --headful`（系统 Chrome 直接 CDP）——换出口只改 IP 信誉，改不了 Patchright 的驱动痕迹；用户浏览器也打不开时才轮到核对 ASN/地区。返回硬 403/Access Denied、页面不出现 Cloudflare 挑战时，`solve_cloudflare` 与层 2/3 都不会起作用，不要按 CF 挑战继续加层。
6. **间歇成功、换出口后结果明显变化**：按 IP 信誉/限流处理，不换引擎。
7. **所有浏览器层都失败，但层 0/curl_cffi 能拿到正文**：回到层 0 或检查是否根本不需要浏览器。

## 另一条路线：复用真实浏览器会话

引擎分层解决的是“没有用户浏览器时怎么伪装”，还有一类问题不属于任何层：**站点的放行凭据在用户自己的浏览器里**（登录态、clearance cookie、已通过的人机验证）。这时唯一有效的路线是复用那个会话本身，而不是继续升层。

| 浏览器归属 | 状态来源 | 保真度 | 适用 |
| --- | --- | --- | --- |
| 新建隔离实例 | 无 | 低 | 批量、无人值守、不涉登录 |
| 接管用户当前打开的浏览器（扩展 relay、CDP attach） | 用户的 profile、cookie、登录态 | 高，接近真人 | 需登录、已有放行凭据、站点对匿名自动化敏感 |
| 托管/远程浏览器 | 提供方的 profile 与出口 | 取决于提供方 | 需要常驻实例或多地出口 |

判据与代价：

- **真实浏览器不等于能过，换控制面也不等于能过**。同一台机器上，有头真实 Chrome 直连与换出口都被拒；换控制面（直接 CDP）曾有一次拿到完整正文，但同条件复测又回到拦截页。站点风控随频次与时间动态变化，真实会话解决的是“身份与凭据”维度，不解决控制面指纹与出口信誉；两者要分别处理，而且都要复测。
- 复用的前提是**用户在场并授权**：由用户自己打开页面并授权接管，或明确把当前会话交给自动化进程。不复制、不导出、不落盘个人 profile 的凭据；凭据与所有权边界见 [browser-operations](../../browser-automation/references/browser-operations.md)。
- 代价：会话所有权与释放按用户与工具的约定来，不能按进程名批量清理；有人在场的操作节奏不可控，不适合无人值守批处理。
- 账号本身被风控、频率超限导致的拒绝属于业务风控，与反自动化无关，换引擎无解。

**本 skill 的落地方式：`cdp-attach` 引擎**（`--cdp-url`，层 1/备用，不进 auto）。用户用 `--remote-debugging-port` 启动浏览器，自己把目标页打开并等它放行，我们再接管读取：

```bash
# 1) 浏览器开着调试端口（用你平时那个 profile，保留你的 cookie / VPN / 代理规则）
#    端口自己定，下面 <port> 前后要一致
msedge --remote-debugging-port=<port>
# 2) 你在这个浏览器里打开目标页，确认正文已经出来
# 3) 接管读取（只连接、只读、然后断开；不关闭浏览器、不导航）
python scripts/resilient_fetch.py --url "<目标 URL>" --cdp-url http://127.0.0.1:<port> --out page.html
```

要点：

- **只读已放行的标签页**：接管到的浏览器里没有目标页时直接报错并提示先手动打开，不猜、不乱点；确实要让它去导航才加 `--cdp-navigate`（导航期间调试会话在挑战窗口里，Akamai 一类站点可能因此判负）。
- **不拥有那个浏览器**：只断开连接，不关闭进程、不删 profile、不导航；`notes` 里记 `browser_owned:false` 与 `control_plane:cdp-attach`，复盘时能区分"我们自建的浏览器"与"用户的会话"。
- **它不解决挑战，只复用结果**：挑战是你在真实浏览器里过的，我们只是把已经渲染好的 DOM 取出来。所以它排在所有自建引擎之后用——自建引擎能过就别动用用户的会话。
- **htmlmini 也能走这条路**：`htmlmini "<URL>" --cdp-url http://127.0.0.1:<port> --render=always --mode markdown`；渲染由 `resilient-browser-fetch` 的 `cdp-attach` 执行（同一代理、同一解释器），htmlmini 只做提取。

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

## 实战判读：Akamai 商品页

某家居零售站商品详情页（Akamai Bot Manager 防护），同一 URL、同一台机器的尝试序列。**同一路线在不同时间的结果不同**，所以按时间分段记录：

| 时段 | 路线 | 结果 | 判读 |
| --- | --- | --- | --- |
| 首次 | 裸 HTTP（`static`） | `403`，`Server: AkamaiGHost` | WAF 层拒绝，不是 404/410 资源级结论 |
| 首次 | 无头 `playwright` | `200`，约 115 KB，正文是站点外壳加一句通用错误文案 | 宽松校验会判成功，属于软错误页 |
| 首次 | 有头真实 Chrome（直连 / 换美国出口） | `Access Denied`，约 400～550 B | 有头、换出口都不等于通过 |
| 首次 | `scrapling` | `403` | 控制面仍是 Patchright，与层 1 同源，一起失败不说明档位不够 |
| 首次 | `nodriver --headful` | `200`，约 1.28 MB，命中商品标题与正文 | 当时唯一成功的一次 |
| 数小时后 | `nodriver --headful`（新 profile、美国出口、当时成功的同一 profile，共 3 次） | 全部回到约 2.7 KB 的 Akamai 拦截页 | **单次通过不可复现**：不是控制面差异，是站点风控随频次升级 |
| 数小时后 | DrissionPage 有头（直连 / 美国出口） | `Access Denied`，约 550 B | 与 Patchright 有头同级，换控制面同样被拦 |
| 数小时后 | DrissionPage 无头 | `200`，约 115 KB 软错误壳 | 与无头 Playwright 同级 |
| 再测 | `nodriver --headful` + SOCKS5 出口（美国，数据中心 AS） | 仍被判 `access denied` | 换到另一国数据中心出口无效 |
| 再测 | DrissionPage 有头 + SOCKS5 出口（浏览器内实测出口已切换） | `Access Denied`，约 550 B | 出口换了，拦截照旧 |
| 再测 | 纯净 Chrome（无任何自动化启动参数，只挂裸 CDP 读结果）+ 同一 SOCKS 出口 + 全新 profile | `Access Denied`，约 400 B | 不是启动参数、驱动痕迹或 `webdriver` 标志的问题 |
| 再测 | 纯 Chrome + **直连** + 全新 profile + 加载中接入 CDP | 2.7 KB 页面 | 按现在的模型读，这是**挑战页**（挑战容器），不是"拦截页"：读得太早，挑战还没跑完 |
| 再测 | 纯 Chrome + **直连** + 全新 profile + 页面加载完 12 秒才接入 CDP | ✅ 200，约 596 KB，标题与正文命中 | 晚接入即可取到内容 |
| 再测 | 纯 Chrome + **直连** + 调试端口开着但不接入 | ✅ 商品页正常渲染 | 端口开着无害，接入才有害 |
| 再测 | 直连 + 用户 Chrome 默认 profile + 系统代理 | ✅ 商品页正常渲染 | 出口与客户端同时满足 |
| 再测 | 晚接入静默窗口 3000 / 5000 / 8000 ms | 三次都 ✅（595 KB / 597 KB / 597 KB） | 3000 ms 已能放行但正文偏少，5000 ms 起内容完整；默认取 5000 |
| 复核 | 普通 Playwright（有头、早挂 CDP、直连），逐秒观察 | 211 B → 2.7 KB 挑战容器 → 9.8 s 变 `Access Denied` 402 B | **挑战在 ~7 s 判定失败**；该会话 `navigator.webdriver` 为 true |
| 复核 | Patchright（有头、同样早挂 CDP、直连），逐秒观察 | 211 B → 2.7 KB 挑战容器 → 12.8 s 变 418 KB 真正文 | 同样早挂 CDP，但 `navigator.webdriver` 为 false，**挑战通过** |
| 复核 | 纯净 Chrome，全程不接 CDP，只看标签标题 | 0.5 s 标题空 → 4.3 s 标题显示 URL → 21.9 s 标题变商品标题 | 挑战页没有标题，**标题变成真实标题 = 挑战已过、正文已就位** |
| 复核 | 纯净 Chrome 晚接入后当场测痕迹 | 挑战早已结束；`navigator.webdriver` 为 false | 晚接入没有"晚"的魔力，效果是**别在挑战窗口里出现** |
| 复核 | 纯净 Chrome 晚接入 + 等 DOM 渲染稳定 | ✅ 1.4 MB 正文（此前 596 KB 属半渲染状态） | 标题就绪时正文只渲染了一半，必须等渲染稳定再读 |

**修正后的结论（这三条与旧版文档不同）**：

1. 站点在拿到第一个文档请求时先下发**挑战页**（`sec-if-cpt-container` 行为挑战容器），挑战在**页面加载早期约 0–10 s** 内判定成败：过了就自己重载正文，没过就落到 `Access Denied`。
2. 决定成败的是**挑战窗口内有没有暴露自动化痕迹**。实测同一台机器、同一 URL、同样"早挂 CDP"：`navigator.webdriver` 为 true（普通 Playwright）→ 挑战失败；为 false（Patchright、系统 Chrome）→ 挑战通过。**"晚接入"之所以有效，是因为它让浏览器在挑战决策窗口里没有调试会话，而不是"晚"本身有什么魔力。**
3. **在挑战跑完之前读到的不是"拦截页"，而是"还没放行"。** 早期读到的 211 B / 2.7 KB 页面是挑战中间页；把它当拦截处理会误判"这条路走不通"，实际上再等十几秒就能拿到正文。

判读顺序：

1. 页面里有没有挑战特征。没有就不是挑战问题，`solve_cloudflare` 与层 3 不必再试。
2. 用户自己的浏览器能不能打开同一 URL。能打开说明出口与地区正常，可以换控制面试（`--engine nodriver --headful`）；打不开才去核对外部出口与 IP 信誉。换控制面只改信号维度，不保证放行。
3. **先分清"被拒绝"和"挑战没跑完"**：标题是 `Access Denied` / 硬 403 → 被拒绝，换引擎与等待都无解；正文是挑战容器（`sec-if-cpt-container`、`Powered and protected by`、Cloudflare challenge-platform）→ 站点还没放行，**再等**才有意义（`chrome-late` 会等标题变成真实标题再读）。把后者当失败，会白白丢掉本来能拿到的正文。
4. **把"挑战窗口内是否暴露痕迹"单独测一遍**：本阶梯的引擎都是"先接入再导航"，在 Akamai 类站点上会一律失败。改用"先自然加载、后接入"读同一 URL，若放行，问题不在引擎档位，而在挑战窗口里有没有调试会话（见下节）。
5. 任何一次通过都要**同条件复测**：换新 profile、换出口、隔一段时间各跑一次并记录结果。单次成功只说明当时风控窗口放行，不能写成"某层更隐蔽"。
6. 拿到 200 先看正文是不是目标内容。这类站点常用"外壳 + 通用错误文案"冒充成功，取数必须带 `--expect-text` 或 `--wait-selector`。
7. 频繁访问会推高出口 IP 的风险分，越打越难；降频与错峰比换引擎更有效。
8. 同出口下**用户自己的浏览器能打开、而所有自动化与纯净浏览器都被拦**时，先按第 3、4 条查"挑战窗口"，再查出口信誉；两者都排除后才是客户端信任度（历史 cookie、行为信号、账号状态）。实测中 profile 全新与可信、指纹标准与否都无差别。

配套命令与产物核对见 [module-api.md](module-api.md) 与 `SKILL.md` 的“工作流”第六步；本案例只解释“为什么结论要靠复测，而不是靠一次成功”。

### Akamai：挑战页与边缘封禁要分开判

Akamai 不是 Cloudflare，`solve_cloudflare` 对它无效。本 skill 的 `--solve-akamai`（层 1/2/3 与 `chrome-late` 可选）只处理**挑战页**，不处理**边缘封禁**；两者页面上很像，处置却相反。

| 页面形态 | 特征 | 含义 | 处置 |
| --- | --- | --- | --- |
| SEC-CPT interstitial | `sec-if-cpt-container` / `sec-bc-tile-container` / `/_sec/cp_challenge/`；iframe 上带 `challenge="<base64 json>"` 与 `data-duration=N` | 站点还没放行，挑战会自己重载正文 | 等；页面自己没解题时本地解 PoW（见下） |
| SBSD 挑战 | 小页面里加载 `/.well-known/sbsd/...` 或带 `?v=<uuid>&t=<n>` 的脚本 | 同上，脚本会提交并重载 | 等；带 `t=` 的是主动挑战，不带 `t=` 只是传感器 |
| 边缘封禁 | 403 + `Access Denied` + `Reference #18.…` + `errors.edgesuite.net`；或站点自己的 403 页但 `Server` 是 Akamai | **第一个请求就被拒，没有挑战窗口** | 换出口；换引擎、换指纹、加求解器都无效 |
| 正常页 | 页面里也可能带 `/.well-known/sbsd` 传感器脚本 | 不是挑战 | 不要按挑战处理（见下面的假阳性） |

**本地能算的那部分**：SEC-CPT 的 crypto/adaptive 挑战是 SHA-256 工作量证明——找 `count` 个答案使 `sha256(sec + timestamp + nonce + difficulty + answer)` 能被 `difficulty` 整除（每答对一个难度加一），`sec` 取自 `sec_cpt` cookie 的第一个 `~` 字段，答完从页面内 POST 到 `/_sec/verify?provider=…`，`sec_cpt` cookie 出现 `~3~` 即放行。服务端还要求至少等满 `data-duration` 秒才收答案，提交太早会被拒。behavioral 型挑战要采集行为数据，本 skill 不伪造，只能等页面自己跑完。

**判读顺序**：先看有没有挑战特征（没有就与 Akamai 无关）→ 再分清“被拒绝”与“还没放行”（标题 `Access Denied` / 正文有 `Reference #` / 硬 403 = 被拒）→ 最后看是不是出口问题。`notes` 里 `akamai:edge_block` 表示边缘封禁（换出口），`akamai:unsolved` 表示挑战没解开（可能是挑战窗口里暴露了痕迹，也可能是出口信誉），`akamai:no_challenge` 表示页面本来就是好的。

**一个必须避开的假阳性**：正常页面也会加载 SBSD 传感器脚本（`/.well-known/sbsd/16ab20?v=<uuid>`，**没有** `t=` 参数）。2026-10-21 实测 hilton 的 offers 页（99 KB，3847 字可见文本）就是这种：它带着传感器脚本却是正常页面。判定 SBSD 挑战必须同时满足“页面很小（≤ 50 KB）”与“脚本带 `t=` 或路径是 `/.well-known/sbsd`”，否则会把好页面当成挑战页拒掉。已按此修掉过一次误判。

**2026-10-21 实测（出口 23.239.105.146 / 162.251.162.205，Patchright 有头与 chrome-late 各跑）**：

| 目标 | 结果 | 判读 |
| --- | --- | --- |
| hilton.com 首页 | chrome-late 拿到 154 KB（标题 `Hilton Page Reference Code`） | 站点自己的 403 页，Akamai 代发；换出口才有意义 |
| hilton.com offers 详情页 | chrome-late 99 KB / playwright 201 KB，均 200 | 正常页（带被动 SBSD 传感器），求解器判定 `akamai:no_challenge` |
| hilton.com/en/hotels/ | 404 + SBSD 脚本 | 资源级结论（404），不是挑战 |
| kohls.com、marriott.com | 403 + `Reference #18.…` | 边缘封禁 → 记 `akamai_edge_block`，换出口 |
| bedbathandbeyond.com 首页 | 200，1.39 MB | 正常页 |
| bedbathandbeyond.com 商品页 | chrome-late 403；playwright 200 但是 115 KB 软错误壳 | 挑战窗口被边缘拦下；与旧案例一致 |

**顺带一条操作提醒**：hilton 的 offers 页带一长串 `cid=` 查询参数，资源很重，`--wait-until load` 时 `Page.goto` 会等满 120 s 超时（**不是被拦**，是 `load` 事件始终不触发）。改 `--wait-until domcontentloaded` 后同一页面 12.5 s 拿到 200 与 101 KB 正文。看到 `Page.goto: Timeout … waiting until "load"` 先换等待条件，别误判成检测失败。

**这台机器上没拿到真实 SEC-CPT 挑战页**：两个出口在上述站点上都只出现“正常页 / 边缘封禁 / 软错误壳”三种形态，没有下发 `sec-if-cpt` + `challenge=` 的 interstitial。因此 PoW 求解器目前只有**本地仿真端到端**证据（`tests/test_akamai.py` 起了本地服务器模拟“挑战页 → `/_sec/verify` 校验 → 发 `sec_cpt` 放行”全流程，同步与异步两条路径都跑通）。**不要把它当成“线上已验证能过 Akamai”**。

**顺带修掉的一个真 bug**：整机走代理的环境常设 `HTTP_PROXY` / `HTTPS_PROXY`，Playwright 的 `connect_over_cdp` 会用这些变量去请求 `127.0.0.1` 的调试端口，于是本地请求被送去代理，chrome-late 直接报 “This does not look like a DevTools server”。现在 chrome-late 连接前会临时给 `NO_PROXY` 补上 `127.0.0.1,localhost`，退出时还原。

### 实战判读：H&M 商品页（出口级拒绝，压根没有挑战窗口）

2026-10-21 实测 `www2.hm.com` 商品页（Akamai Bot Manager）。结论只有一句：**晚接入解决“挑战窗口”，不解决“出口级封禁”**。

| 路线 | 结果 | 判读 |
| --- | --- | --- |
| `static` 裸 HTTP | `403` | WAF 层拒绝 |
| `chrome-late` + 直连 | `Access Denied`，475 B，5.4 s，`pre_attach_state:blocked` | **连挑战页都没出现**：站点在第一个请求就拒绝，不是“挑战还没放行”，晚接入无从谈起 |
| `chrome-late` + 登记的海外代理 | ✅ 1.57 MB 商品页（标题、价格、描述、推荐位齐全），9.9 s | 同一套代码、同一台机器，只换出口就通 |
| 零依赖 Chrome `dump-dom` + 同一代理 | `Access Denied` 页面 | 真实浏览器也过不去：这条路线缺的不是渲染能力 |

要点：

1. **先分清“被拒绝”与“挑战没跑完”**。直连那次 `pre_attach_state:blocked`、页面 475 B、标题就是 `Access Denied`——没有挑战容器、没有重载迹象，属于终局；`chrome-late` 会在标题表明被拒时提前结束等待（实测 5.4 s 就返回，不烧整段预算）。这类站点的正解是**换出口**，不是换引擎、也不是换指纹。
2. **“用户浏览器能打开”也要拆成两个变量**：人手工的浏览器能开，可能同时满足了"出口合格"和"客户端可信"。本例里用户浏览器走系统代理（海外出口），所以**只有代理这一项是真正的差异**；照抄"用户的浏览器能开"而忽略出口，是最常见的误判。
3. **WAF 的拒绝页不是正文**。它标题是 `Access Denied`、正文只有一句话、体积几百字节；采集层若把它当正文交出去，就是**假成功**（一次实测里 htmlmini 交出了 13 个词的拒绝页）。判据按标题认（`Access Denied` / `Forbidden` / `Error 1020`），并与"挑战页"分开处置：拒绝页提示换出口或换晚接入引擎，挑战页提示等或换求解引擎。
4. 同属 Akamai，**姿态可以完全不同**：bedbathandbeyond 会先下发挑战页（挑战窗口存在，晚接入有效），H&M 在被封的出口上直接拒（挑战窗口不存在，晚接入无效）。**不要把上一站的结论套到下一站**，每次都按"有没有挑战特征 → 有没有被拒 → 出口行不行"重新判。

**2026-10-21 补充实测：换到 10808 出口后，H&M 两条路都变终局，而且"浏览器能开"的差异不在 IP**——

| 目标 | 路线 | 结果 | 判读 |
| --- | --- | --- | --- |
| `productpage.1367517001.html` | 静态（curl_cffi chrome124，直连 / 10808 / 7897 三个出口） | 全部 `403`，565 B，`Access Denied` | 边缘封禁，三个出口都不行 |
| 同上 | `chrome-late`（10808） | `akamai_edge_block` | 边缘封禁，没有挑战窗口可等 |
| 同上 | 同一 profile 连跑 3 次、带 / 不带调试端口 | 全部 `Access Denied` | **不是调试端口、也不是 profile 温度**的问题 |
| `/en_us` 首页 | `chrome-late`（10808）与纯 Chrome（不带端口） | `200` 但正文是 H&M 自己的 **"Down for maintenance"** 占位页（18.8 KB / 220 字） | 站点把我们当机器人，**用维护页软挡**，不是挑战 |

关键差异在**客户端身份 + 网络路径**，不在 IP：用户用的是 Edge，而 Edge 的 **Secure Network(Edge VPN) 开关是打开的**（`Preferences → secure_network.setting=1`），同时 Windows 系统代理 `ProxyEnable=0`、Clash 的 TUN 也是关的——**浏览器那条路的出口与我们强制指定的 10808 根本不是同一个**，再加上 Edge 带着长期 cookie 与扩展。**"同一个 IP"这个前提在浏览器那条路上不成立**，照着它去换代理是白忙；这时唯一有胜算的路线是"复用真实浏览器会话"（下一节），而不是继续换引擎、换指纹、换出口。

**2026-10-21 再补充：把出口固定成同一个之后，判决还会按浏览器品牌变**——上表"出口不是同一个"的干扰被控掉后，仍有一层差异：

| 客户端 | 出口 | 结果 |
| --- | --- | --- |
| Chrome（`chrome-late` 默认拉起的就是它） | 10808 | `Access Denied`（`Reference #18.…`，`akamai_edge_block`） |
| Edge（同一套启动参数、同一份全新 profile） | 10808 | ✅ 正常页（1.94 MB DOM，2474 可见字符） |
| Chrome | 7897 / 直连 | ✅ 正常页 |

这次是**受控对照**：只换浏览器可执行文件，出口（10808 → `23.239.105.146`，AS53850 GorillaServers 机房 IP）、协议（`http://` 与 `socks5://` 出口 IP 相同）、profile（全新）、启动参数都不变。三条结论：

1. **边缘封禁可能按客户端品牌判**：上一段推测"浏览器那条路的出口根本不是同一个"，今天证明**同一出口也会因品牌不同而判决不同**。所以"换出口"不是唯一解，"换客户端"也要试。
2. **协议不是变量**：10808 同时接受 `http://` 与 `socks5://`，两种协议出口相同、判决相同；换代理写法救不了 Chrome 客户端。
3. **profile/cookie 也不是变量**：用 7897 预热过的 profile 再走 10808 依然被拒（Akamai 的 `akavpau` 绑 IP，换出口即失效）。

因此 `chrome-late` 的默认浏览器（总是 Chrome）会**继承 Chrome 的判决**：用户自己的 Edge 在同一出口能开，晚接入引擎却一直失败。加 `--browser-brand edge`（或 `--executable-path <Edge 路径>`、或环境变量 `RESILIENT_BROWSER=edge`）即可换客户端；`notes` 里的 `browser_channel` 现在如实写 `system-edge(msedge.exe)`，不再是笼统的 `system-chrome`。

### 排查路径：一次只改一个变量

被拦时不要横向换引擎、换指纹、换代理——那样每次动两个变量，结论不可用。按下面的顺序推进，**每步只动一个变量**，哪一步让结果变了，根因就在那一维：

| 步 | 只改这一项 | 判读 |
| --- | --- | --- |
| 1 | 资源级 vs WAF：同一 URL 的首页与深链各取一次 | 首页 200、深链 403 → 不是首页路由的问题，锁定客户端或挑战窗口 |
| 2 | 控制面：Patchright、直连 CDP、第三方 CDP 库各跑一次 | 结果一致 → 不是驱动痕迹，换控制面无用 |
| 3 | 出口：直连、另一国、另一 ASN 各跑一次 | 结果一致 → 不是 IP 拉黑（但**出口仍可能与客户端叠加**，两者分开验） |
| 4 | profile：全新 vs 可信（他人 profile 副本）各跑一次 | 结果一致 → 不是 cookie、账号或历史 |
| 5 | 自动化痕迹：纯 Chrome + 裸 CDP（零自动化参数） | 仍被拦 → 排除启动参数与 `webdriver` 标志 |
| 6 | 挑战窗口：加载中接入 vs 渲染完再接入 | 结果不同 → 根因是挑战窗口内暴露了痕迹，落到 `chrome-late` |
| 7 | 读的时刻：挑战页 vs 挑战完成后 | 同一个会话早读是挑战页、晚读是正文 → 说明"拦截"其实是"还没放行" |

**走过的弯路**（都排除了，勿重复）：

- 把**一次**成功当结论：同一控制面换新 profile、换出口、隔一段时间复测又回到拦截页；站点风控随频次与时间动态变化。**任何通过都要同条件复测**。
- **把"接入时机"当成根因**：早年的结论是"早接入即被判自动化、晚接入即放行"。复核发现两处问题——(1) 早期读到的 2.7 KB 页面是**挑战页**而不是拦截页，那次"早接入被拦"里可能有一部分只是读早了；(2) 同样早挂 CDP，Patchright（`navigator.webdriver=false`）挑战通过、普通 Playwright（true）挑战失败，说明**决定成败的是挑战窗口里有没有暴露痕迹，而不是"早"或"晚"**。正确的表述是"别在挑战决策窗口里出现"，落地做法是晚接入。
- 复制他人 profile：Chrome 启动时会清掉复制过来的 Akamai cookie（实测 5 → 0），等于全新客户端。
- 拟人化输入（鼠标轨迹、滚动、停留）：在早接入的前提下测过，结论无效——它与接入时机耦合，分不开就不算数。
- TLS 指纹伪装（curl_cffi `--impersonate`）：只改层 0 的出网指纹，对浏览器层的判定无效。
- 换到另一国的数据中心出口：Akamai 对数据中心 ASN 明显更敏感，换国家可能更糟。

**方法论要点**：结论要能写成一句话的因果（“是 X，不是 Y、不是 Z”），并且有**可复现的对照**支撑；只有“换了个东西就好了”不算结论。

## 读页面而不被判成自动化：先让挑战跑完，再接入

适用于"普通 Chrome 打开正常，但本阶梯的每个引擎都被拦"的站点。**机制不是"晚接入有魔力"，而是挑战有决策窗口**：WAF 在第一个文档请求时先下发挑战页，挑战在页面加载早期（约 0–10 s）采集环境与驱动会话，这个窗口里暴露了自动化痕迹就判失败（落到 `Access Denied`），没暴露就自己重载正文。所以要做的是**在挑战决策窗口里不要有调试会话**，等挑战跑完再读。

四步配方：

1. 用系统 Chrome 以**命令行参数**打开目标 URL，**不接任何调试器客户端**（调试端口可以先开着，端口本身无害）。用系统 Chrome 还有第二重收益：它不带 `navigator.webdriver` 之类的标志，挑战能正常通过。
2. 等挑战跑完。**判别信号是标签标题**：挑战页没有 `<title>`，Chrome 于是显示 URL；标题变成真实标题就说明挑战已过、正文已就位。只读 DevTools 的 HTTP 端点（`/json`）即可，不建立调试会话。标题直接是 `Access Denied` 则不用再等。
3. 再通过 CDP 连上浏览器，**等 DOM 渲染稳定后**读正文（`Runtime.evaluate` 取 `document.documentElement.outerHTML`）并落盘。标题就绪时正文往往只渲染了一半（实测 596 KB → 渲染稳定后 1.4 MB）。
4. 用 [htmlmini](../../htmlmini/SKILL.md) 从落盘 HTML 提取正文与字段。

本 skill 已把这套做法做成 `chrome-late` 引擎（`--engine chrome-late`）：`--settle-ms` 控制最小静默窗口，`--render-timeout-ms` 控制渲染等待上限；上面四步由它自动完成，包括浏览器回收。运行结果里 `pre_attach_state`（接入前页面状态）、`final_state`（读取时页面状态）、`attach_delay_ms`、`render_wait_ms` 四个 note 用来复盘当时发生了什么。

边界：

- 只解决"挑战窗口内暴露痕迹"这一维。**出口仍要单独选**：实测同一配方下直连放行、强制走美国数据中心 SOCKS 仍被拦，Akamai 对数据中心 ASN 明显更敏感。
- **更硬的边界：被出口直接封禁的站点没有"挑战窗口"可言**。H&M 商品页在被封出口上第一个请求就回 `Access Denied`（475 B，`pre_attach_state:blocked`），全程无挑战容器、无重载——这类站点的正解是换出口，晚接入、换指纹、换控制面都无效（见上节）。
- 挑战失败（`Access Denied`）时这条路线无解，要换控制面（隐身栈）或换出口；`chrome-late` 会在标题表明被拒时提前结束等待，不浪费整段预算。
- 晚接入读到的是**已渲染完的页面**：懒加载、折叠区、虚拟滚动列表不会展开，与 HTML 快照的边界相同。
- **只读取一次**：在同一会话里再导航等于又回到挑战窗口。同站多页要**一次启动开多个标签**（每个标签各自自然加载），最后统一接入读取；逐页起停也可以，只是每次都要付一次启动与静默窗口。
- 复制他人 profile 不是解法：Chrome 启动时会清掉复制过来的 Akamai cookie（实测 5 → 0），等于全新客户端。
- 这套做法只对"用户有权访问的公开或获授权页面"使用；频繁访问会推高出口 IP 的风险分。

## 同类方案对比

本 skill 只维护自己的引擎阶梯。生态里还有其他实现，选型时按**控制面 / 增量能力 / 许可**三点比，不按功能清单比。

评估一个候选实现的顺序（四步，缺一步就可能把不能用的东西写进依赖）：

1. **控制面**：它怎么驱动浏览器？与本阶梯哪一档同级？（直接 CDP 与 Patchright 是两种不同信号，不要混为一谈。）
2. **增量能力**：相对本阶梯多出的是“真本事”还是“API 更好用”？只有前者才值得引入为引擎档位。
3. **许可**：查 LICENSE 原文与仓库 license 字段，不看 README 的措辞。**禁止商用的一律不进依赖层**——它可以出现在对比表里供用户自行选型，但不能出现在 `requirements*.txt` 或 `auto` 阶梯里。
4. **实测等级**：在同一个目标上与既有引擎同批跑一遍，得出“同级/更强/更弱”的事实结论，而不是照抄作者宣称。

| 方案 | 控制面 | 相对本阶梯的增量 | 许可与维护 | 结论 |
| --- | --- | --- | --- | --- |
| `nodriver`（层 1/备用） | 系统 Chrome 直接 CDP | 无 | AGPL-3.0，作者维护 | 已内置 |
| DrissionPage | 系统 Chrome 直接 CDP | 浏览器控制与数据包收发同一会话（XHR/ws/sse 监听）、`ax:` 无障碍树定位、上下文级独立 cookie 与代理、账密代理、Edge 与移动端控制 | **禁止商业使用**（个人/非营利，文档 CC BY-NC 4.0）；作者个人维护；5.0 仍是 beta | 控制面与 nodriver 同级，**不引入为依赖层**；用户自行选型时先读许可 |
| Playwright / Patchright | 驱动注入 | 层 1–3 已覆盖 | Apache-2.0，多人维护 | 已在阶梯内 |
| Selenium / WebDriver | WebDriver | 语言与生态覆盖广，授权测试场景成熟 | Apache-2.0 | 驱动痕迹明显，适合有授权的测试，不适合绕风控 |
| 托管浏览器（Browserbase 一类） | 提供方实现 | 常驻实例、多地出口、免运维 | 商用计费 | 需要常驻或多出口时用；保真度与出口由提供方决定 |

DrissionPage 的实测记录（与上表同批测试的 Akamai 商品页）：有头直连与美国出口均 `Access Denied`，无头拿到 115 KB 软错误壳，与本 skill 的有头/无头结果同级；`navigator.webdriver` 为 false，未带自动化标志。所以它不是“更隐蔽的引擎”，而是“更省事的 API”——**独特价值在取数与 agent 交互**（数据包监听、无障碍定位、上下文级代理），不在绕过检测。另注：它对 SOCKS 代理会打印“不支持这种代理”的提示，但把 `socks5://` 交给 Chrome 后实际生效（浏览器内实测出口已切换）；遇到该提示先验证出口再下结论。

以上矩阵按当前锁定的 Scrapling 0.5、CloakBrowser wrapper 和 nodriver 0.50.6 整理；这些项目的控制面、浏览器渠道和挑战行为会随版本变化，升级依赖后要重新核对，不能把本表当成永久结论。通过率也高度依赖目标站点、出口 IP 和访问频率，单次成功或失败都不构成通用保证。
