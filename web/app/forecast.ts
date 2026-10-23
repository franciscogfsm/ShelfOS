import type { AreaPred, Camera, Store } from "./lib";

/** How fast a slot sells, from today's captures so far. App only, never part of predictions.json:
 *  the organisers want the official answer to come from the image itself (README, Q6).
 *  Type imports only, so tools/forecast_backtest.ts runs this file under plain Node.
 *
 *  `paceOf` is what the app shows: how long a slot took to go from full to half, a fact read off
 *  the captures. `forecast` extrapolates a run-out time; it failed the pass mark fixed in docs/Plano.md
 *  (idea C) even on perfect readings, so the app does not show it. It stays for the backtest. */

export const MIN_POINTS = 3; // captures since the last restock
export const RESTOCK_JUMP = 0.25; // a rise in the signal between two captures larger than this is a restock
export const THETA_EMPTY = 0.25; // signal at or below this reads as empty (half-way between empty 0 and half 0.5)
export const MAX_HORIZON = 8 * 3600; // further out than this: "stable"
export const MAX_OBSTRUCTION = 0.3; // captures with more of the slot hidden than this are left out
export const MAX_LOOKBACK = 16 * 3600; // only today's captures (test images can carry far-off timestamps)

export type Signal = "fill" | "occ";

export interface Point {
  ts: number;
  probs: [number, number, number];
  occ?: number;
  obstruction?: number;
  source?: "image" | "memory";
}

export type Outlook =
  | { kind: "empties"; at: number; points: number }
  | { kind: "stable"; points: number }
  | null;

/** Expected stock value from the calibrated level probabilities: 0 empty, 0.5 half, 1 full. */
export const fillOf = (p: Pick<AreaPred, "probs">) => 0.5 * p.probs[1] + p.probs[2];

const valueOf = (p: Point, signal: Signal) => (signal === "occ" ? p.occ ?? fillOf(p) : fillOf(p));

export interface Pace {
  /** first capture of the run of full captures before the slot went half (the restock, or the day's first capture) */
  fullFrom: number;
  /** first capture that showed it half */
  halfAt: number;
  seconds: number;
}

/** For a slot that reads half now: when it was last restocked full, and when it was first seen half.
 *  null when the half run did not follow a full one today (e.g. it was refilled only to half). */
export function paceOf(cam: Camera, areaId: string, now: number): Pace | null {
  const levels: { ts: number; level: AreaPred["level"] }[] = [];
  for (const f of cam.frames) {
    const p = f.areas[areaId];
    if (p && f.ts <= now && f.ts >= now - MAX_LOOKBACK && p.source !== "memory") levels.push({ ts: f.ts, level: p.level });
  }
  let i = levels.length - 1;
  if (i < 0 || levels[i].level !== "half") return null;
  while (i > 0 && levels[i - 1].level === "half") i--;
  const half = i;
  if (half === 0 || levels[half - 1].level !== "full") return null;
  i = half - 1;
  while (i > 0 && levels[i - 1].level === "full") i--;
  return { fullFrom: levels[i].ts, halfAt: levels[half].ts, seconds: levels[half].ts - levels[i].ts };
}

/** Pace of every slot that reads half at `ts`, keyed by area id. */
export function paceAt(store: Store, ts: number): Map<string, Pace> {
  const out = new Map<string, Pace>();
  for (const cam of store.cameras)
    for (const a of cam.areas) {
      const p = paceOf(cam, a.id, ts);
      if (p) out.set(a.id, p);
    }
  return out;
}

/** Straight line through the captures since the last restock; where it crosses THETA_EMPTY.
 *  null when there is too little to say anything (then the app shows nothing). */
export function forecast(points: Point[], now: number, signal: Signal = "fill"): Outlook {
  const usable = points.filter((p) => p.ts <= now && p.source !== "memory" && (p.obstruction ?? 0) <= MAX_OBSTRUCTION);
  if (!usable.length) return null;
  const ys = usable.map((p) => valueOf(p, signal));
  let start = 0;
  for (let i = 1; i < ys.length; i++) if (ys[i] - ys[i - 1] > RESTOCK_JUMP) start = i;
  const seg = usable.slice(start);
  const y = ys.slice(start);
  if (y[y.length - 1] <= THETA_EMPTY) return null; // already empty: that is a task of its own
  if (seg.length < MIN_POINTS) return null;

  // least squares y = a + b·x, with x in seconds from the first capture of the segment
  const t0 = seg[0].ts;
  const xs = seg.map((p) => p.ts - t0);
  const mx = xs.reduce((s, x) => s + x, 0) / xs.length;
  const my = y.reduce((s, v) => s + v, 0) / y.length;
  let sxy = 0, sxx = 0;
  for (let i = 0; i < xs.length; i++) {
    sxy += (xs[i] - mx) * (y[i] - my);
    sxx += (xs[i] - mx) ** 2;
  }
  if (sxx === 0) return null;
  const b = sxy / sxx;
  if (b >= 0) return { kind: "stable", points: seg.length };
  const at = t0 + mx + (THETA_EMPTY - my) / b;
  if (at - now > MAX_HORIZON) return { kind: "stable", points: seg.length };
  // the line has already crossed but the last capture still shows stock: it is about to go
  return { kind: "empties", at: Math.max(at, now), points: seg.length };
}
