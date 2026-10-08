import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Minimal hash router. Route = "#/dns/records?x=1".
 * Keeps everything in a single file build and works inside the preview iframe.
 */
export interface RouteState {
  path: string;
  query: URLSearchParams;
}

interface RouterCtx extends RouteState {
  navigate: (to: string, opts?: { replace?: boolean }) => void;
}

const Ctx = createContext<RouterCtx | null>(null);

function parse(): RouteState {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [p, q = ""] = raw.split("?");
  const path = p.startsWith("/") ? p : "/" + p;
  return { path: path.replace(/\/+$/, "") || "/", query: new URLSearchParams(q) };
}

export function RouterProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<RouteState>(parse);

  useEffect(() => {
    const onChange = () => setState(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((to: string, opts?: { replace?: boolean }) => {
    const hash = to.startsWith("#") ? to : "#" + to;
    if (opts?.replace) {
      const url = new URL(window.location.href);
      url.hash = hash;
      window.history.replaceState(null, "", url.toString());
      setState(parse());
    } else {
      window.location.hash = hash;
    }
  }, []);

  const value = useMemo(() => ({ ...state, navigate }), [state, navigate]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRouter() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useRouter outside RouterProvider");
  return v;
}

/** Anchor that integrates with the hash router; still a real <a> for a11y. */
export function Link({
  to,
  className,
  children,
  ...rest
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a href={"#" + to} className={className} {...rest}>
      {children}
    </a>
  );
}
