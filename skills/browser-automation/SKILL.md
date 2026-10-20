---
name: browser-automation
description: >
  检查本地可用浏览器及自动化工具，定位 Chrome/Edge/Chromium 的安装路径，按任务选择浏览器操作方案和测试运行框架，并指导自动化执行。
  用于浏览器发现、Scoop/便携浏览器复用、普通浏览器与 Playwright/Puppeteer/Selenium/MCP 工具选型、人工或无头截图、shot-quick/shot_scroll、点击填写导航与状态等待、CDP/远程浏览器会话，以及截图卡住、浏览器进程残留、超时与资源回收排障。
  测试覆盖、断言设计和回归维护走 web-app-testing，UI 缺陷分析走 frontend-qa，playwright install/scrapling install 及国内下载受阻走 network-access；不因只查浏览器便启动完整测试或 UI 验收。
---

## 浏览器发现、方案决策与自动化操作

把任务目标、当前环境和可用工具转成一个可执行方案。交付说明所用浏览器与工具、选择理由、实际结果及资源收尾；仅咨询时交付决策，不启动浏览器。发现和截图有随 skill 分发的脚本，通用交互由当前可用浏览器工具或项目运行器执行；本 skill 不提供通用交互服务器或常驻浏览器池。

### 工作流程

1. **确定执行环境与目标。**区分宿主、WSL、容器、远程机器和 CI，确定实际用户、解释器及项目目录。确认要查位置、人工截图、脚本操作还是编写持续回归；尊重已有工具选择和任务授权，不把环境检查扩大成登录或修改远端数据。
2. **只读检查已有能力。**查看项目依赖、锁文件、浏览器配置及当前实际可调用的工具。需要定位系统浏览器时读 [浏览器发现](references/browser-discovery.md)，用 `--list-browsers` 查常见目录、注册表和 Scoop 等渠道；不执行候选程序，不把 PATH 无结果当未安装，不通过可能自动取包的 CLI 探测。整机层面的运行时、Python 环境与代理入口用 [resource-inventory](../resource-inventory/SKILL.md) 一次看清，再回到本 skill 选方案。整机层面的运行时、Python 环境与代理入口用 [resource-inventory](../resource-inventory/SKILL.md) 一次看清，再回到本 skill 选方案。
3. **选择一个方案。**按 [工具与框架决策](references/tool-and-framework-choice.md)复用已有工具；说明选择理由、前置条件和一个必要的回退。缺包或制品时读 [安装与国内网络](../network-access/references/browser-installation.md)，并**先向用户报选项与代价再动手**（复用环境已有的自动化能力；只补 Playwright 包并复用系统 Chrome/Edge；显式 `--engine oneshot|cdp` 加本机浏览器；确需匹配制品时才装浏览器，区分包源与制品源；或改人工截图、记录自动化未执行）；不为检查环境自动下载所有浏览器，未获用户同意不安装。
4. **按任务执行。**独立首屏/滚动截图用 [托管截图工作流](references/screenshot-workflow.md)；点击、填写、导航、登录状态和下载等操作读 [自动化操作](references/browser-operations.md)，使用可用工具或项目运行器。测试用例与断言设计只借用 [web-app-testing](../web-app-testing/SKILL.md)所需部分，不重复建立计划。
5. **核验结果与回收。**文件、缓存和进程存在均不能证明任务成功。按目标核验页面状态、业务结果或下载文件；报告实际浏览器版本、工具、证据及未运行项。自己启动的浏览器确认回收后再重试；连接外部会话按其所有权释放，不按进程名批量清理。

### 最短入口

`<skill-dir>` 指本 skill 目录。只读发现仅需 Python 标准库；截图需目标 Python 环境已有 Playwright。

截图前先读 [托管截图工作流](references/screenshot-workflow.md)「如何选择」。目标环境没有 Playwright 包时有三条合规出路：显式 `--engine oneshot|cdp` 加真实浏览器（仍由同一 guardian 托管），记录自动化未执行并说明人工出路，或经用户明确授权后自行组织裸命令执行，并自担期限与回收（声明总期限、显式终止自己启动的进程、核验残留归零，并给出等价于 `SHOT` / `CLEANUP verified` 的采集与清理结果）。**不得把裸 Chrome/Edge 无头命令或 CDP 脚本当作默认回退**：轻量引擎只在显式传 `--engine` 且显式指定浏览器时运行。

```powershell
# 不启动浏览器，也不要求安装 Playwright
python -X utf8 <skill-dir>/scripts/shot_scroll.py --list-browsers

# 只读体检哪条引擎可用、会选中哪个浏览器；不加 --probe-launch 不启动浏览器
python -X utf8 <skill-dir>/scripts/shot_scroll.py --doctor

# 允许使用系统浏览器时，显式自动选择并受管截图
python -X utf8 <skill-dir>/scripts/shot_scroll.py --url 'https://example.com' --discover-browser --out page.png
```

不传选择参数时保留 Playwright 默认制品；项目已固定版本时沿用项目运行器。自动选择失败后不轮流启动候选或自动安装。成功截图需本轮 `SHOT` 与 `CLEANUP verified`，并按任务要求实际查看；当前入口只拍视口（首屏、自顶向下的多屏、末屏），整页、交互及多视口由合适工具或受管项目脚本执行。

### 协作与能力边界

| 主问题 | 读取位置 |
|---|---|
| 浏览器在哪、系统版本怎么复用、包装器能否直接运行 | [浏览器发现](references/browser-discovery.md) |
| 选现有浏览器工具、Playwright/Puppeteer/Selenium，或测试运行器 | [工具与框架决策](references/tool-and-framework-choice.md) |
| 自动点击填写、状态等待、CDP、下载和会话所有权 | [自动化操作](references/browser-operations.md) |
| 截图命令、期限、调用端异常退出、残留进程及旧入口迁移 | [托管截图工作流](references/screenshot-workflow.md) |
| 浏览器包/制品下载、代理、镜像和系统依赖 | [network-access 安装参考](../network-access/references/browser-installation.md) |
| 测什么、断言、测试数据与回归维护 | [web-app-testing](../web-app-testing/SKILL.md) |
| 页面哪里有问题、布局/交互/可访问性诊断 | [frontend-qa](../frontend-qa/SKILL.md) |

资源预算政策复用 [测试资源预算与回收](../web-app-testing/references/environment-and-maintenance.md#测试资源预算与回收)，不用完整测试 skill 代替工具操作说明。普通页面提取沿用 `htmlmini`；挑战页经网络分流确认后才用 `resilient-browser-fetch`，反检测的控制面/指纹/IP 分层与 Playwright/Patchright 选择也由该 skill 负责。这些工具不会因引用本 skill 自动获得截图 guardian 的回收保证。

### 验证与限制

浏览器发现和截图的回归入口：

```powershell
python -X utf8 -m unittest discover -s <skill-dir>/tests -v
```

Windows 已验证发现、托管截图与轻量引擎两屏采集；Linux/macOS 的路径规则只有隔离样本验证，Linux guardian 还需目标系统实测，macOS guardian 当前不支持。工具选型及通用操作指引需结合目标项目验证；脚本测试不证明所有框架、远程服务或实际代理都可用，也不证明 skill 自动触发效果。
