import { useSyncExternalStore } from "react";

export type ThemePref = "system" | "light" | "dark";
const KEY = "nimbus.theme";
const mql = window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

function readInitial(): ThemePref {
  try {
    const m = window.location.hash.match(/[?&]theme=(light|dark|system)/);
    if (m) return m[1] as ThemePref;
    const s = localStorage.getItem(KEY);
    if (s === "light" || s === "dark" || s === "system") return s;
  } catch {
    /* 隐私模式等场景下忽略 */
  }
  return "system";
}

let pref: ThemePref = readInitial();

export function resolveTheme(p: ThemePref = pref): "light" | "dark" {
  return p === "system" ? (mql.matches ? "dark" : "light") : p;
}

function apply() {
  const r = resolveTheme();
  document.documentElement.classList.toggle("dark", r === "dark");
  document.documentElement.style.colorScheme = r;
}

function emit() {
  listeners.forEach((l) => l());
}

apply();
mql.addEventListener("change", () => {
  if (pref === "system") {
    apply();
    emit();
  }
});

export function setTheme(p: ThemePref, persist = true) {
  pref = p;
  apply();
  if (persist) {
    try {
      localStorage.setItem(KEY, p);
    } catch {
      /* ignore */
    }
  }
  emit();
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
const snapshot = () => `${pref}|${resolveTheme()}`;

export function useTheme() {
  const s = useSyncExternalStore(subscribe, snapshot, () => "system|light");
  const [p, r] = s.split("|") as [ThemePref, "light" | "dark"];
  return { pref: p, resolved: r, setPref: setTheme };
}
