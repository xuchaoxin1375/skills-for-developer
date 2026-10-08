import { useEffect } from "react";
import { useRoute } from "@/lib/route";
import DashboardApp from "@/dashboard/DashboardApp";
import Showcase from "@/showcase/Showcase";

/**
 * 路由：
 *   #/                       展示壳 · 设计稿（舞台 + 控制浮层）
 *   #/docs/<slug>            展示壳 · 文档
 *   #/dashboard/...          设计稿本体（Nimbus Console），可独立打开，也会被舞台以 iframe 嵌入
 */
export default function App() {
  const route = useRoute();
  const isDashboard = route.path[0] === "dashboard";

  useEffect(() => {
    if (isDashboard) document.title = "Nimbus Console · DNS records";
    else if (route.path[0] !== "docs") document.title = "Nimbus Console · Cloudflare 风格控制台设计参考";
  }, [isDashboard, route.path]);

  return isDashboard ? <DashboardApp route={route} /> : <Showcase route={route} />;
}
