import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useBreakpoint, useLocalStorage } from "@/lib/hooks";
import { useRouter } from "@/lib/router";

/**
 * Sidebar state model (see docs/03-shell-and-sidebar.md):
 *
 *  desktop/tablet:  pinned  ──toggle──▶ collapsed (rail)
 *                   collapsed + hover/focus ──▶ peek (overlay, does not push content)
 *  mobile:          hidden ──hamburger──▶ drawer (modal)
 */
interface ShellState {
  isFrame: boolean;
  pinned: boolean;
  setPinned: (v: boolean) => void;
  peek: boolean;
  /** effective visual state of the desktop sidebar */
  expanded: boolean;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
  paletteOpen: boolean;
  setPaletteOpen: (v: boolean) => void;
  /** sidebar hover/focus handlers (hoverPeek vs focusPeek independent) */
  onSidebarEnter: () => void;
  onSidebarLeave: () => void;
  onSidebarFocusIn: () => void;
  onSidebarFocusOut: (next: EventTarget | null, panel: HTMLElement | null) => void;
  /** defers peek while a press is held so rows can't shift under the pointer */
  onSidebarPointerDown: (e: React.PointerEvent) => void;
  onSidebarPointerUp: (panel: HTMLElement | null) => void;
  /** Collapse button: closes peek and suppresses hover re-peek until pointer leaves */
  collapseNow: () => void;
  /** Esc dismiss: closes peek without suppressing future hover; holds focusPeek until focus leaves */
  dismissPeek: () => void;
  canHover: boolean;
  isMobile: boolean;
}

