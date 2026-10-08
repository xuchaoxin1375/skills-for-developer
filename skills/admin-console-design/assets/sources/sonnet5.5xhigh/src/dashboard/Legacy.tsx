import { useEffect, useState } from "react";
import { postToParent } from "@/lib/bridge";
import { useLayout } from "@/lib/hooks";
import { Link, type Route } from "@/lib/route";
import { fqdn, useData, ttlLabel } from "./data";

/**
 * 「传统方案」对比样本 —— 刻意保留常见缺陷，供与 CF 规范方案并排对比：
 *  1. 侧边栏固定 220px，无折叠 / 无抽屉 → 窄屏内容被挤压
 *  2. 表格强制 min-width，页面级横向滚动
 *  3. 表单：仅 placeholder 当标签、单行硬排列、提交按钮灰掉代替校验、
 *     错误只在顶部笼统提示、不聚焦首个错误、无粘性操作栏、无未保存提醒
 */
export function LegacyShell({ route }: { route: Route }) {
  const layout = useLayout();
  const path = "/" + route.path.join("/");
  const isForm = path.includes("/dns/new") || path.includes("/dns/edit");

  useEffect(() => {
    postToParent({ type: "nimbus:state", path, layout, pinned: "expanded", expanded: true, peek: false, drawer: false, width: window.innerWidth, variant: "legacy" });
  }, [path, layout]);

  return (
    <div className="flex min-h-dvh bg-bg" lang="en">
      <aside className="w-[220px] flex-none border-r border-line bg-subtle p-3">
        <p className="mb-3 px-2 font-bold">NIMBUS</p>
        <ul className="grid gap-1 text-sm">
          {["Overview", "Analytics", "DNS", "Email", "SSL/TLS", "Security", "Access", "Speed", "Caching", "Workers", "Rules"].map((t) => (
            <li key={t}>
              <Link to={t === "DNS" ? "/dashboard/dns" : "/dashboard/overview"} className="block rounded px-2 py-1 text-fg no-underline hover:bg-hover">
                {t}
              </Link>
            </li>
          ))}
        </ul>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex h-12 items-center border-b border-line px-4 font-semibold">myexample.com</header>
        <main className="p-4">{isForm ? <LegacyForm /> : <LegacyList />}</main>
      </div>
    </div>
  );
}

function LegacyList() {
  const { records } = useData();
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">DNS records</h1>
        <Link to="/dashboard/dns/new" className="rounded bg-primary px-3 py-1 text-sm text-white no-underline">
          Add
        </Link>
      </div>
      <table className="w-[900px] border border-line text-sm">
        <thead>
          <tr className="bg-subtle text-left">
            <th className="w-[80px] p-2">Type</th>
            <th className="w-[200px] p-2">Name</th>
            <th className="w-[280px] p-2">Content</th>
            <th className="w-[100px] p-2">Proxy</th>
            <th className="w-[80px] p-2">TTL</th>
            <th className="w-[160px] p-2">Comment</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id} className="border-t border-line">
              <td className="p-2">{r.type}</td>
              <td className="p-2">{fqdn(r.name)}</td>
              <td className="p-2">{r.content}</td>
              <td className="p-2">{r.proxied ? "Proxied" : "DNS only"}</td>
              <td className="p-2">{ttlLabel(r.ttl)}</td>
              <td className="p-2">{r.comment || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LegacyForm() {
  const [v, setV] = useState({ type: "A", name: "", content: "", ttl: "", comment: "" });
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const valid = v.name.length > 0 && v.content.length > 0;
  const set = (k: string, val: string) => {
    setV((s) => ({ ...s, [k]: val }));
    setDone(false);
  };
  return (
    <div>
      <h1 className="mb-3 text-2xl font-semibold">Add record</h1>
      {err && <div className="mb-3 rounded border border-danger bg-danger-soft p-2 text-danger">{err}</div>}
      {done && <div className="mb-3 rounded border border-line bg-ok-soft p-2 text-ok">Saved.</div>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!/^\d+\.\d+\.\d+\.\d+$/.test(v.content)) setErr("Error: invalid input");
          else {
            setErr("");
            setDone(true);
          }
        }}
      >
        <div className="flex gap-2">
          <select className="h-7 w-[90px] flex-none border border-line bg-surface text-xs" value={v.type} onChange={(e) => set("type", e.target.value)} aria-label="Type">
            <option>A</option>
            <option>AAAA</option>
            <option>CNAME</option>
            <option>MX</option>
            <option>TXT</option>
          </select>
          <input className="h-7 w-[160px] flex-none border border-line bg-surface px-1 text-xs" placeholder="Name" value={v.name} onChange={(e) => set("name", e.target.value)} />
          <input className="h-7 w-[220px] flex-none border border-line bg-surface px-1 text-xs" placeholder="IPv4 address" value={v.content} onChange={(e) => set("content", e.target.value)} />
          <input className="h-7 w-[80px] flex-none border border-line bg-surface px-1 text-xs" placeholder="TTL" value={v.ttl} onChange={(e) => set("ttl", e.target.value)} />
          <input className="h-7 w-[200px] flex-none border border-line bg-surface px-1 text-xs" placeholder="Comment" value={v.comment} onChange={(e) => set("comment", e.target.value)} />
          <button type="submit" disabled={!valid} className="h-7 flex-none rounded bg-primary px-3 text-xs text-white disabled:opacity-40">
            Save
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">No labels · placeholder-only fields · disabled submit hides what is wrong · errors are not tied to fields.</p>
      </form>
    </div>
  );
}
