# 分阶段策略与效率

目标不是“把所有站跑一遍”，而是每个阶段用最便宜、可验证的证据推进，并在预算内停止。示例来自项目基准站，数字只证明当日样本，不外推全站。

## 阶段默认

| 阶段 | 先做什么 | 证据 | 效率与停止 |
| --- | --- | --- | --- |
| 分诊 | 每个入口 1 个请求：状态、标题、robots 的 `Sitemap:` 行／sitemap、平台与市场 | 403／406／429／挑战、最终 URL | 1 请求／入口；不先开浏览器 |
| 发现 | sitemap／公开 API → HTML 索引／分类 → 分页 | 候选 URL、入口贡献、分母 | 唯一实体 URL／请求；无新身份／预算／部分枚举 |
| 获取 | 含基础字段的静态／JSON／列表 → 详情 → 浏览器 | 字段是否已在响应；请求头与会话 | 请求数／有效商品；404／410／空页／total |
| 提取 | 列表层基础字段优先；详情只补缺 | 字段来源、商品归属 | 字段命中率；模板差异 |
| 校验 | 10–30 个分层样本：基础字段／状态／描述 | 样本矩阵、冲突 | 有效率／部分率；质量阻塞 |
| 效率／停止 | 每有效商品请求数／字节、墙钟、并发 | 实测吞吐 | 到预算／访问边界 |
| 交付 | 证据、部分、复跑 | 来源／日期／出口／停止原因 | 不把样本写成全站 |

3–5 页模板探针只证明字段形状和容器差异，不替代 10–30 个分层样本验收；站点状态仍记“未测／模板证据”，不写成通过。

## 基准站复盘

