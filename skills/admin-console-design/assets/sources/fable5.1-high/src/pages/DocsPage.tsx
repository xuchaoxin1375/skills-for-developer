import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronLeft, ChevronRight, List } from "lucide-react";
import { cn } from "@/utils/cn";
import { Button } from "@/components/ui/primitives";
import { Card, CollapsibleCard } from "@/components/ui/layout";
import { Link } from "@/lib/router";

import readme from "../../docs/README.md?raw";
import principles from "../../docs/01-design-principles.md?raw";
import tokens from "../../docs/02-tokens.md?raw";
import shell from "../../docs/03-shell-and-sidebar.md?raw";
import forms from "../../docs/04-forms.md?raw";
import tables from "../../docs/05-tables-and-lists.md?raw";
import responsive from "../../docs/06-responsive.md?raw";
import a11y from "../../docs/07-accessibility.md?raw";
import deployment from "../../docs/08-deployment.md?raw";

export const DOCS: { slug: string; title: string; file: string; body: string }[] = [
  { slug: "readme", title: "Document map", file: "docs/README.md", body: readme },
  { slug: "principles", title: "01 · Principles", file: "docs/01-design-principles.md", body: principles },
  { slug: "tokens", title: "02 · Tokens & visuals", file: "docs/02-tokens.md", body: tokens },
  { slug: "shell", title: "03 · Shell & sidebar", file: "docs/03-shell-and-sidebar.md", body: shell },
  { slug: "forms", title: "04 · Forms", file: "docs/04-forms.md", body: forms },
  { slug: "tables", title: "05 · Tables & lists", file: "docs/05-tables-and-lists.md", body: tables },
  { slug: "responsive", title: "06 · Responsive", file: "docs/06-responsive.md", body: responsive },
  { slug: "accessibility", title: "07 · Accessibility", file: "docs/07-accessibility.md", body: a11y },
  { slug: "deployment", title: "08 · Deploy & usage", file: "docs/08-deployment.md", body: deployment },
];

/** GitHub-like heading ids; keeps CJK characters. */
function slugify(text: string) {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
}

function textOf(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) return textOf((node as any).props.children);
  return "";
}

export function DocsPage({ slug }: { slug: string }) {
  const idx = Math.max(0, DOCS.findIndex((d) => d.slug === slug));
  const doc = DOCS[idx];
  const prev = DOCS[idx - 1];
  const next = DOCS[idx + 1];
  const [activeH, setActiveH] = useState<string>("");

  const headings = useMemo(() => {
    const out: { id: string; text: string; level: number }[] = [];
    doc.body.split("\n").forEach((line) => {
      const m = /^(##|###)\s+(.*)$/.exec(line);
      if (m) {
        const text = m[2].replace(/[`*]/g, "");
        out.push({ id: slugify(text), text, level: m[1].length });
      }
    });
    return out;
  }, [doc]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
    setActiveH(headings[0]?.id ?? "");
  }, [slug, headings]);

  useEffect(() => {
    const els = headings.map((h) => document.getElementById(h.id)).filter(Boolean) as HTMLElement[];
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActiveH(vis[0].target.id);
      },
      { rootMargin: "-72px 0px -70% 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [headings, slug]);

  const outline = (
    <ul className="space-y-0.5">
      {headings.map((h) => (
        <li key={h.id}>
          <a
            href={`#/guide/${slug}`}
            onClick={(e) => {
              e.preventDefault();
              document.getElementById(h.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            aria-current={activeH === h.id ? "location" : undefined}
            className={cn(
              "block py-1 pr-2 text-sm border-l-2 -ml-px leading-5 transition-colors",
              h.level === 3 ? "pl-6" : "pl-3",
              activeH === h.id ? "border-primary text-fg font-medium" : "border-transparent text-fg-3 hover:text-fg"
            )}
          >
            {h.text}
          </a>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_240px] gap-6 items-start">
      <div className="min-w-0">
        <p className="text-sm text-fg-3 mb-3 font-mono">{doc.file}</p>

        {/* mobile outline: collapsible above content */}
        <div className="xl:hidden mb-4">
          <CollapsibleCard title="On this page" defaultOpen={false} meta={<List className="size-4 text-fg-3" aria-hidden />}>
            <div className="px-3 py-2 border-l-0">{outline}</div>
          </CollapsibleCard>
        </div>

        <Card className="px-5 sm:px-8 py-6 sm:py-8">
          <article className="prose-doc">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => <h1>{children}</h1>,
                h2: ({ children }) => <h2 id={slugify(textOf(children))}>{children}</h2>,
                h3: ({ children }) => <h3 id={slugify(textOf(children))}>{children}</h3>,
                a: ({ href, children }) => (
                  <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel={href?.startsWith("http") ? "noreferrer" : undefined}>
                    {children}
                  </a>
                ),
                input: ({ checked }) => (
                  <input type="checkbox" checked={!!checked} readOnly aria-label={checked ? "done" : "to do"} className="mr-2 align-middle accent-[var(--c-primary)]" />
                ),
              }}
            >
              {doc.body}
            </ReactMarkdown>
          </article>
        </Card>

        <nav aria-label="Document pagination" className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {prev ? (
            <Link to={`/guide/${prev.slug}`} className="group block">
              <Card className="p-4 h-full group-hover:border-line-strong transition-colors">
                <span className="text-xs text-fg-3 flex items-center gap-1"><ChevronLeft className="size-3.5" /> Previous</span>
                <span className="block text-base font-medium text-fg mt-1">{prev.title}</span>
              </Card>
            </Link>
          ) : <span />}
          {next && (
            <Link to={`/guide/${next.slug}`} className="group block sm:text-right">
              <Card className="p-4 h-full group-hover:border-line-strong transition-colors">
                <span className="text-xs text-fg-3 flex items-center gap-1 sm:justify-end">Next <ChevronRight className="size-3.5" /></span>
                <span className="block text-base font-medium text-fg mt-1">{next.title}</span>
              </Card>
            </Link>
          )}
        </nav>
      </div>

      <aside className="hidden xl:block sticky top-[calc(var(--topbar-h)_+_24px)] max-h-[calc(100vh_-_var(--topbar-h)_-_48px)] overflow-y-auto">
        <p className="text-2xs font-semibold uppercase tracking-wide text-fg-3 mb-2 pl-3">On this page</p>
        <div className="border-l border-line">{outline}</div>
        <div className="mt-4 pl-3">
          <Button size="sm" variant="ghost" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            Back to top
          </Button>
        </div>
      </aside>
    </div>
  );
}
