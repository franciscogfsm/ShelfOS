"use client";

import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Crop } from "./components";
import { ISSUES, STATUS, Status, Store, Task, clock, frameAt, tally } from "./lib";

type Item = { key: string; group: string; title: string; sub: string; hay: string; color?: string; task?: Task; glyph?: string; run: () => void };

/** Words a person might type for each state, in English and Portuguese. */
const WORDS: Record<Status, string> = {
  empty: "empty vazio vazia out of stock sem stock restock repor nothing",
  wrong: "wrong errado misplaced another product trocado fix placement planogram",
  low: "low half baixo meio running out restock soon",
  ok: "ok full cheio compliant fine good",
};

const plain = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** How well one typed word matches a text: start of the text, start of a word, inside a word, or letters in order. */
function wordScore(hay: string, word: string): number {
  const i = hay.indexOf(word);
  if (i === 0) return 100;
  if (i > 0) return hay[i - 1] === " " ? 80 : 55;
  if (word.length < 3) return 0;
  let at = 0;
  for (const ch of word) {
    at = hay.indexOf(ch, at) + 1;
    if (!at) return 0;
  }
  return 20;
}

function score(item: Item, words: string[]): number {
  const title = plain(item.title);
  let total = 0;
  for (const w of words) {
    const s = Math.max(wordScore(title, w) + 30, wordScore(item.hay, w));
    if (s <= 30 && !wordScore(title, w)) return 0;
    total += s;
  }
  return total;
}

