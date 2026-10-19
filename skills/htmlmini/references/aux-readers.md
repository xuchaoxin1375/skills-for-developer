# 第三方与归档辅助路线

本地提取（Defuddle / Trafilatura / UI 清单）与本地渲染（`resilient-browser-fetch`）都拿不到页面时，才考虑这里。按顺序往外走，每往外一步都要说明代价。

## 使用前提

- **先穷尽本地**：静态提取 → `--render` / `resilient-browser-fetch`（有头，必要时 `--real-chrome`）→ 浏览器导出。本地层与出口都没试完就换第三方，等于把没排除的失败当成结论。
- 第三方服务会把目标 URL 交给外部服务器；带有查询参数、内网地址、会话标识的链接**不上传**。需要登录态的页面走本地浏览器导出。
- 属于对外部服务的依赖与成本（额度、限流、隐私），使用前告知用户并取得同意；结果里注明来源、取回时间与实际出口。
- 不自动翻页、不批量轰炸；同时遵守目标站点与所调服务的条款。

## 顺序与做法

1. **浏览器导出（无第三方，优先）**

   自己的浏览器能打开页面时：`Ctrl+S` 保存完整 HTML，或 DevTools → Elements → 复制 `<html>` 外层 HTML 存成文件，再用 `htmlmini_extract_file` 提取；PDF 交给 `markitdown`。适合一次性页面、需要登录态或人机验证后的页面。

2. **开源自托管（自己出网，数据不经第三方）**

   | 工具 | 许可 | 做法 |
   | --- | --- | --- |
   | Crawl4AI | Apache-2.0 | `pip install -U crawl4ai && crawl4ai-setup`，再用 `AsyncWebCrawler().arun(url)` 取 `result.markdown`；可接本机代理与浏览器 profile |
   | Firecrawl | AGPL-3.0 | 支持 Docker 自托管；用于自己的服务端时注意 AGPL 义务 |

   自托管的代价是浏览器与依赖，收益是出口、代理和 profile 都由自己控制，和本地渲染路线一致。

3. **托管 reader 服务（需用户同意）**

   | 服务 | 免费额度（2026-10-20 核验） | 适合 | 注意 |
   | --- | --- | --- | --- |
   | Jina Reader `r.jina.ai` | 不带 Key 20 RPM（按 IP）；注册 Key 赠 1000 万 token，之后按输出 token 计费 | 单页转 Markdown、PDF、指定选择器或自带代理 | 同一 URL 5 分钟缓存；失败请求不扣费；付费**不解锁**被拦站点，也不主动绕过反爬 |
   | Crawl4AI Cloud | 每月 1000 credits，10 次/分钟、2 并发 | 需要 JS 渲染或多页抓取又不想自己跑浏览器 | 软启动期定价可能调整，用前核对 |
   | Wayback Machine | 快照读取免费；Save Page Now 需登录且有限额 | 取历史版本、绕开当前拦截 | 只反映归档时刻，不等于当前页面 |

   ```bash
   curl -s 'https://r.jina.ai/https://example.com/product' | head -50
   curl -s 'https://archive.org/wayback/available?url=example.com'
   ```

   Jina 的常用请求头：`X-Target-Selector` / `X-Remove-Selector`（只留或去掉指定节点）、`X-Retain-Links`、`X-Timeout`、`X-Proxy-Url`（用你自己的代理）；带 cookie 的请求不缓存。

4. **结果处理**：第三方返回的是别人的清洗产物，字段覆盖可能少于本地（例如分页表格只给首屏）。与页面结构化数据或接口交叉核对，取不到的字段如实说明，不补写。

## 不适合

- 需要登录态、支付或后台操作的页面。
- 高频采集和生产链路（额度、限流与合规风险都在对方手里）。
- 用第三方结果替代本地可验证的取数：价格、库存一类易变字段应以页面自身数据为准。
