"use client";

import { useSyncExternalStore } from "react";

type Theme = "dark" | "light";

// The theme lives on <html data-theme>, set before first paint by the script in layout.tsx.
const listeners = new Set<() => void>();
const read = (): Theme => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
};

function apply(next: Theme) {
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("shelfos-theme", next);
  } catch {}
  listeners.forEach((l) => l());
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, read, (): Theme => "dark");
  const light = theme === "light";
  const flip = () => {
    const next: Theme = light ? "dark" : "light";
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    // where the browser can, the whole page cross-fades instead of snapping
    if (doc.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) doc.startViewTransition(() => apply(next));
    else apply(next);
  };
  return (
    <button type="button" role="switch" aria-checked={light} aria-label="Light mode" title={light ? "Switch to dark" : "Switch to light"} onClick={flip} className="theme-switch glass">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" /></svg>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="currentColor" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></svg>
      <i />
    </button>
  );
}
