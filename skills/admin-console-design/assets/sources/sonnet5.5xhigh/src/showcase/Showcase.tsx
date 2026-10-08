import { Cloud, Monitor, Moon, Sun } from "lucide-react";
import { Link, type Route } from "@/lib/route";
import { useTheme, type ThemePref } from "@/lib/theme";
import { DocsView } from "./DocsView";
import { PrototypeView } from "./Stage";

const THEMES: { v: ThemePref; label: string; Icon: typeof Sun }[] = [
  { v: "system", label: "跟随系统", Icon: Monitor },
  { v: "light", label: "浅色", Icon: Sun },
  { v: "dark", label: "深色", Icon: Moon },
];

/** 展示壳：顶部导航（设计稿 / 文档）+ 主题切换；设计稿运行在 iframe 中，拥有真实的媒体查询环境 */
export default function Showcase({ route }: { route: Route }) {
  const { pref, setPref } = useTheme();
  const docs = route.path[0] === "docs";

  const tab = (active: boolean) =>
    `inline-flex min-h-9 items-center border-b-2 px-2 font-medium no-underline sm:px-3 ${active ? "border-primary text-fg" : "border-transparent text-muted hover:text-fg"}`;

  return (
    <div className="flex h-dvh flex-col bg-bg">
      <header className="flex h-14 flex-none items-center gap-2 border-b border-line bg-bg px-3 sm:gap-3 sm:px-4">
        <Link to="/" className="flex min-w-0 flex-none items-center gap-2 text-fg no-underline" aria-label="Nimbus Console 设计参考 首页">
          <Cloud size={24} fill="currentColor" aria-hidden="true" className="flex-none text-brand" />
          <span className="hidden truncate font-bold sm:inline">Nimbus Console · 设计参考</span>
        </Link>
        <nav aria-label="主导航" className="flex items-center gap-1">
          <Link to="/" className={tab(!docs)} aria-current={!docs ? "page" : undefined}>
            设计稿
          </Link>
          <Link to="/docs/README" className={tab(docs)} aria-current={docs ? "page" : undefined}>
            文档
          </Link>
        </nav>
        <div className="seg ml-auto flex-none" role="group" aria-label="外观主题">
          {THEMES.map(({ v, label, Icon }) => (
            <button key={v} type="button" aria-pressed={pref === v} title={label} aria-label={label} onClick={() => setPref(v)}>
              <Icon size={16} aria-hidden="true" />
              <span className="hidden md:inline">{label}</span>
            </button>
          ))}
        </div>
      </header>
      <main className="relative min-h-0 flex-1 overflow-hidden">{docs ? <DocsView slug={route.path[1]} /> : <PrototypeView />}</main>
    </div>
  );
}
