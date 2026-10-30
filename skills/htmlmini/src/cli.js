#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { ATTR_POLICIES, ATTR_POLICY_DESCRIPTIONS, EXTRACTORS, EXTRACTOR_DESCRIPTIONS, FORMAT_POLICIES, FORMAT_POLICY_DESCRIPTIONS, MODES, MODE_DESCRIPTIONS, RENDER_ENGINE_CHOICES, RENDER_ENGINE_DESCRIPTIONS, runExtractDetailed } from './extract.js';
import { fmtBytes, fmtMs, log, setLogLevel } from './log.js';
import { markSource, padPayload } from './output.js';
import { VERSION, VERSION_LINE } from './version.js';

/** 取值清单统一从这里生成：帮助文本、--list-* 输出与实现共用一份，避免互相脱节。 */
const modeList = () => MODES.map((m) => `  ${m.padEnd(12)}${MODE_DESCRIPTIONS[m] ?? ''}`).join('\n');
const engineList = () => RENDER_ENGINE_CHOICES.map((e) => `  ${e.padEnd(12)}${RENDER_ENGINE_DESCRIPTIONS[e] ?? ''}`).join('\n');
const attrList = () => ATTR_POLICIES.map((a) => `  ${a.padEnd(12)}${ATTR_POLICY_DESCRIPTIONS[a] ?? ''}`).join('\n');
const formatList = () => FORMAT_POLICIES.map((f) => `  ${f.padEnd(12)}${FORMAT_POLICY_DESCRIPTIONS[f] ?? ''}`).join('\n');
/** 环境变量清单：帮助文本与 --list-env 共用一份。 */
const ENV_HELP = [
  'HTMLMINI_PYTHON             save_page/Trafilatura 用的解释器（等价 --python-bin）',
  'HTMLMINI_CHROME_BIN         零依赖 Chrome 的可执行文件路径',
  'HTMLMINI_CHROME_EXTRA_ARGS  追加给 Chrome 的启动参数（空格分隔）',
  'HTMLMINI_RENDER_SCRIPT      自备 save_page 脚本路径（自建渲染器/测试用）',
  'HTMLMINI_RENDER_ENGINES     限定可用的渲染引擎集合',
  'HTMLMINI_ENV_SCAN=0         关闭"渲染失败后扫描更强解释器重试"这一步',
  'HTMLMINI_ENV_SCAN_SCRIPT    自备环境扫描脚本路径',
  'HTMLMINI_PROXY_REGISTRY     代理登记文件路径（默认 ~/.config/proxy-resources.json；'
    + '只读不改，仅用于在报错里提示可用代理）',
  'HTMLMINI_LOG=quiet|info|debug 日志级别',
  'HTMLMINI_LOG_TIME=0         去掉日志行首时间戳',
  'HTMLMINI_SOURCE_MARKS=1     输出来源哨兵行（HTML 注释风格，默认关）',
];

/**
 * 短版帮助（默认）：一屏内看完——简介、用法、来源、输出模式、常用选项、完整版入口。
 * 完整选项、取值说明、环境变量、退出码、示例与症状表在 --help full。
 * 两版共用同一份清单生成函数，内容不许分叉（tests/reliability.mjs 有守卫断言）。
 */