const Ctx = createContext<ShellState | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const { isMobile, canHover, isDesktop } = useBreakpoint();
  const isFrame = useMemo(() => new URLSearchParams(window.location.search).has("frame"), []);
  const { path } = useRouter();

  // pinned persisted; default expanded on desktop, rail on tablet
  const [pinnedStored, setPinnedStored] = useLocalStorage<boolean | null>("cfui.sidebar.pinned", null);
  const pinned = pinnedStored ?? isDesktop;
  const setPinned = useCallback((v: boolean) => setPinnedStored(v), [setPinnedStored]);

  const [hoverPeek, setHoverPeek] = useState(false);
  const [focusPeek, setFocusPeek] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const enterT = useRef<number | null>(null);
  const leaveT = useRef<number | null>(null);
  // deferred focus re-arm after press release (runs after click so the rail
  // activation keeps rail semantics); tracked so dismiss/collapse/unmount or
  // a new press can cancel/supersede it instead of firing with a stale panel
  const focusRearmT = useRef<number | null>(null);
  // only suppresses hover re-peek after Collapse click; never blocks keyboard focus peek
  const suppressHover = useRef(false);
  // suppresses focus re-peek after Esc dismiss while focus stays inside;
  // cleared once focus fully leaves the panel so later re-entry can peek again
  const suppressFocus = useRef(false);
  // true while a primary pointer press started inside the sidebar is held:
  // defers hover/focus peek until release so rows can't shift under a
  // stationary pointer (pointerdown in rail -> peek -> pointerup miss)
  const pressHold = useRef(false);

  const clearHoverTimers = () => {
    if (enterT.current) window.clearTimeout(enterT.current);
    if (leaveT.current) window.clearTimeout(leaveT.current);
    if (focusRearmT.current) window.clearTimeout(focusRearmT.current);
    enterT.current = null;
    leaveT.current = null;
    focusRearmT.current = null;
  };

  // avoid setState on unmounted provider when hover timers are pending
  useEffect(() => () => clearHoverTimers(), []);

  const onSidebarEnter = useCallback(() => {
    if (pinned || !canHover || suppressHover.current || pressHold.current) return;
    if (enterT.current) window.clearTimeout(enterT.current);
    if (leaveT.current) window.clearTimeout(leaveT.current);
    enterT.current = window.setTimeout(() => setHoverPeek(true), 110);
  }, [pinned, canHover]);

  const onSidebarLeave = useCallback(() => {
    suppressHover.current = false;
    if (enterT.current) window.clearTimeout(enterT.current);
    if (leaveT.current) window.clearTimeout(leaveT.current);
    leaveT.current = window.setTimeout(() => setHoverPeek(false), 220);
  }, []);

  const onSidebarFocusIn = useCallback(() => {
    if (pinned) return;
    if (suppressFocus.current || pressHold.current) return;
    setFocusPeek(true);
  }, [pinned]);

  const onSidebarFocusOut = useCallback((next: EventTarget | null, panel: HTMLElement | null) => {
    if (panel && next instanceof Node && panel.contains(next)) return;
    suppressFocus.current = false;
    setFocusPeek(false);
  }, []);

  const onSidebarPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (pinned || e.button !== 0) return;
      pressHold.current = true;
      // cancel a pending hover-peek so no expansion happens mid-press,
      // and supersede a pending focus re-arm from a previous release
      if (enterT.current) {
        window.clearTimeout(enterT.current);
        enterT.current = null;
      }
      if (focusRearmT.current) {
        window.clearTimeout(focusRearmT.current);
        focusRearmT.current = null;
      }
    },
    [pinned]
  );

  const onSidebarPointerUp = useCallback(
    (panel: HTMLElement | null) => {
      if (!pressHold.current) return;
      pressHold.current = false;
      if (pinned) return;
      // Defer focus re-arm until after click dispatch: setting focusPeek
      // synchronously here would flip the rail onClick (navigate to first
      // child) to the peek onClick (accordion toggle) before click fires,
      // swallowing the intended Rail navigation. The timeout runs after click.
      if (focusRearmT.current) window.clearTimeout(focusRearmT.current);
      focusRearmT.current = window.setTimeout(() => {
        focusRearmT.current = null;
        if (!panel?.isConnected) return;
        const active = document.activeElement as Node | null;
        if (!suppressFocus.current && active && panel.contains(active)) setFocusPeek(true);
      }, 0);
      // …and hover peek on the normal enter delay (no hover suppression here)
      if (!canHover || suppressHover.current) return;
      if (enterT.current) window.clearTimeout(enterT.current);
      if (leaveT.current) window.clearTimeout(leaveT.current);
      enterT.current = window.setTimeout(() => setHoverPeek(true), 110);
    },
    [pinned, canHover]
  );

  // release outside the panel still clears the hold (no re-arm)
  useEffect(() => {
    const clear = () => {
      pressHold.current = false;
    };
    window.addEventListener("pointerup", clear);
    window.addEventListener("pointercancel", clear);
    return () => {
      window.removeEventListener("pointerup", clear);
      window.removeEventListener("pointercancel", clear);
    };
  }, []);

  const collapseNow = useCallback(() => {
    suppressHover.current = true;
    clearHoverTimers();
    setHoverPeek(false);
    setFocusPeek(false);
  }, []);

  const dismissPeek = useCallback(() => {
    clearHoverTimers();
    // Esc close: keep hover re-armable after pointer exit/reentry (no suppressHover).
    // Only hold focusPeek closed when focus actually stays inside the panel, so the
    // retained focus does not immediately reopen peek (cleared on full focus-out).
    // For hover-only peek with focus outside, no suppression: there will be no
    // panel focusOut to clear it, and the next keyboard entry must still open peek.
    const active = document.activeElement as HTMLElement | null;
    suppressFocus.current = !!active?.closest?.("[data-state]");
    setHoverPeek(false);
    setFocusPeek(false);
  }, []);

  // reset transient states on breakpoint / route changes
  useEffect(() => {
    setMobileOpen(false);
    // touch devices have no "mouseleave": collapse the peek once navigation happened
    if (!canHover) {
      setHoverPeek(false);
      setFocusPeek(false);
    }
  }, [path, canHover]);
  useEffect(() => {
    if (pinned) {
      suppressFocus.current = false;
      setHoverPeek(false);
      setFocusPeek(false);
    }
  }, [pinned]);
  useEffect(() => {
    if (!isMobile) setMobileOpen(false);
  }, [isMobile]);

  // global shortcuts: Ctrl/⌘+K palette, "[" toggles sidebar
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === "[" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setPinnedStored((p) => !(p ?? isDesktop));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPinnedStored, isDesktop]);

  const derivedPeek = (hoverPeek || focusPeek) && !pinned;
  const derivedExpanded = pinned || hoverPeek || focusPeek;
  const value = useMemo<ShellState>(
    () => ({
      isFrame,
      pinned,
      setPinned,
      peek: derivedPeek,
      expanded: derivedExpanded,
      mobileOpen,
      setMobileOpen,
      paletteOpen,
      setPaletteOpen,
      onSidebarEnter,
      onSidebarLeave,
      onSidebarFocusIn,
      onSidebarFocusOut,
      onSidebarPointerDown,
      onSidebarPointerUp,
      collapseNow,
      dismissPeek,
      canHover,
      isMobile,
    }),
    [isFrame, pinned, setPinned, derivedPeek, derivedExpanded, mobileOpen, paletteOpen, onSidebarEnter, onSidebarLeave, onSidebarFocusIn, onSidebarFocusOut, onSidebarPointerDown, onSidebarPointerUp, collapseNow, dismissPeek, canHover, isMobile]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShell() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useShell outside ShellProvider");
  return v;
}
