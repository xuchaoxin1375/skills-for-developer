# Playwright 浏览器安装加速（通用）

> 何时读：缺浏览器、CI 从零装、默认 CDN 下载数小时时。只记长期有效的品类做法，不记版本号与本机路径；各仓库的代理/证书特例放自家治理文档。

## 1. 国内镜像（推荐）

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright"
playwright install chromium   # 只装 Chromium，减少下载量
```

`*nix` 用 `export`，备选镜像 `https://cdn.npmmirror.com/binaries/playwright`（部分版本可用）。
经 npm 装的也可用：`npm config set playwright_download_host https://npmmirror.com/mirrors/playwright`。

## 2. 有系统浏览器则免下载

`playwright install chrome` 装体积更小的 channel 版；或启动时直连系统浏览器
（Python：`p.chromium.launch(channel="chrome")`）。功能验证够用，像素级视觉基线仍建议用 playwright 自带浏览器。

## 3. 手动放缓存（最后手段）

用下载工具拉报错信息里对应版本的构建 zip，解压到本系统缓存目录（子目录名即版本号，以报错为准）：

| 系统 | 缓存目录 |
|---|---|
| Windows | `%USERPROFILE%\AppData\Local\ms-playwright\` |
| macOS | `~/Library/Caches/ms-playwright/` |
| Linux | `~/.cache/ms-playwright/` |

## 4. 工具链纪律

- 先探环境再装：已有系统浏览器优先免下载，其次镜像只装所需通道，全量安装最后。
- 命令行截图只做降级：优先 playwright 脚本（自动等待+断言+截图一次完成），手拼 CDP 其次，手拼无头浏览器截图命令不用。
- 包管理器垫片（如 scoop 的 `chrome` 垫片会注入 `--user-data-dir` 等参数）可能让无头截图静默失败：直调真实浏览器可执行文件，或走 playwright 通道版。
- 选择器不臆测：先 evaluate 探真实 DOM 再写断言。
