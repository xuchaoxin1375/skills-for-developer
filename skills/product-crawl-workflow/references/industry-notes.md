# 行业来源与取舍

用于支撑 `product-crawl-workflow` 的判断，不把厂商博客当受控基准。来源在 2026-11-19 读取，页面与产品能力会变化，使用前按目标站点复核。

## 发现与覆盖

- 全目录采集的难点是覆盖而不是解析：优先站点地图和 feed，其次分类，最后站内搜索；分页应持续到没有新商品，并按商品 ID 去重，不用固定页数。[Scrapfly](https://scrapfly.io/blog/posts/how-to-scrape-large-product-catalogs)
- 电商任务通常从分类或搜索页开始，经分页进入详情页；试点要检查第二页和最后一页，而不是只看首屏。[Web Scraper](https://webscraper.io/blog/best-web-scraping-tools-ecommerce)
- 站点地图可能不完整或只覆盖部分区段；分类和搜索是补充入口，不能因为某一种入口缺失就判定全站不可采。[AIMultiple](https://aimultiple.com/ecommerce-scraper)

## 获取方式

- 静态 HTTP 与无头浏览器的选择取决于字段是否已在原始响应中；空壳页面需要渲染，已有公开数据接口时优先直接读取。[Ollagraph](https://ollagraph.com/blog/static-fetch-vs-headless-browser-choosing-the-right-web-scraping-strategy)
- 判断方法：查看原始 HTML（View Source）是否含目标数据；在 Network 面板确认数据是否由公开请求返回；原始响应为空壳时才需要浏览器。[DEV Community](https://dev.to/extractdata/how-to-tell-if-a-page-uses-javascript-rendering-and-what-to-do-about-it-5af8)
- 无头浏览器更慢、资源占用更高，也更易被识别；是否升级由目标站点的实际响应决定，不存在通用通过率。[Browserless](https://www.browserless.io/blog/best-headless-browser-for-scraping)、[Tendem](https://tendem.ai/blog/scraping-dynamic-javascript-websites)

## 详情页提取

- 稳定顺序是结构化数据 → 嵌入 JSON → CSS 选择器，并记录实际使用的来源；JSON-LD 可能只覆盖当前变体或只给摘要，必须逐条校验。[Shifter](https://shifter.io/blog/extract-structured-data-json-ld-instead-of-parsing-html)
- JSON-LD 需要确认它出现在原始 HTML 还是渲染后 DOM；商品页优先检查 `Product`／`Offer`，并核对价格、币种和库存的归属。[Web Scraper JSON-LD](https://webscraper.io/blog/extract-json-ld-structured-data)
- JSON-LD 是搜索引擎推荐的格式，但推荐格式不等于字段完整；仍以页面和公开数据为准。[Google Search Central](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data)

## 采用与不采用

采用：

- 发现顺序、分页到无新增、按商品身份去重、记录分母。
- 静态优先、公开 JSON 优先、浏览器按证据升级。
- 结构化数据优先、记录字段来源、区分摘要与完整正文。
- 样本覆盖首尾分页、变体、缺货和异常价格。

不采用：

- 具体厂商的成功率、价格或“通用反爬通过率”数字。
- 默认使用托管抓取 API、住宅代理或验证码服务；这些涉及费用、合规和出口选择，按项目授权另行决定。
- 把某个平台的字段路径写成所有站点通用的固定解析器。
