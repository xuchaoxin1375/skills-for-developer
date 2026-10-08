import { useCallback, useEffect, useRef, useState, type FocusEvent, type PointerEvent } from 'react';

export function useStoredState<T>(key: string, fallback: T, validate?: (value: unknown) => boolean) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) {
        const parsed: unknown = JSON.parse(raw);
        if (validate ? validate(parsed) : typeof parsed === typeof fallback) return parsed as T;
      }
    } catch { /* A restricted browser still gets a fully usable in-memory session. */ }
    return fallback;
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage is an enhancement, not a prerequisite. */ }
  }, [key, value]);
  return [value, setValue] as const;
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [query]);
  return matches;
}

export function useHoverNavigation(pinned: boolean, enabled = true, delay = 120) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const enterTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const clearTimers = useCallback(() => { clearTimeout(enterTimer.current); clearTimeout(leaveTimer.current); }, []);
  useEffect(() => clearTimers, [clearTimers]);
  useEffect(() => { clearTimers(); if (!enabled || pinned) setHovered(false); }, [enabled, pinned, delay, clearTimers]);
  return {
    expanded: pinned || hovered || focused,
    reset: () => { clearTimers(); setHovered(false); setFocused(false); },
    handlers: {
      onPointerEnter: (event: PointerEvent<HTMLElement>) => {
        if (!enabled || pinned || event.pointerType === 'touch' || !window.matchMedia('(hover: hover)').matches) return;
        clearTimers();
        enterTimer.current = setTimeout(() => setHovered(true), delay);
      },
      onPointerLeave: () => {
        clearTimers();
        leaveTimer.current = setTimeout(() => setHovered(false), 240);
      },
      onFocusCapture: (event: FocusEvent<HTMLElement>) => {
        setFocused(!pinned && !(event.target as HTMLElement).closest('[data-nav-toggle]'));
      },
      onBlurCapture: (event: FocusEvent<HTMLElement>) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
      },
    },
  };
}

export function useOutsideClose(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const pointer = (event: globalThis.PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) closeRef.current();
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        const activeDialog = document.querySelector('dialog[open]');
        if (activeDialog && !activeDialog.contains(ref.current)) return;
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
        ref.current?.querySelector<HTMLElement>('[aria-expanded]')?.focus();
      }
    };
    document.addEventListener('pointerdown', pointer);
    document.addEventListener('keydown', keyboard);
    return () => {
      document.removeEventListener('pointerdown', pointer);
      document.removeEventListener('keydown', keyboard);
    };
  }, [open]);
  return ref;
}