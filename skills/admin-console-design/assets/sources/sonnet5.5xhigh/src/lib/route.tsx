import { useMemo, useSyncExternalStore, type AnchorHTMLAttributes } from "react";

/**
 * 极简 hash 路由：#/path/a/b?query
 * - embed / variant 两个参数会在站内跳转时自动保留（用于 iframe 预览）
 * - 支持"导航守卫"：表单有未保存修改时拦截站内跳转，弹出确认
 */
export interface Route {
  path: string[];
  params: URLSearchParams;
}

function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}
const getHash = () => window.location.hash;

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#/, "");
  const [p, q = ""] = h.split("?");
  return { path: p.split("/").filter(Boolean), params: new URLSearchParams(q) };
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getHash, () => "");
  return useMemo(() => parseHash(hash), [hash]);
}

const PERSIST = ["embed", "variant"];

export function withPersist(to: string): string {
  const [p, q = ""] = to.split("?");
  const cur = parseHash(window.location.hash).params;
  const next = new URLSearchParams(q);
  for (const k of PERSIST) {
    const v = cur.get(k);
    if (v && !next.has(k)) next.set(k, v);
  }
  const qs = next.toString();
  return `#${p}${qs ? "?" + qs : ""}`;
}

type Guard = (proceed: () => void) => boolean;
let guard: Guard | null = null;
export function setNavGuard(g: Guard | null) {
  guard = g;
}

export function navigate(to: string, opts?: { replace?: boolean; force?: boolean }) {
  const go = () => {
    const h = withPersist(to);
    if (opts?.replace) window.location.replace(h);
    else window.location.hash = h.slice(1);
  };
  if (guard && !opts?.force && guard(go)) return;
  go();
}

export function Link({ to, onClick, ...rest }: { to: string } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const href = withPersist(to);
  return (
    <a
      {...rest}
      href={href}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        if (guard) {
          e.preventDefault();
          navigate(to);
        }
      }}
    />
  );
}
