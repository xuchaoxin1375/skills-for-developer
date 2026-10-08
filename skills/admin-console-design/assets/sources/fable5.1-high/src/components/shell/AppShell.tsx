import { TopBar } from "./TopBar";
import { DesktopSidebar, MobileDrawer } from "./Sidebar";
import { CommandPalette } from "./CommandPalette";
import { useShell } from "./ShellContext";
import { cn } from "@/utils/cn";

const FOOTER_LINKS = ["Support", "System Status", "Careers", "Terms of Use", "Report Security Issues", "Privacy Policy"];

export function AppShell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  const { peek, isFrame } = useShell();
  return (
    <div className="min-h-full flex flex-col">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <DesktopSidebar />
        <MobileDrawer />
        <div className="flex-1 min-w-0 flex flex-col">
          {/* dim content slightly while peeking so the overlay reads as temporary */}
          <main
            id="main"
            tabIndex={-1}
            className={cn("flex-1 min-w-0 transition-opacity duration-[var(--dur-base)]", peek && "opacity-[0.92]")}
          >
            <div className={cn("mx-auto w-full px-4 sm:px-6 lg:px-8 py-5 sm:py-8", wide ? "max-w-none" : "max-w-[var(--content-max)]")}>{children}</div>
          </main>
          <footer className="border-t border-line bg-surface">
            <div className="mx-auto max-w-[var(--content-max)] px-4 sm:px-6 lg:px-8 py-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm text-fg-2">
              {FOOTER_LINKS.map((l) => (
                <a key={l} href="#/guide/readme" className="hover:text-fg hover:underline underline-offset-2">
                  {l}
                </a>
              ))}
              <span className="text-fg-3">© 2026 Example, Inc.{isFrame ? " · preview" : ""}</span>
            </div>
          </footer>
        </div>
      </div>
      <CommandPalette />
    </div>
  );
}