| 站点 | 分诊／发现 | 获取／提取 | 效率改进 |
| --- | --- | --- | --- |
| sixmoondesigns.com | Shopify；sitemap 568 条／104 商品；`/products.json` 返回 112 商品 | API 1.2MB；52 个多变体、28 个价格区间；198／623 个变体不可售；3 个缺主图、7 个空正文 | 1 请求约 112 商品；商品页 0.84–1.3MB／页，API 明显更省；D01 S4 4 请求／29 有效／14.49s（1 费用项排除）；API 必须带 `?country=US`，否则价格是 CNY |
| javaestate.com | Shopify；sitemap 707；`/products.json` 250／页 | API 918,943 B／250 ≈ 3.7KB／商品；27 个多变体、21 个价格区间；373／859 个变体无 SKU | 707 商品约 3 页、约 2.7MB；直连 429、代理 200，按页退避；D01 S1 试点 30／30，34 请求／116s，独立复跑差异 0 |
| shopthebulkstore.com | sitemap 2,528 条，但仅 2 个 `/catalog/product/view`；分类是主入口；Candy Unwrapped 62 商品 | 商品页 209–230KB；Product JSON-LD 价格／币种／库存／品牌；描述由 overview＋description 两块组成；单位 `per lb` 27、`per oz` 2、`per 12oz. bag` 1；缺货 3 个仍有价 | sitemap 数量不等于商品数；分类＋sitemap；静态解析；S5 33 请求／30 商品／66.67s；保留单位价，不乘包装重量 |
| skatepro.es | sitemap 8,399 条、8,398 个商品形；历史观察 `Crawl-delay: 10`（当前不解析） | 商品页 168KB／1.75s；JSON-LD €19.95、InStock | 全量约 23.3h；列表／抽样优先，详情按需；D01 S2 试点 30／30，34 请求／378s（历史 10s 间隔） |
| tognar.com | 无 sitemap；首页 345KB／899 链接；分类混合 | 商品页 382KB；2 个重复 Product JSON-LD；$70、InStock；可见 $40／$80 干扰 | 分类优先；锚定 canonical／SKU；模板需多样本；不按首个可见价格 |
| BigCommerce（bybebe／tacticalsurplususa） | sitemap：bybebe 6,212 条；tactical 25 个 products 子图、每页 10,000 条 | 商品页 618–679KB／5.6–26.8s（bybebe）、1.01MB／1.3–3.1s（tactical，代理）；Product JSON-LD 3/3；bybebe 价格在 `offers.priceSpecification.price`，tactical 在 `offers.price`；tactical 描述仅在 DOM | 静态解析；主价＋meta；缺货仍有价，状态看 JSON-LD／内嵌 `instock`／`og:availability`；bybebe 单页慢，设超时 |
| 自定义微数据（fr.lennylamb.com） | 历史观察 robots `Crawl-delay: 1`（当前不解析）；`products.xml` 902 条（895 `web_page`／7 `ware`，混编辑页）；分类页 24 个 `product_box` | 商品页 199–210KB；0 JSON-LD；Product 微数据：价格 176.48–197.88 EUR、InStock、SKU／MPN、约 2.4k 字模板描述；`ware/158` 66.85 EUR | 分类页发现优先；解析 microdata；`web_page`／`ware` 两模板；`mpn` 不是公开 URL |
| Shopify 模型店（rcteam.com，FR／EUR） | sitemap 257 条含 products 子图；`products.json` 250 商品／304 变体／45 不可售 | 商品页约 1.0MB／0.54–1.2s；主题 Product JSON-LD；价格 3.50–1075.99 EUR；多变体 AggregateOffer 无 availability；全缺货主题 OutOfStock 与 app InStock 冲突；描述与 `span.description` 一致 | 列表用 `products.json`；变体库存看 variants／option disabled；忽略 app 富摘要块与 149€ 免邮文本 |
| shop.fooddepot.com／afsupermarket.com | 裸 403；US 代理 200；SPA／API；sitemap 19,287 | 列表 API 100／页、total 19,129；描述在 `/details` | 192 个列表请求约 47MB 取基础字段；详情只补描述；sitemap／API 差异留档 |
| partsfornissans.com | CF；Scrapling 75–88s／页、chrome-late 约 40s | JSON-LD 基础字段；描述按 section | 同站会话复用 3 页；只取需要页；不逐页重开浏览器 |
| repairtoolparts.com | HTML `/site-map` 558 型号；分类高扇出 | 30 页 JSON-LD；11 个 `none.jpg`、4 个零价／无 Offer、9 个停售 | 静态解析；30 样本；状态／占位图单独记录 |
| campsaver.com | 挑战页；有头晚接入可放行；`PRESS & HOLD` | 商品页 741KB；Product JSON-LD 1–8 个 offer、USD 24.89–549.95、30 个描述完整、22 个有 differential 选项、6 个 BackOrder；30／30 商品页 `content` | 有头 `chrome-late`；32 次目标请求；pilot 批 3／10／10／7，推荐 3–5；真实标题 + Product JSON-LD 即读，不等图片／networkidle；不重复 headless |
| roco.cc | 挑战页／403 | 未取得内容 | 分类后停止，不反复重试或换引擎 |
| PrestaShop（familidoo.fr） | 首页 167KB／2.16s，6 个 `.html` 商品链接；商品页 232KB／1.38s | 0 JSON-LD；`39,00 € TTC`、En stock、`#description`、og:image | 静态、无浏览器；价格按 locale |
| PrestaShop 颜色变体（familidoo.fr） | Noire／Bleue／Grise／Rouge 各自商品 URL；均自指 canonical、无 selects | 4 页均 89,00 €、En stock；SKU `H1E-*`、GTIN13 各异；描述仅颜色词不同（Grise 误写 Black） | 按型号＋颜色归并为 1 个商品／4 变体；SKU 级导出保留 4 行；颜色以标题／SKU／GTIN 为准 |
| 自定义 object-path（scheufele-modellbau.de） | 首页 149KB／2.28s，36 个 ObjectPath 商品链接 | 直接 GET 商品 URL 返回首页，无商品标记 | 需要会话／JS；记录导航边界 |
| 阻断站（speedshop24／modellparadies／derkum） | 超时／444／403 CF | 未取得内容 | 分类后停止，不反复重试 |

## 效率计算