const HELP_BRIEF = `htmlmini ${VERSION} - 剥掉 CSS/JS 与样板，只留核心正文（Markdown/JSON，省 token）

用法 (USAGE)
  htmlmini [来源] [选项]
  来源：本地 HTML 文件 | http(s) 地址 | -（stdin，默认）

输出模式 (--mode，或对应短选项)
${modeList()}

常用选项
  -m, --markdown / -j, --json / -s, --skeleton / -u, --ui / -t, --text / -T, --title
  --mode <名称>              输出模式，见上表
  --extractor <名称>         抽取引擎：auto | defuddle | trafilatura | semantic | ui | sanitize | passthrough
  -r, --render[=auto|always] 浏览器渲染回退：auto 只在静态 403/5xx 时回退；always 静态 200 也渲染
  -e, --render-engine <名称> 钉住渲染引擎：auto | playwright | scrapling | cloak-cdp | chrome-late | nodriver
  -b, --browser-brand <品牌> 渲染用浏览器品牌：auto | chrome | edge | chromium（默认 auto）
  --cdp-url <地址>           接管你已开着的浏览器（复用它的 cookie/放行凭据），只读已渲染 DOM
  -p, --proxy <地址>         抓取代理：http(s) 地址，或 direct 绕过环境代理
  --save-html <文件>         落盘实际使用的 HTML（配兄弟 .meta.json），便于换模式复用
  --expect-text <文本>       断言最终 HTML 含该文本（可重复）；缺失直接失败，不交"空壳"结果
  --wait-selector <选择器>   渲染时等该 CSS 选择器可见（需 save_page 通路）
  --output <文件>            结果写文件而不是 stdout
  --allow-empty              保留"像应用壳"的结果（默认报错并提示 --render=always）
  --quiet / --verbose        日志静音 / 详细日志

更多
  --help full                完整选项、取值说明、环境变量、退出码、示例与常见症状
  --list-modes / --list-extractors / --list-render-engines / --list-env
  -V, --version              版本号（YYYY.MM.DD.HHmm）

例子
  htmlmini page.html
  htmlmini page.html --json
  htmlmini "https://example.com/spa" --render=always
  htmlmini "https://example.com/item" --render=always --render-engine chrome-late --proxy http://127.0.0.1:<port>
`;

