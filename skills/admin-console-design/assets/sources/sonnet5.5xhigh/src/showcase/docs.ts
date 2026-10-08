import { Marked } from "marked";
import readme from "../../docs/README.md?raw";
import principles from "../../docs/01-design-principles.md?raw";
import sidebar from "../../docs/02-sidebar-spec.md?raw";
import form from "../../docs/03-form-spec.md?raw";
import responsive from "../../docs/04-responsive-a11y.md?raw";
import tokens from "../../docs/05-design-tokens.md?raw";
import practices from "../../docs/06-best-practices.md?raw";
import usage from "../../docs/07-usage-deploy.md?raw";
import table from "../../docs/08-data-table-spec.md?raw";

export interface DocMeta {
  slug: string;
  title: string;
  summary: string;
  raw: string;
}

export const DOCS: DocMeta[] = [
  { slug: "README", title: "文档地图", summary: "目录、阅读顺序与术语", raw: readme },
  { slug: "01-design-principles", title: "设计思路与原则", summary: "为什么这样设计、取舍与布局原型", raw: principles },
  { slug: "02-sidebar-spec", title: "侧边栏规范", summary: "状态机、悬停意图、动画、键盘与无障碍", raw: sidebar },
  { slug: "03-form-spec", title: "表单页规范", summary: "布局、校验、状态、保存与离开保护", raw: form },
  { slug: "04-responsive-a11y", title: "响应式与无障碍", summary: "断点、容器查询、极窄窗口与 a11y 底线", raw: responsive },
  { slug: "05-design-tokens", title: "设计令牌", summary: "颜色、字号、间距、圆角、阴影、动效", raw: tokens },
  { slug: "06-best-practices", title: "实践指南", summary: "必须 / 应该 / 可以 / 避免", raw: practices },
  { slug: "07-usage-deploy", title: "部署与使用说明", summary: "运行、构建、目录结构与扩展", raw: usage },
  { slug: "08-data-table-spec", title: "交互式表格与条目规范", summary: "列宽调节、排序、批量、粘性操作列、行内 / 弹窗编辑", raw: table },
];

export interface TocItem {
  id: string;
  text: string;
  level: number;
}
export interface RenderedDoc {
  html: string;
  toc: TocItem[];
}

const md = new Marked({ gfm: true, breaks: false });
const cache = new Map<string, RenderedDoc>();

const strip = (s: string) =>
  s
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .trim();

/** Markdown → HTML：为 h2/h3 生成锚点与目录、包裹表格、重写文档间链接 */
export function renderDoc(slug: string): RenderedDoc {
  const hit = cache.get(slug);
  if (hit) return hit;
  const doc = DOCS.find((d) => d.slug === slug) ?? DOCS[0];
  const toc: TocItem[] = [];
  const used = new Map<string, number>();
  let html = md.parse(doc.raw, { async: false }) as string;

  html = html.replace(/<h([23])>([\s\S]*?)<\/h\1>/g, (_m, lv: string, inner: string) => {
    const text = strip(inner);
    let id = text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "") || "section";
    const n = used.get(id) ?? 0;
    used.set(id, n + 1);
    if (n) id = `${id}-${n}`;
    toc.push({ id, text, level: Number(lv) });
    return `<h${lv} id="${id}">${inner}</h${lv}>`;
  });
  html = html
    .replace(/<table>/g, '<div class="doc-table" tabindex="0" role="region" aria-label="表格，可横向滚动"><table>')
    .replace(/<\/table>/g, "</table></div>")
    .replace(/href="((?:README|\d\d-[\w-]+))\.md(#[^"]*)?"/g, (_m, s: string) => `href="#/docs/${s}"`);

  const out = { html, toc };
  cache.set(slug, out);
  return out;
}