- sixmoons：1 个 API 请求约 1.2MB／112 商品 ≈ 10.7KB／商品；商品页 0.84–1.3MB／页，112 页约 94–146MB；API 省约 80–120 倍字节。
- javaestate：707／250 = 3 页，约 2.7MB；3 个请求 vs 707 个详情页。
- fooddepot／afsupermarket：19,129／100 = 192 个列表请求；100 条约 246KB，合计约 47MB 基础字段；19,129 个详情页只用于描述，按缺失率决定是否下钻。
- skatepro：8,399 × 10s ≈ 23.3h；按 3,504 个商品计算约 9.7h；全量前先算墙钟，预算不够就收窄。
- partsfornissans：40–88s／页；100 页约 1.1–2.4h；会话复用和按需详情是主要优化。
- shopthebulkstore／tognar／repairtoolparts：静态请求秒级；无浏览器；只取主容器。

## 策略改进

- 首页 1 个请求可筛平台／访问／商品链接；平台标记和首页 JSON-LD 只作线索，商品页模板可能不同（tognar 首页无 Product JSON-LD、商品页有 2 个；PrestaShop 常无 JSON-LD）。
- API／列表一次取多条，详情只补缺；先算每有效商品的请求数和字节数。
- sitemap 数量不等于商品数；分类页或公开 API 可能是主入口，记录入口贡献。
- 分页先读 total；空页或 `skip >= total` 停止；sitemap 与 API total 差异留档，不强行对齐。
- 变体商品：单个零价变体不等于整品零价；取有价变体的最低正价，零价变体单独记录；全部变体零价／无价才按 quote-only 或无效处理。
- 变体也可能是独立商品 URL（颜色／尺寸各一页）；单页没有 selects 不等于无变体，按商品名、属性、父子关系和业务键归并。
- 价格按 locale 解析（`39,00 € TTC`、`206,90 €`）；优先 `product:price:amount`／`itemprop="price"`，否则锚定主价格容器，区分现价与划线价。
- 价格和币种可能按出口 IP／语言／市场路径本地化；构建、主机验证和运行期固定同一出口，换出口后重新抽检，不凭出口国家猜币种。sixmoondesigns 的 `products.json` 明确需要 `?country=US`，否则价格是 CNY；真实构建中本地直连也会得到 CNY。
- ObjectPath／JS 店面的商品链接可能返回首页；记录导航／会话边界，不据此判无商品，也不反复重试同一条链接。
- 客户端和出口差异先比较一个变量；429 退避或换出口，403 先分挑战、地区／IP 与权限。
- 挑战站会话复用、按需页面、有限尝试；不逐页重开浏览器，不反复重试同一条失败路线。
- 按固定保守速率先算墙钟；不解析 `Crawl-delay`。预算不够就收窄范围或降低字段目标，不先提高并发。
- Shopify 可能重复 Product JSON-LD：主题块（带 `@id`／productID）与富摘要 app 块冲突时以主题块 + variants 为准；多变体 AggregateOffer 无 availability 时看 variants／option disabled。
- 描述完整文本可用 `span.description` 或 JSON-LD；宽泛 `.rte` 可能只取到 intro。主价用 meta／JSON-LD／`price-list`，页面其他 € 文本（免邮门槛）不是商品价。
- 3–5 页模板探针只证明模板，不能写成站点通过；站点状态按 10–30 样本验收或明确“未测／模板证据”。
- 框架/运行时选型不改变分阶段原则；候选画像、适用边界与同条件对照底线见 [framework-selection.md](framework-selection.md)。
- 校验用 10–30 个分层样本，覆盖入口、列表、详情、变体、缺货、描述缺失；失败和未测项保留。
- 构建期记录模型 provider／id／思考等级、工具调用、tokens／费用、修订次数和主机验证；trace 默认剥离 reasoning，需要时显式保留并截断。只留最终规则无法判断慢在发现、提取、验证还是修复。

## 自检

- [ ] 是否先分诊再开浏览器，避免为静态页启动浏览器？
- [ ] 是否先找 sitemap／公开 API／列表，而不是直接逐条抓详情？
- [ ] 是否记录了候选数、入口贡献和分母；sitemap 数量没有被当成商品数？
- [ ] 是否按每有效商品请求数／字节数和墙钟评估，而不是只看配置并发？
- [ ] 变体、零价、缺货、占位图和描述缺失是否分别记录？
- [ ] 是否把 3–5 页模板探针误写成站点通过或 10–30 样本验收？
- [ ] 挑战和限流是否在预算内停止，并保留停止原因？
- [ ] 框架选型是否按路径与约束判断，而不是按文档排名、单次演示或不同样本的结果？