/** 完整版帮助：选项全表 + 取值说明 + 环境变量 + 退出码 + 示例 + 常见症状与对策。 */
const HELP = `htmlmini ${VERSION} - 剥掉 CSS/JS 与样板，只留核心正文（Markdown/JSON，省 token）
（完整版；短版见 --help）

用法 (USAGE)
  htmlmini [来源] [选项]

来源 (SOURCE)
  <文件>            本地 HTML 文件。旁边的 "<文件>.meta.json" 会自动被用来还原页面 URL
                    （例如 resilient-browser-fetch save_page 落盘的文件）
  <http(s) 地址>    抓取 URL 并提取正文（Defuddle + schema.org 元数据）
  -                 从 stdin 读 HTML（默认）

输出模式 (--mode，或对应短选项)
${modeList()}

渲染引擎 (--render-engine，仅 --render 时有意义)
${engineList()}

选项 (OPTIONS)
  取值型
    --mode <名称>              输出模式，见上表；显式写法，适合脚本与 agent
    --extractor <名称>         抽取引擎：auto | defuddle | trafilatura | semantic | ui | sanitize | passthrough
    --attrs <策略>             仅 --mode html：属性策略 none | semantic | all（默认 semantic）
    --format <策略>            仅 --mode html：排版策略 raw | compact | pretty（默认 compact）
    --text-max <n>             仅 --mode ui / --extractor ui：单条文本的字符上限（默认 150，0 = 不限）
    -r, --render[=auto|always] 浏览器渲染回退。auto（默认）只在静态 403/5xx 时回退；
                               always 则静态 200 也渲染（-r always 同义）。渲染链：save_page
                               （需层 >= 1 引擎）→ 系统 Chrome 无头 dump-dom（零依赖）→ 友好报错
    -e, --render-engine <名称> 钉住 save_page 的引擎（见上表）。显式即严格：只跑这一层，
                               缺件直接报错、不再自动升档
    --cdp-url <地址>           接管你已开着的浏览器（如 --remote-debugging-port 启动的
                               Chrome/Edge），复用它自己的 profile/cookie/放行凭据，只读已
                               渲染的 DOM，不会关闭它。给了它就走 save_page 的接管路线
    --render-timeout-ms <毫秒> 渲染超时上限（默认 300000；chrome dump-dom 上限 120000）
    --chrome-bin <路径>        渲染用的浏览器可执行文件（默认自动探测）。零依赖 Chrome 直渲
                               与 save_page 渲染（chrome-late 等）都用它；显式指定时
                               晚接入引擎会拉起这个浏览器，而不是默认的 Chrome——
                               WAF 可能按客户端品牌判负（实测同一出口 Chrome 被拒、
                               Edge 放行），此时指定 Edge 路径即可放行
    -b, --browser-brand <品牌> 渲染用浏览器品牌偏好：auto（默认，Chrome→Edge→Chromium）|
                               chrome | edge | chromium。不用自己写路径，渲染脚本按品牌
                               找已安装的浏览器（Windows 先查注册表 App Paths）；边缘封禁
                               按客户端品牌判时用它换品牌。点名品牌是严格语义：该品牌没装
                               就报错，不会静默换用别的浏览器（与 --chrome-bin 同时给时
                               路径优先）
    --python-bin <路径>        save_page 与 Trafilatura 用的解释器；"auto" = 扫描本机挑一个
                               装了引擎的（conda/venv/uv/PATH）
    -p, --proxy <地址>         抓取代理：http(s) 地址，或 direct 表示绕过环境代理
                               （默认跟随 HTTP_PROXY/HTTPS_PROXY/NO_PROXY）
    --save-html <文件>         把实际用于抽取的 HTML 落盘到这个文件，并写一份兄弟
                               "<文件>.meta.json"（含页面 URL）。之后换模式读这份文件即可，
                               不用再抓一次或再渲染一次。仅 URL 输入有效；内容是原始 HTML
                               （不是 --mode html 的清理结果），且在校验之前写盘，
                               所以挑战空壳/空页报错时原文也留得下来
    --expect-text <文本>       断言最终 HTML 必须包含该文本（可重复，全部命中才算成功）。
                               缺失时直接报错，不把"渲染成功但没有目标块"当成结果；
                               静态抓取与渲染后都会校验，渲染时同时透传给 save_page，
                               让它按引擎升档而不是提前交差。用于下拉清单、商品名、
                               价格这类"有没有真的抓到"的判据。命中了但当前模式的
                               输出里没有（控件值/清单常被剔除）会提示换 --mode html
                               或 --save-html，不让人误以为抓取失败
    --wait-selector <选择器>   渲染时等该 CSS 选择器可见再取 DOM（save_page 通路的
                               playwright / scrapling / chrome-late 等；零依赖 chrome
                               dump-dom 没有等待钩子，给了它会改用 save_page）。
                               等的是"可见"：闭合 <select> 里的 <option> 没有布局，
                               等它会等到超时；改等容器并加 :has(option)，或用
                               断言文本代替
    --post-wait-ms <毫秒>      取 DOM 前额外等待（save_page 默认 1000）；数据在 load
                               之后才到的页面用它补齐，与 --wait-selector 一起用更稳
    -o, --output <文件>        结果写文件而不是 stdout（文件末尾恰好一个换行；
                               比 shell 管道更稳，管道可能多出空行）
    --completion <shell>       打印补全脚本：bash | powershell
    （以上取值型选项都接受 --opt=value 写法）
  开关型
    -m, --markdown             输出 Markdown（默认）
    -j, --json                 输出 JSON：title / used / requested / version / content / stats / meta
    -s, --skeleton             只出大纲：标题层级、表格、代码块语言
    -u, --ui                   强制界面组件清单（标签/按钮/输入/表格）
    -t, --text                 纯文本，不带标记
    -T, --title                只打印页面标题
    --render-always            等价 --render=always
    --headful                  渲染时弹出真实浏览器窗口（只影响"要不要开窗"，
                               不改变"什么时候渲染"；需 save_page 通路，用于首次人工验证）
    --compact / --pretty       --format compact / pretty 的简写
    --prune-empty              仅 --mode html：顺带删掉清理后变空的容器
                               （空 div/span/nav/header…；table/form/pre 结构保留）
    --allow-empty              保留"像客户端渲染壳"的结果（正文 < 200 字符且 HTML >= 5 KB）。
                               默认报错并提示改用 --render=always
    --keep-options[=list|html]
                               正文模式（markdown/text/skeleton）末尾追加"## 表单选项"：
                               下拉框/optgroup/datalist/单选多选的选项按页面顺序列出。
                               默认 list 只写显示文本（文本为空才用 value）；html 把下拉框
                               写成真正的 <select>（保留 value/selected，查看器支持表单控件
                               时才有交互）；都不截断
    --keep-details             把正文里被压平的 <details> 原位包回 HTML（FAQ/手风琴页）。
                               需能在正文里定位到该段并比对成功，否则保持纯文本
    --noproxy                  强制直连，忽略环境代理
    --quiet                    只输出错误（进度日志静音）
    --verbose                  额外细节：解析/抽取内部信息、耗时、体积
    --source-marks             输出来源哨兵行：HTML 注释风格，包住载荷并写明
                               url / 状态码 / 抓取方式 / 时刻；默认关（别名 --marks）
    --no-source-marks          显式关闭来源哨兵行（默认即关；别名 --no-marks）
    --list-modes               列出输出模式与说明
    --list-extractors          列出抽取引擎与说明
    --list-render-engines      列出渲染引擎与说明
    --list-env                 列出环境变量与说明
    -h, --help                 显示短版帮助（默认）；--help full 给完整版
    -V, --version              打印版本号（日期时间式 YYYY.MM.DD.HHmm）

  --attrs 取值
${attrList()}
  --format 取值
${formatList()}

环境变量 (ENVIRONMENT)
${ENV_HELP.map((line) => `  ${line}`).join('\n')}
  （--list-env 单独打印这份清单）

退出码 (EXIT CODES)
  0  成功
  1  抓取或抽取失败（原因写在 stderr）
  2  参数错误

示例 (EXAMPLES)
  # 1) 本地文件 → Markdown（默认模式）
  htmlmini page.html

  # 2) 看元数据、实际用了哪个抽取器、省了多少 token
  htmlmini page.html --json

  # 3) 界面/仪表盘：强制组件清单，长段落不截断
  htmlmini dashboard.html --mode ui --text-max 0

  # 4) 要结构而不是摘要：清理后的 HTML，保留 DOM 顺序
  htmlmini page.html --mode html --attrs semantic
  htmlmini page.html --mode html --attrs none --prune-empty    # 最小结构骨架

  # 5) 远程 SPA：静态 200 但正文要水合 → 强制渲染
  htmlmini "https://example.com/spa" --render=always

  # 6) 走代理抓（国内网络，或站点只放行特定出口；端口按本机登记的代理填）
  htmlmini "https://example.com/item" --proxy http://127.0.0.1:<port>

  # 7) 挑战站点：普通浏览器能开、自动化全被拦 → 钉晚接入引擎
  htmlmini "https://example.com/item" --render=always --render-engine chrome-late --proxy http://127.0.0.1:<port>

  # 8) 渲染一次、多个视图复用同一份快照（不再联网）
  htmlmini "https://example.com/app" --render=always --save-html app.html
  htmlmini app.html --mode ui
  htmlmini app.html --mode json

  # 9) 管道与输出控制
  cat page.html | htmlmini - --text
  htmlmini page.html --output out.md --quiet
  htmlmini "https://example.com/app" --source-marks --mode markdown  # 加一行来源注释

  # 10) 异步清单 / 下拉框：等目标块出现，并断言真的抓到（缺了直接失败）
  htmlmini "https://example.com/list" --render=always \
    --wait-selector '#list li' --expect-text '<清单里必有的文本>'

  # 11) 与 resilient-browser-fetch 配合（渲染产物 + 兄弟 .meta.json 会被自动利用）
  python ../resilient-browser-fetch/scripts/resilient_fetch.py --url "https://example.com/app" --out app.html --engine chrome-late
  htmlmini app.html --json

  # 12) 表单可选项与折叠块：正文模式不收控件值，details 会被压平
  htmlmini "https://example.com/tool" -m --keep-options         # 追加列表（只写显示文本）
  htmlmini "https://example.com/tool" -m --keep-options=html    # 下拉框写成真正的 <select>
  htmlmini "https://example.com/faq" -m --keep-details          # details 原位包回 HTML

常见症状与对策 (TROUBLESHOOTING)
  403（静态抓取）             → 加 --render（只在 403/5xx 时回退渲染）。
                               仍被拒说明站点按出口封禁，见下一条。
  "Access Denied" 拒绝页      → 站点直接拒绝了这次请求，不是"内容少"。换出口/代理，或改用
                               --render-engine chrome-late；别把它当正文交出去。
                               同一出口 Chrome 被拒而 Edge 放行时，用
                               --chrome-bin "<Edge 路径>" 换客户端品牌。
  正文只有几十字、像应用壳     → 加 --render=always 让页面水合；确实没内容再加 --allow-empty 保留。
  渲染后仍是挑战页            → 换求解引擎：--python-bin auto（scrapling/cloak-cdp），
                               或 --render-engine chrome-late（先让挑战跑完再接入）。
  渲染超时                    → 调大 --render-timeout-ms；客户端渲染的站点常要 30~60 s。
   提取结果太多/太少           → 换 --mode 或 --extractor；用 --json 的 used 确认实际引擎。
  中文乱码                    → 输出是 UTF-8：文件与 --output 不受影响；控制台显示乱码多半是
                               Windows 旧代码页（chcp 936），先 chcp 65001；被 shell 重定向的
                               内容会按控制台代码页二次编码，需要保真就按字节落盘。

MCP 工具 (MCP)
  htmlmini_extract_file(path) / htmlmini_extract_url(url) / htmlmini_extract_html(html_content)
  参数名是 snake_case（proxy / render / render_engine / save_html / render_timeout_ms…），
  语义与上面同名选项一致；render 取 false | true | "always"。
`;

