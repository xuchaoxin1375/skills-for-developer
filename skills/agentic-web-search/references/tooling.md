# 工具与参数参考

本文件汇总面向 Agent 的联网搜索与抓取工具，以及关键参数。文中产品信息主要来自训练知识与两篇联网搜索指南，**使用前请查阅各家当前文档核实**。

## 工具分类与选型

| 类别 | 方案 | 特点 | 国内可用性 |
| --- | --- | --- | --- |
| 面向 LLM 的搜索 API | Tavily | 为 Agent 设计，返回精炼片段，支持搜索深度参数 | 需代理或海外部署 |
| 面向 LLM 的搜索 API | Exa | 神经检索，擅长语义化与“相似页面”发现 | 同上 |
| 通用搜索 API | Brave Search API | 独立索引，有免费额度，支持时效过滤 | 同上 |
| 通用搜索 API | SerpAPI 等 SERP 代理 | 复用主流引擎结果，语法丰富 | 同上 |
| 国内搜索 API | 博查（Bocha）、智谱 Web Search、通义联网搜索 | 中文索引好，国内直连 | 直连可用 |
| 自托管元搜索 | SearXNG | 开源、免费、聚合多引擎、可私有部署 | 可部署在海外 VPS 供国内调用 |
| 页面抓取转 Markdown | Jina Reader（`r.jina.ai/` 前缀）、Firecrawl | 把网页转为 LLM 友好的正文 | Jina 国内可用性较好；Firecrawl 可自托管 |
| 模型厂商内置搜索 | Anthropic 的 web search 工具、OpenAI 的搜索工具、Perplexity Sonar | 省去自建，但可控性较弱 | 需代理 |

**选型权衡**：

- **可控性优先**（需要站点限定、时间过滤、自定义来源分级）：自建 `web_search` 与 `web_fetch` 两件套，底层接 Brave、Tavily 或 SearXNG。
- **省事优先**：直接用模型厂商内置的搜索工具，但要在系统提示词中补上时间锚定与探测查询策略。
- **中文为主**：至少接一路国内搜索 API，否则国内方案与中文社区线索几乎不可见。

## Claude web search 工具

Anthropic API 提供服务端搜索工具，工具类型示例为 `web_search_20250305`。版本号可能已有更新，使用前查阅官方文档。

| 参数 | 含义 | 说明 |
| --- | --- | --- |
| `max_uses` | 单次请求最多搜索几次 | 超出后返回 `max_uses_exceeded` 错误，属硬约束；软性引导靠系统提示词 |
| `allowed_domains` | 只允许这些域名的结果 | 不要带 `https://` 前缀 |
| `blocked_domains` | 屏蔽这些域名 | 与 `allowed_domains` 只能二选一 |
| `user_location` | 本地化搜索结果 | 含 `type`（`approximate`）、`city`、`region`、`country`、`timezone` |

官方文档说明，**何时触发搜索可通过系统提示词引导**：可以鼓励模型多搜，也可以让它倾向直接回答。组织管理员须先在控制台启用该工具。

## Tavily Search API

面向 Agent 的第三方搜索 API，参数丰富，适合自建两件套。

| 参数 | 取值 | 含义 |
| --- | --- | --- |
| `search_depth` | `basic`（默认）、`advanced`、`fast`、`ultra-fast` | 搜索深度；`advanced` 相关性更高但更慢、更贵 |
| `topic` | `general`、`news`、`finance` | 切换索引类别；时效性新闻用 `news` |
| `time_range` | `day`、`week`、`month`、`year` | 从当前日期往前的相对时间范围 |
| `start_date` / `end_date` | 日期字符串，如 `2026-01-01` | 精确的绝对日期区间 |
| `max_results` | 1 到 20，默认 5 | 返回结果数 |
| `chunks_per_source` | 默认 3 | 每个页面返回多少片段，控制阅读深度 |
| `include_raw_content` | 布尔值 | 返回清洗后的全文；需要细读时再开，否则浪费 token |
| `include_domains` / `exclude_domains` | 域名数组 | 域名白名单与黑名单 |
| `auto_parameters` | 布尔值 | 根据查询意图自动配置参数，手动设置的值优先 |

**辨析**：`time_range` 与 `start_date`/`end_date` 都用于限定时间。前者是**相对**范围（“最近一个月”），适合追新；后者是**绝对**区间，适合查某个时间段的历史事件。注意 `time_range` 过滤不能证明发布日期，时效敏感流程仍须核实来源。

**国内方案（需自行核实）**：博查 Web Search API、智谱与通义等平台提供的联网搜索工具，适合在国内网络环境下直接调用、覆盖中文内容。

## 网络环境

生产环境部署在海外服务器时，国外 API 直连即可；国内开发测试环境通常需要本地代理（如 mihomo）。

- Linux / macOS：`export HTTPS_PROXY=http://127.0.0.1:7890`（端口以本机配置为准）
- Windows PowerShell：`$env:HTTPS_PROXY="http://127.0.0.1:7890"`
- Windows CMD：`set HTTPS_PROXY=http://127.0.0.1:7890`

部分 Python HTTP 库对系统代理的读取行为不同，建议在代码中显式传入代理配置。无代理条件下访问 GitHub 原始文件可考虑 gh-proxy 一类镜像前缀（可用性随时变化，需自行核实）。

## 非 ASCII 字符

部分抓取工具对中文页面的编码探测不稳，返回乱码时优先检查 `Content-Type` 与 `<meta charset>`。SearXNG 等自托管方案的中文分词与结果质量依赖所聚合的引擎，宜加入百度、必应等中文源。

## 工具参数设计示意

以下为结构化搜索工具的 JSON Schema 片段，可作为自建工具的起点；字段含义与注意事项见上表。

```json
{
  "name": "web_search",
  "description": "搜索互联网获取最新信息。用于时效敏感问题（版本、价格、新闻、人事）。查询应具体、含关键实体与年份，避免使用'最新'等模糊词。每次会话最多调用8次。",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "2到6个关键词，含具体实体名与时间锚点"},
      "time_range": {"type": "string", "enum": ["day", "week", "month", "year", "any"], "description": "按发布时间过滤，新闻类用week，版本类用year"},
      "include_domains": {"type": "array", "items": {"type": "string"}, "description": "限定站点，如 docs.python.org"},
      "max_results": {"type": "integer", "default": 6}
    },
    "required": ["query"]
  }
}
```

| 字段 | 含义 | 注意点 |
| --- | --- | --- |
| `query` | 检索词 | 过长的自然语言句子在多数引擎上效果差于关键词组合 |
| `time_range` | 发布时间过滤 | 不同供应商参数名不同（`freshness`、`days`、`time_range`），需在工具内适配 |
| `include_domains` | 白名单站点 | 对官方文档类问题极有效，但会漏掉社区线索，宜与无限定查询配合 |
| `max_results` | 返回条数 | 条数越多上下文越脏；宽探测用多，精查用少 |
