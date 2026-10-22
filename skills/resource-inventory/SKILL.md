---
name: resource-inventory
description: >
  本机资源体检与复用：一次汇总运行时（Node/Python/pnpm/uv/conda/git 等）、Python 解释器与可用引擎层、
  浏览器候选、代理登记与实际入口、项目已有的测试与包管理工具，让安装、选型或排障前先读报告，
  避免重复装依赖、凭猜测探测和片面误判环境。
  当任务需要知道本机有什么、准备装依赖或浏览器前先探测、怀疑环境判断不完整、换机器或新环境排查，
  或要复用已有代理入口与测试套件时使用；代理选路转 network-access，浏览器操作转 browser-automation，
  渲染与挑战求解转 resilient-browser-fetch，测试设计转 web-app-testing。
---

# 本机资源体检

安装、选型、排障之前先回答"这台机器现在有什么、哪些能直接用"。报告由各组归属工具实际探测，本 skill 只做聚合与判读，不另写检测规则。

## 适用范围

- 回答本机资源：运行时版本与路径、Python 解释器及可用引擎层、浏览器候选、代理入口、项目已有工具。
- 安装或下载依赖、浏览器、运行时之前的对照；换机器、新环境、怀疑"环境判断不完整"时的第一步。
- 不承担：代理选路与镜像决策（network-access）、浏览器操作与截图（browser-automation）、渲染与挑战求解（resilient-browser-fetch）、测试设计与运行（web-app-testing）。这些细节按组名转对应 skill。

## 使用

```bash
python <skill>/scripts/inventory.py                  # 人类可读，默认不联网
python <skill>/scripts/inventory.py --json           # 机器可读，供 agent 判读
python <skill>/scripts/inventory.py --project .      # 追加项目级工具（可重复）
python <skill>/scripts/inventory.py --only proxies   # 只跑指定分组，省掉无关探测
python <skill>/scripts/inventory.py --probe-proxy    # 代理活体探测（会出网）
```

选项、默认值与降级行为以 `--help` 为准，本文不复制清单。脚本只用标准库，任何 PATH 上的 Python 3.10+ 都能跑；不需要安装依赖。

## 报告怎么读

| 分组 | 看什么 | 关键判据 |
|---|---|---|
| 会话环境 | `VIRTUAL_ENV`、`CONDA_PREFIX`、镜像与 Playwright 路径等 | 说明当前 shell 在哪个环境；与 PATH 上的工具不是一回事 |
| 运行时 | 名称、版本、路径 | 缺失的才需要安装；版本以工具自身输出为准，不按印象判断 |
| Python 环境 | `层`、引擎、已装包 | 层 ≥ 2 才有挑战求解能力；`建议` 取首个层 ≥ 1 的解释器；PATH 上的 `python` 常只有层 1 |
| 浏览器 | `可用/不可用`、来源 | `eligible:false` 多为 shim/wrapper；Playwright 缓存里的 chromium 同样是候选 |
| 代理 | 环境变量、登记条目、`verified` 日期 | 环境变量会直接影响子进程抓取；登记 ≠ 可用；只有 `--probe-proxy` 给可用性与实际出口 |
| 项目 | lockfile、scripts、测试框架、`installed` | lockfile 判定包管理器；`installed` 是已装证据（`node_modules/.bin`、项目虚拟环境包），有就不必重装；文件存在不等于能跑 |

## 约束

- 先读报告再装：同一会话复用一次结果，不逐页重复扫描；报告是否过期看 `generated`。
- 负面证据和正面证据同等重要：包在但层缺、候选不可用、登记日期过旧，都要写进结论，而不是只报"有"。
- 报告只回答"有什么"，不是安装授权。装什么、走哪个镜像或代理按 network-access；需要用户同意时不代装。
- `available:false` 表示兄弟 skill 没链接到同一 harness 或脚本缺失，不等于本机没有该资源；按组名去真源仓库跑对应工具。
- `installed` 只证明文件或包在不在，不证明可运行；真正要用时按归属 skill 做一次最小实跑。
- 结论冲突时以实测为准；历史 `verified` 日期不能当作当前可用性。

## 各组维护位置

| 分组 | 归属 |
|---|---|
| 运行时 | 本脚本（PATH + 各工具 `--version`） |
| Python 环境与引擎层 | [resilient-browser-fetch](../resilient-browser-fetch/SKILL.md) 的 `scripts/check_environment.py` |
| 浏览器 | [browser-automation](../browser-automation/SKILL.md) 的 `scripts/browser_discovery.py` |
| 代理 | [network-access](../network-access/SKILL.md) 的 `scripts/probe_local_proxies.py`、环境变量与 `~/.config/proxy-resources.json` |
| 项目工具 | [web-app-testing](../web-app-testing/SKILL.md)（测试运行器与已装证据）、[swe-gov](../swe-gov/SKILL.md)（工程约定） |

调整检测口径改归属脚本与 skill；不在这里复制规则或选项。

## 自检

- 是否先跑一次报告，再决定安装、选型或下"本机没有"的结论？
- 是否读了 `available:false`、`eligible:false`、缺层等负面证据，而不只看"有"？
- 是否把登记条目、历史核验日期当成了当前可用性？
- 同一会话内，是否重复扫描了同一环境？

## 验证协议

1. `python -X utf8 scripts/inventory.py --json` 退出码 0，各组齐全；缺兄弟 skill 时该组为 `available:false` 且带 `reason`。
2. `python -X utf8 tests/test_inventory.py`（或 `python -m pytest tests`）17 项全部通过。
3. 真实环境抽查一条：报告里的解释器或浏览器路径存在；代理结论与 `--probe-proxy` 结果一致。