const MODE_FLAGS = {
  '-m': 'markdown',
  '--markdown': 'markdown',
  '-j': 'json',
  '--json': 'json',
  '-s': 'skeleton',
  '--skeleton': 'skeleton',
  '-u': 'ui',
  '--ui': 'ui',
  '-t': 'text',
  '--text': 'text',
  '-T': 'title',
  '--title': 'title',
};

function splitEq(arg) {
  const i = arg.indexOf('=');
  return i < 0 ? [arg, null] : [arg.slice(0, i), arg.slice(i + 1)];
}

async function printCompletion(shell) {
  const file = shell === 'bash' ? '../completions/htmlmini.bash' : shell === 'powershell' ? '../completions/htmlmini.ps1' : null;
  if (!file) {
    log.error(`unknown shell "${shell}" (use: bash | powershell)`);
    process.exit(2);
  }
  process.stdout.write(await readFile(new URL(file, import.meta.url), 'utf8'));
  process.exit(0);
}

const argv = process.argv.slice(2);
/** 浏览器品牌取值：与 resilient-browser-fetch 的 --browser-brand 保持一致。 */
const BROWSER_BRANDS = ['auto', 'chrome', 'edge', 'chromium'];
/**
 * 短选项 → 长选项。长选项是主名（可读、写在文档与补全里），短选项是高频开关的
 * 便利层：条件允许就同时给，冲突或含义会歧义时宁可不加。
 * 这里只做一次规范化，后面参数解析只认长选项。
 */