export function Search({
  store, tasks, line, playing, onClose, onTask, onCamera, onView, onTime, onFilter, onPlay,
}: {
  store: Store; tasks: Task[]; line: { min: number; max: number; latest: number }; playing: boolean;
  onClose: () => void; onTask: (t: Task) => void; onCamera: (id: string) => void; onView: (v: "tasks" | "wall" | "analytics" | "run") => void;
  onTime: (ts: number) => void; onFilter: (s: Status) => void; onPlay: () => void;
}) {
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const list = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    const out: Item[] = [];
    for (const t of tasks) {
      if (t.status === "ok") continue;
      const slot = t.area.id.split("_")[1];
      out.push({
        key: `t${t.key}`, group: "Needs attention", title: t.area.product, sub: `${STATUS[t.status].hint} · camera ${t.cam.id}, slot ${slot}`,
        hay: plain(`${t.area.product} ${t.area.rawName} ${STATUS[t.status].label} ${STATUS[t.status].action} ${WORDS[t.status]} cam camera ${t.cam.id} slot ${slot} ${t.area.id}`),
        color: STATUS[t.status].color, task: t, run: () => onTask(t),
      });
    }
    const by = new Map<string, Task[]>();
    for (const t of tasks) by.set(t.area.productId, [...(by.get(t.area.productId) ?? []), t]);
    for (const [id, ts] of by) {
      const worst = ts[0];
      const issues = ISSUES.map((s) => [s, ts.filter((t) => t.status === s).length] as const).filter(([, n]) => n);
      const cams = [...new Set(ts.map((t) => t.cam.id))];
      out.push({
        key: `p${id}`, group: "Products", title: worst.area.product,
        sub: `${ts.length} slot${ts.length === 1 ? "" : "s"} · ${issues.length ? issues.map(([s, n]) => `${n} ${STATUS[s].label.toLowerCase()}`).join(", ") : "all fine"} · camera ${cams.join(", ")}`,
        hay: plain(`${worst.area.product} ${worst.area.rawName} ${id} product produto ${ts.map((t) => WORDS[t.status]).join(" ")} ${cams.join(" ")}`),
        color: STATUS[worst.status].color, task: worst, run: () => onTask(worst),
      });
    }
    for (const c of store.cameras) {
      const n = tally(c, frameAt(c, line.latest));
      const todo = n.empty + n.wrong + n.low;
      const worst = ISSUES.find((s) => n[s]) ?? "ok";
      out.push({
        key: `c${c.id}`, group: "Cameras", title: `Camera ${c.id}`, sub: `${c.areas.length} areas · ${todo ? `${todo} need attention` : "all fine"}`,
        hay: plain(`camera cam camara ${c.id} ${[...new Set(c.areas.map((a) => a.product))].join(" ")}`), color: STATUS[worst].color, glyph: "cam", run: () => onCamera(c.id),
      });
    }
    for (const s of ISSUES)
      out.push({ key: `f${s}`, group: "Actions", title: `Show ${STATUS[s].label.toLowerCase()} shelves`, sub: `${tasks.filter((t) => t.status === s).length} right now · ${STATUS[s].action.toLowerCase()}`, hay: plain(`filter show list ${WORDS[s]}`), color: STATUS[s].color, run: () => onFilter(s) });
    out.push(
      { key: "v-tasks", group: "Actions", title: "Open tasks", sub: "Everything that needs doing, biggest impact first", hay: "tasks tarefas todo to do work queue go open", glyph: "→", run: () => onView("tasks") },
      { key: "v-wall", group: "Actions", title: "Open store wall", sub: "All cameras at a glance", hay: "store wall overview home cameras go open loja", glyph: "→", run: () => onView("wall") },
      { key: "v-analytics", group: "Actions", title: "Open analytics", sub: "The day in numbers: trends, cameras by hour, longest problems", hay: "analytics analise stats statistics numbers charts trends insights report heatmap go open", glyph: "→", run: () => onView("analytics") },
      { key: "v-run", group: "Actions", title: "Test new images", sub: "Drop a folder, images or a zip and get predictions.json", hay: "test images upload run predictions validation score analyse analyze folder zip testar", glyph: "↑", run: () => onView("run") },
      { key: "a-play", group: "Actions", title: playing ? "Pause the day" : "Play the day", sub: "Watch the shelves change from opening to now", hay: "play pause replay day timeline history time lapse", glyph: "▶", run: onPlay },
      { key: "a-latest", group: "Actions", title: "Jump to latest", sub: `Back to ${clock(line.latest)}`, hay: "latest now live current jump agora", glyph: "↦", run: () => onTime(line.latest) },
    );
    return out;
  }, [store, tasks, line.latest, playing, onTask, onCamera, onView, onTime, onFilter, onPlay]);

  const results = useMemo(() => {
    const text = plain(q).trim();
    const found: Item[] = [];
    // "14", "14h", "14:30": a time of day to jump to
    const time = /^(\d{1,2})(?:\s*[h:]\s*(\d{2})?)?$/.exec(text);
    if (time) {
      const want = `${time[1].padStart(2, "0")}:${time[2] ?? "00"}`;
      for (let t = Math.floor(line.min / 60) * 60; t <= line.max; t += 60)
        if (clock(t) === want) {
          found.push({ key: "time", group: "Time", title: `Jump to ${want}`, sub: "See the store as it was then", hay: "", glyph: "◷", run: () => onTime(t) });
          break;
        }
    }
    if (!text) return [...items.filter((i) => i.group === "Needs attention").slice(0, 5), ...items.filter((i) => i.group === "Actions")];
    const words = text.split(/\s+/);
    const ranked = items.map((item) => ({ item, s: score(item, words) })).filter((r) => r.s > 0).sort((a, b) => b.s - a.s);
    for (const group of ["Needs attention", "Products", "Cameras", "Actions"]) found.push(...ranked.filter((r) => r.item.group === group).slice(0, 5).map((r) => r.item));
    return found;
  }, [q, items, line.min, line.max, onTime]);

  const active = Math.min(at, results.length - 1);
  useEffect(() => {
    list.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active, results]);

  const pick = (item?: Item) => {
    if (!item) return;
    onClose();
    item.run();
  };

  return (
    <div className="popup-backdrop palette-backdrop" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Search" className="palette glass" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
          <input
            autoFocus
            value={q}
            placeholder="Search a product, a camera, “empty”, or a time like 14h"
            aria-label="Search"
            onChange={(e) => {
              setQ(e.target.value);
              setAt(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setAt((active + (e.key === "ArrowDown" ? 1 : -1) + results.length) % Math.max(1, results.length));
              } else if (e.key === "Enter") pick(results[active]);
              else if (e.key === "Escape") onClose();
            }}
          />
          <kbd>esc</kbd>
        </div>
        <div ref={list} className="palette-list">
          {results.map((item, i) => (
            <div key={item.key}>
              {(i === 0 || results[i - 1].group !== item.group) && <div className="palette-group">{item.group}</div>}
              <button data-active={i === active} style={{ "--i": i } as React.CSSProperties} onMouseMove={() => i !== active && setAt(i)} onClick={() => pick(item)} className="palette-row">
                {item.task ? (
                  <span className="relative shrink-0">
                    <Crop store={store} cam={item.task.cam} frame={item.task.frame} area={item.task.area} className="size-9 rounded-[10px]" />
                    <i style={{ background: item.color }} />
                  </span>
                ) : (
                  <span className="palette-glyph">{item.glyph === "cam" ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="3" /><path d="m16 10 5-3v10l-5-3" /></svg> : item.glyph ?? <b style={{ background: item.color }} />}</span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{item.title}</span>
                  <span className="block truncate text-[11px] text-muted">{item.sub}</span>
                </span>
                <kbd>↵</kbd>
              </button>
            </div>
          ))}
          {results.length === 0 && <div className="px-5 py-12 text-center text-sm text-muted">Nothing matches “{q}”. Try a product name, a camera number or “empty”.</div>}
        </div>
        <div className="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span className="ml-auto">{tasks.length} areas · {store.cameras.length} cameras</span></div>
      </div>
    </div>
  );
}
