import { useEffect } from "react";
import { RouterProvider, useRouter } from "@/lib/router";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/components/ui/overlays";
import { ShellProvider } from "@/components/shell/ShellContext";
import { AppShell } from "@/components/shell/AppShell";
import { OverviewPage, PlaceholderPage } from "@/pages/OverviewPage";
import { DnsRecordsPage } from "@/pages/dns/DnsRecordsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { CreateFormPage, WizardPage } from "@/pages/forms/FormPatternsPage";
import { ResponsiveLabPage } from "@/pages/ResponsiveLabPage";
import { DocsPage } from "@/pages/DocsPage";
import { NAV } from "@/data/nav";

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/dns/records": "DNS records",
  "/dns/analytics": "DNS analytics",
  "/dns/settings": "DNS settings",
  "/forms/create": "Create application",
  "/forms/wizard": "Add a domain",
  "/settings": "Settings",
  "/lab": "Responsive Lab",
};

function Routes() {
  const { path } = useRouter();

  useEffect(() => {
    const t = TITLES[path] ?? (path.startsWith("/guide") ? "Design Guide" : "Console");
    document.title = `${t} · Console UI Reference`;
    // scroll to top on route change except in-page anchors
    window.scrollTo({ top: 0 });
  }, [path]);

  let page: React.ReactNode;
  let wide = false;

  if (path === "/") page = <OverviewPage />;
  else if (path === "/dns/records") page = <DnsRecordsPage />;
  else if (path === "/dns/settings") page = <SettingsPage section="dns" />;
  else if (path === "/dns/analytics") page = <PlaceholderPage title="DNS analytics" />;
  else if (path === "/forms/create") page = <CreateFormPage />;
  else if (path === "/forms/wizard") page = <WizardPage />;
  else if (path === "/settings") page = <SettingsPage />;
  else if (path === "/lab") {
    page = <ResponsiveLabPage />;
    wide = true;
  } else if (path.startsWith("/guide")) {
    const slug = path.split("/")[2] || "readme";
    page = <DocsPage slug={slug} />;
  } else if (path.startsWith("/placeholder/")) {
    const id = path.split("/")[2];
    const label =
      NAV.find((n) => n.path === path)?.label ?? NAV.flatMap((n) => n.children ?? []).find((c) => c.path === path)?.label ?? id;
    page = <PlaceholderPage title={label} />;
  } else page = <PlaceholderPage title="Page not found" />;

  return <AppShell wide={wide}>{page}</AppShell>;
}

export default function App() {
  return (
    <ThemeProvider>
      <RouterProvider>
        <ToastProvider>
          <ShellProvider>
            <Routes />
          </ShellProvider>
        </ToastProvider>
      </RouterProvider>
    </ThemeProvider>
  );
}
