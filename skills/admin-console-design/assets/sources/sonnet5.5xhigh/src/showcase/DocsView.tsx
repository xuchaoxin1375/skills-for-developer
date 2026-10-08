import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, PanelLeft } from "lucide-react";
import { useMediaQuery } from "@/lib/hooks";
import { Link } from "@/lib/route";
import { cn } from "@/utils/cn";
import { DOCS, renderDoc } from "./docs";
import { Panel } from "./Panel";

export function DocsView({ slug }: { slug?: string }) {
  const wide = useMediaQuery("(min-width: 1024px)");
  const [mapOpen, setMapOpen] = useState(() => window.innerWidth >= 1024);
  const idx = Math.max(
    0,
    DOCS.findIndex((d) => d.slug === slug),
  );
  const doc = DOCS[idx];
  const { html, toc } = useMemo(() => renderDoc(doc.slug), [doc.slug]);
  const scroller = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState("");

  // 切换文档：回到顶部；窄屏自动收起文档地图
  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
    setActive("");
    if (!wide) setMapOpen(false);
    document.title = `${doc.title} · Nimbus Console 设计参考`;
  }, [doc.slug, doc.title, wide]);

  // 目录高亮：IntersectionObserver，避免在 scroll 事件里做布局计算
  useEffect(() => {
    const root = scroller.current;
    if (!root || !toc.length) return;
    const els = toc.map((t) => root.querySelector<HTMLElement>(`#${CSS.escape(t.id)}`)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (vis) setActive(vis.target.id);
      },
      { root, rootMargin: "0px 0px -75% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [toc, html]);

  const jump = (id: string) => {
    const el = scroller.current?.querySelector<HTMLElement>(`#${CSS.escape(id)}`);
    el?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    setActive(id);
  };

  return (
    <div className="absolute inset-0 flex min-h-0">
      <Panel open={mapOpen} onClose={() => setMapOpen(false)} inflow={wide} width={288} label="文档地图">
        <nav aria-label="文档地图" className="p-4">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">文档地图</h2>
          <ul className="grid gap-1">
            {DOCS.map((d) => (
              <li key={d.slug}>
                <Link
                  to={`/docs/${d.slug}`}
                  aria-current={d.slug === doc.slug ? "page" : undefined}
                  className="block rounded-md px-3 py-2 text-fg no-underline hover:bg-hover aria-[current=page]:bg-active"
                >
                  <span className="block font-semibold">{d.title}</span>
                  <span className="block text-xs text-muted">{d.summary}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </Panel>

      <div ref={scroller} className="min-w-0 flex-1 overflow-y-auto bg-bg">
        <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-line bg-bg px-4 py-2">
          <button type="button" className="btn btn-ghost btn-icon" aria-expanded={mapOpen} aria-label={mapOpen ? "收起文档地图" : "展开文档地图"} onClick={() => setMapOpen((o) => !o)}>
            <PanelLeft size={18} aria-hidden="true" />
          </button>
          <p className="min-w-0 flex-1 truncate font-semibold">{doc.title}</p>
        </div>
        <div className="mx-auto flex max-w-[1200px] items-start gap-8 px-4 py-8 sm:px-8">
          <div className="min-w-0 max-w-3xl flex-1">
            <article
              className="prose-doc"
              // 文档为项目内置、构建期引入的受信任内容
              dangerouslySetInnerHTML={{ __html: html }}
              onClick={(e) => {
                const a = (e.target as HTMLElement).closest("a");
                const href = a?.getAttribute("href");
                if (href && href.startsWith("#") && !href.startsWith("#/")) {
                  e.preventDefault();
                  jump(href.slice(1));
                }
              }}
            />
            <nav aria-label="上一篇与下一篇" className="mt-12 flex flex-wrap justify-between gap-3 border-t border-line pt-6">
              {idx > 0 ? (
                <Link to={`/docs/${DOCS[idx - 1].slug}`} className="btn">
                  <ChevronLeft size={16} aria-hidden="true" />
                  {DOCS[idx - 1].title}
                </Link>
              ) : (
                <span />
              )}
              {idx < DOCS.length - 1 && (
                <Link to={`/docs/${DOCS[idx + 1].slug}`} className="btn">
                  {DOCS[idx + 1].title}
                  <ChevronRight size={16} aria-hidden="true" />
                </Link>
              )}
            </nav>
          </div>
          {toc.length > 0 && (
            <nav aria-label="本页大纲" className="sticky top-16 hidden max-h-[calc(100dvh-160px)] w-56 flex-none overflow-y-auto xl:block">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">本页大纲</h2>
              <ul className="grid gap-1 border-l border-line">
                {toc.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => jump(t.id)}
                      aria-current={active === t.id ? "location" : undefined}
                      className={cn(
                        "block w-full border-0 bg-transparent py-1 text-left text-sm text-muted hover:text-fg aria-[current=location]:font-semibold aria-[current=location]:text-link",
                        t.level === 3 ? "pl-6" : "pl-3",
                      )}
                    >
                      {t.text}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}