const SHORT_ALIASES = {
  '-p': '--proxy',
  '-b': '--browser-brand',
  '-e': '--render-engine',
  '-r': '--render',
};
/** `-r` 的可选取值：给就带上，不给就是"仅 403/5xx 时回退渲染"。 */
const RENDER_VALUES = new Set(['auto', 'always']);
let source = '-';
let mode = 'markdown';
let extractor = 'auto';
let output = null;
let proxy;
let render = false;
let renderTimeoutMs;
let headful = false;
let chromeBin;
let browserBrand;
let pythonBin;
let saveHtml;
let renderEngine;
let cdpUrl;
let expectTexts = [];
let waitSelector;
let postWaitMs;
let attrs = 'semantic';
let format = 'compact';
let pruneEmpty = false;
let textMax = 150;
let allowEmpty = false;
let keepOptions = false;
let keepDetails = false;
let logLevelOverride = null;
// 来源哨兵行：默认关（HTML 注释风格）。显式 `--source-marks` 或 HTMLMINI_SOURCE_MARKS=1 才加。
let sourceMarks = process.env.HTMLMINI_SOURCE_MARKS === '1';

for (let i = 0; i < argv.length; i++) {
  let a = argv[i];
  // 短选项先归一成长选项（-r 允许带可选值：-r always）。
  if (SHORT_ALIASES[a]) {
    const long = SHORT_ALIASES[a];
    if (long === '--render' && RENDER_VALUES.has(argv[i + 1])) {
      argv[i] = `${long}=${argv[i + 1]}`;
      argv.splice(i + 1, 1);
    } else {
      argv[i] = long;
    }
    a = argv[i];
  }
  if (a === '-h' || a === '--help' || a.startsWith('--help=')) {
    // 默认短版（一屏看完），"--help full" 给完整版。
    // 完整版入口要显眼：短版末尾就写着它。
    let want = 'brief';
    if (a.startsWith('--help=')) want = a.slice('--help='.length) === 'full' ? 'full' : 'brief';
    else if (argv[i + 1] === 'full' || argv[i + 1] === 'brief') {
      want = argv[i + 1];
      i += 1;
    }
    process.stdout.write(want === 'full' ? HELP : HELP_BRIEF);
    process.exit(0);
  } else if (a === '-V' || a === '--version') {
    process.stdout.write(`${VERSION_LINE}\n`);
    process.exit(0);
  } else if (a === '--list-modes') {
    // 名字 + 一句说明：只给名字的话，调用方还得回头查文档才知道该选哪个
    process.stdout.write(`${modeList()}\n`);
    process.exit(0);
  } else if (a === '--list-extractors') {
    process.stdout.write(`${EXTRACTORS.map((e) => `  ${e.padEnd(13)}${EXTRACTOR_DESCRIPTIONS[e] ?? ''}`).join('\n')}\n`);
    process.exit(0);
  } else if (a === '--list-render-engines') {
    process.stdout.write(`${engineList()}\n`);
    process.exit(0);
  } else if (a === '--list-env') {
    process.stdout.write(`${ENV_HELP.map((line) => `  ${line}`).join('\n')}\n`);
    process.exit(0);
  } else if (a === '-o' || a === '--output') {
    output = argv[++i];
    if (!output) {
      log.error('--output needs a file argument');
      process.exit(2);
    }
  } else if (a === '--mode' || a === '--extractor' || a === '--attrs' || a === '--format' || a === '--completion' || a === '--proxy' || a === '--chrome-bin' || a === '--browser-brand' || a === '--python-bin' || a === '--save-html' || a === '--render-engine' || a === '--cdp-url') {
    const v = argv[++i];
    if (!v) {
      log.error(`${a} needs a value`);
      process.exit(2);
    }
    if (a === '--mode') mode = v;
    else if (a === '--extractor') extractor = v;
    else if (a === '--attrs') attrs = v;
    else if (a === '--format') format = v;
    else if (a === '--proxy') proxy = v;
    else if (a === '--chrome-bin') chromeBin = v;
    else if (a === '--browser-brand') {
      if (!BROWSER_BRANDS.includes(v)) {
        log.error(`--browser-brand needs one of ${BROWSER_BRANDS.join(' | ')} (got "${v}")`);
        process.exit(2);
      }
      browserBrand = v;
    }
    else if (a === '--python-bin') pythonBin = v;
    else if (a === '--save-html') saveHtml = v;
    else if (a === '--render-engine') renderEngine = v;
    else if (a === '--cdp-url') cdpUrl = v;
    else await printCompletion(v);
  } else if (a === '--expect-text') {
    const v = argv[++i];
    if (!v) {
      log.error('--expect-text needs a value');
      process.exit(2);
    }
    expectTexts.push(v);
  } else if (a.startsWith('--expect-text=')) {
    const [, v] = splitEq(a);
    if (!v) {
      log.error('--expect-text needs a value');
      process.exit(2);
    }
    expectTexts.push(v);
  } else if (a === '--wait-selector') {
    const v = argv[++i];
    if (!v) {
      log.error('--wait-selector needs a CSS selector');
      process.exit(2);
    }
    waitSelector = v;
  } else if (a.startsWith('--wait-selector=')) {
    const [, v] = splitEq(a);
    if (!v) {
      log.error('--wait-selector needs a CSS selector');
      process.exit(2);
    }
    waitSelector = v;
  } else if (a === '--post-wait-ms') {
    const v = argv[++i];
    postWaitMs = Number(v);
    if (!Number.isFinite(postWaitMs) || postWaitMs < 0) {
      log.error(`--post-wait-ms needs a number >= 0 (got "${v ?? ''}")`);
      process.exit(2);
    }
  } else if (a.startsWith('--post-wait-ms=')) {
    const [, v] = splitEq(a);
    postWaitMs = Number(v);
    if (!Number.isFinite(postWaitMs) || postWaitMs < 0) {
      log.error(`--post-wait-ms needs a number >= 0 (got "${v ?? ''}")`);
      process.exit(2);
    }
  } else if (a === '--compact') {
    format = 'compact';
  } else if (a === '--pretty') {
    format = 'pretty';
  } else if (a === '--prune-empty') {
    pruneEmpty = true;
  } else if (a === '--text-max') {
    const v = argv[++i];
    textMax = Number(v);
    if (!Number.isFinite(textMax) || textMax < 0) {
      log.error(`--text-max needs a number >= 0 (0 = no limit), got "${v ?? ''}"`);
      process.exit(2);
    }
  } else if (a.startsWith('--text-max=')) {
    const [, v] = splitEq(a);
    textMax = Number(v);
    if (!Number.isFinite(textMax) || textMax < 0) {
      log.error(`--text-max needs a number >= 0 (0 = no limit), got "${v ?? ''}"`);
      process.exit(2);
    }
  } else if (a === '--allow-empty') {
    allowEmpty = true;
  } else if (a === '--keep-options' || a === '--keep-options=list' || a === '--keep-options=html') {
    // 可选值只认 `=` 形式：空格形式会把下一个参数（通常是输入路径）当值吞掉。
    keepOptions = a === '--keep-options=html' ? 'html' : 'list';
  } else if (a.startsWith('--keep-options=')) {
    log.error(`--keep-options 取值只能是 list 或 html，got "${a.slice('--keep-options='.length)}"`);
    process.exit(2);
  } else if (a === '--keep-details') {
    keepDetails = true;
  } else if (a === '--no-source-marks' || a === '--no-marks') {
    sourceMarks = false;
  } else if (a === '--source-marks' || a === '--marks') {
    sourceMarks = true;
  } else if (a === '--quiet') {
    logLevelOverride = 'quiet';
  } else if (a === '--verbose') {
    logLevelOverride = 'debug';
  } else if (a === '--noproxy') {
    proxy = 'direct';
  } else if (a === '--render') {
    render = true;
  } else if (a === '--render-always') {
    render = 'always';
  } else if (a.startsWith('--render=')) {
    const [, v] = splitEq(a);
    if (v !== 'always' && v !== 'auto') {
      log.error(`--render accepts "auto" or "always" (got "${v}")`);
      process.exit(2);
    }
    render = v === 'always' ? 'always' : true;
  } else if (a === '--headful') {
    headful = true;
    // 只升级、不降级: --headful 跟在 --render=always 后面时不能把"总是渲染"降回"仅 403/5xx 回退"
    render = render === 'always' ? 'always' : true;
  } else if (a === '--render-timeout-ms') {
    const v = argv[++i];
    renderTimeoutMs = Number(v);
    if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
      log.error(`--render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
      process.exit(2);
    }
  } else if (a.startsWith('--mode=') || a.startsWith('--extractor=') || a.startsWith('--attrs=') || a.startsWith('--format=') || a.startsWith('--output=') || a.startsWith('--completion=') || a.startsWith('--proxy=') || a.startsWith('--chrome-bin=') || a.startsWith('--browser-brand=') || a.startsWith('--python-bin=') || a.startsWith('--save-html=') || a.startsWith('--render-engine=') || a.startsWith('--render-timeout-ms=') || a.startsWith('--cdp-url=')) {
    const [k, v] = splitEq(a);
    if (k === '--mode') mode = v;
    else if (k === '--extractor') extractor = v;
    else if (k === '--attrs') attrs = v;
    else if (k === '--format') format = v;
    else if (k === '--output') output = v;
    else if (k === '--proxy') proxy = v;
    else if (k === '--chrome-bin') chromeBin = v;
    else if (k === '--browser-brand') {
      if (!BROWSER_BRANDS.includes(v)) {
        log.error(`--browser-brand needs one of ${BROWSER_BRANDS.join(' | ')} (got "${v}")`);
        process.exit(2);
      }
      browserBrand = v;
    }
    else if (k === '--python-bin') pythonBin = v;
    else if (k === '--save-html') saveHtml = v;
    else if (k === '--render-engine') renderEngine = v;
    else if (k === '--cdp-url') cdpUrl = v;
    else if (k === '--render-timeout-ms') {
      renderTimeoutMs = Number(v);
      if (!Number.isFinite(renderTimeoutMs) || renderTimeoutMs <= 0) {
        log.error(`--render-timeout-ms needs a positive number of ms (got "${v ?? ''}")`);
        process.exit(2);
      }
    } else await printCompletion(v);
  } else if (MODE_FLAGS[a]) {
    mode = MODE_FLAGS[a];
  } else if (a === '-' || !a.startsWith('-')) {
    source = a;
  } else {
    log.error(`unknown option "${a}" (see --help)`);
    process.exit(2);
  }
}

if (!MODES.includes(mode)) {
  log.error(`unknown mode "${mode}" (see --list-modes)`);
  process.exit(2);
}
if (!EXTRACTORS.includes(extractor)) {
  log.error(`unknown extractor "${extractor}" (see --list-extractors)`);
  process.exit(2);
}
if (!ATTR_POLICIES.includes(attrs)) {
  log.error(`unknown --attrs policy "${attrs}" (use: ${ATTR_POLICIES.join(' | ')})`);
  process.exit(2);
}
if (renderEngine !== undefined && !RENDER_ENGINE_CHOICES.includes(renderEngine)) {
  log.error(`unknown --render-engine "${renderEngine}" (use: ${RENDER_ENGINE_CHOICES.join(' | ')}) — static/scrapling-cli are not render engines`);
  process.exit(2);
}
if (!FORMAT_POLICIES.includes(format)) {
  log.error(`unknown --format policy "${format}" (use: ${FORMAT_POLICIES.join(' | ')})`);
  process.exit(2);
}
if (logLevelOverride) setLogLevel(logLevelOverride);

// 终端裸跑（无管道、无文件参数）会无限等 stdin：直接给提示而不是挂起。
if (source === '-' && process.stdin.isTTY) {
  log.error('no input (stdin is a terminal). Give a file, a URL, or pipe HTML via stdin. See --help.');
  process.exit(2);
}

// 哨兵行与终端留白都在 output.js（纯函数，单测直接覆盖）；这里只决定用哪种：
// `--json` 不掺任何外围内容，管道/重定向保持纯载荷。

try {
  const startedAt = Date.now();
  const { output: raw, info } = await runExtractDetailed(source, mode, { extractor, attrs, format, pruneEmpty, textMax, allowEmpty, ...(proxy === undefined ? {} : { proxy }), ...(render ? { render } : {}), ...(renderTimeoutMs === undefined ? {} : { renderTimeoutMs }), ...(headful ? { headful: true } : {}), ...(chromeBin === undefined ? {} : { chromeBin }), ...(browserBrand === undefined ? {} : { browserBrand }), ...(pythonBin === undefined ? {} : { pythonBin }), ...(renderEngine === undefined ? {} : { renderEngine }), ...(cdpUrl === undefined ? {} : { cdpUrl }), ...(saveHtml === undefined ? {} : { saveHtml }), ...(expectTexts.length ? { expectTexts } : {}), ...(waitSelector === undefined ? {} : { waitSelector }), ...(postWaitMs === undefined ? {} : { postWaitMs }), ...(keepOptions ? { keepOptions } : {}), ...(keepDetails ? { keepDetails: true } : {}) });
  // JSON 模式不包哨兵行（否则不再可解析），来源由 JSON 里的 source/fetchStatus/fetchedAt 字段承载。
  const out = mode === 'json' || !sourceMarks ? raw : markSource(raw, info);
  const total = `total ${fmtMs(Date.now() - startedAt)}`;
  if (output) {
    // 与 stdout 分支同口径：结果已以换行结尾时不再补，避免落盘文件尾部多出空行。
    await writeFile(output, out.endsWith('\n') ? out : out + '\n', 'utf8');
    log.info('write', `${output} ${fmtBytes(Buffer.byteLength(out, 'utf8'))} (${total})`);
  } else {
    // 终端里在载荷上下各留一行空白，好和 [read] / [write] 日志分开；管道与重定向写纯载荷，
    // 脚本里 `$(htmlmini … -t)` 拿到的仍是精确值（哨兵行本身已是边界，不再留白）。
    const pad = !sourceMarks && mode !== 'json' && Boolean(process.stdout.isTTY);
    const shown = pad ? padPayload(out) : out;
    process.stdout.write(shown + (shown.endsWith('\n') ? '' : '\n'));
    log.info('write', `stdout ${fmtBytes(Buffer.byteLength(out, 'utf8'))} (${total})`);
  }
} catch (err) {
  log.error(err.message);
  // 不用 process.exit(1)：Windows 上静态抓取失败后 undici 句柄仍在收尾，
  // 立刻 exit 会在管道 stdout/stderr 写入未落定时触发 libuv 断言
  // （Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), src\win\async.c），
  // 进程 abort 成 0xC0000409 而不是约定的退出码 1。
  // 置 exitCode 让事件循环自然退出，退出码语义不变。
  process.exitCode = 1;
}
