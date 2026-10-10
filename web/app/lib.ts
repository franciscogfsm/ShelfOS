export type Level = "empty" | "half" | "full";
export type Status = "ok" | "low" | "empty" | "wrong";

export interface AreaPred {
  ok: boolean;
  level: Level;
  probs: [number, number, number];
  pOk: number;
  occ: number;
  map: number[][];
  /** catalogue products the crop resembles most: [productId, similarity] */
  looks?: [string, number][];
  /** "memory": the image was unreadable here, answered from the last known state */
  source?: "image" | "memory";
  /** share of the slot covered by something never seen on this shelf today (shopper, cart, boxes) */
  obstruction?: number;
}
export interface AreaDef {
  id: string;
  productId: string;
  product: string;
  rawName: string;
  quad: [number, number][];
}
export interface Frame {
  file: string;
  ts: number;
  areas: Record<string, AreaPred>;
  /** "reference": the day ShelfOS learned from. "run": an image tested through the app. */
  origin?: "reference" | "run";
  ms?: number | null;
  /** how the camera was found: its folder, an id in the file name, or the picture itself */
  cameraSource?: "folder" | "name" | "auto" | null;
  warnings?: string[];
}
export interface Camera {
  id: string;
  areas: AreaDef[];
  frames: Frame[];
}
export interface Store {
  store: string;
  section: string;
  width: number;
  height: number;
  cameras: Camera[];
  emptyCompliant?: boolean;
  products?: Record<string, { name: string; rawName: string }>;
  run?: { images: number; areas: number; ms: number } | null;
  /** set on load: where the camera images are served from, and whether the inference server answered */
  base?: string;
  live?: boolean;
}
export interface Task {
  key: string;
  cam: Camera;
  frame: Frame;
  area: AreaDef;
  pred: AreaPred;
  status: Status;
}

/** The four states of the brief: "compliant, low, empty or holding the wrong product". */
export const STATUS: Record<Status, { label: string; action: string; hint: string; color: string; glyph: string; rank: number }> = {
  empty: { label: "Empty", action: "Restock now", hint: "Nothing on the shelf", color: "#ff6b7a", glyph: "!", rank: 0 },
  wrong: { label: "Wrong product", action: "Fix placement", hint: "Holding another product", color: "#a996ff", glyph: "⇄", rank: 1 },
  low: { label: "Low", action: "Restock soon", hint: "About half left", color: "#f5b84a", glyph: "↓", rank: 2 },
  ok: { label: "Compliant", action: "No action", hint: "Full and in place", color: "#3ddc97", glyph: "✓", rank: 3 },
};
export const ORDER: Status[] = ["empty", "wrong", "low", "ok"];
export const ISSUES: Status[] = ["empty", "wrong", "low"];
export const LEVEL_VALUE: Record<Level, number> = { empty: 0, half: 0.5, full: 1 };
export const ACCENT = "#fafafa";

export function statusOf(p: AreaPred): Status {
  if (p.level === "empty") return "empty";
  if (!p.ok) return "wrong";
  if (p.level === "half") return "low";
  return "ok";
}

/** Confidence in the call that drives the status, 0..1. */
export function confidence(p: AreaPred): number {
  const s = statusOf(p);
  if (s === "wrong") return 1 - p.pOk;
  return p.probs[{ empty: 0, half: 1, full: 2 }[p.level]];
}

/** Latest frame at or before `ts`; the first frame if the camera had not captured yet. */
export function frameAt(cam: Camera, ts: number): Frame {
  let best = cam.frames[0];
  for (const f of cam.frames) if (f.ts <= ts) best = f;
  return best;
}

export function tasksAt(store: Store, ts: number): Task[] {
  const out: Task[] = [];
  for (const cam of store.cameras) {
    const frame = frameAt(cam, ts);
    for (const area of cam.areas) {
      const pred = frame.areas[area.id];
      if (pred) out.push({ key: `${area.id}@${frame.file}`, cam, frame, area, pred, status: statusOf(pred) });
    }
  }
  return out.sort((a, b) => STATUS[a.status].rank - STATUS[b.status].rank || confidence(b.pred) - confidence(a.pred));
}

/** When the area last looked different from its current status (walking back through the day). */
export function since(cam: Camera, areaId: string, frame: Frame): number {
  const now = statusOf(frame.areas[areaId]);
  let start = frame.ts;
  for (let i = cam.frames.indexOf(frame) - 1; i >= 0; i--) {
    const p = cam.frames[i].areas[areaId];
    if (!p || statusOf(p) !== now) break;
    start = cam.frames[i].ts;
  }
  return start;
}

/** Time span of the day on the scrubber, and the newest capture of all. Captures far from the
 *  rest (a test image with an odd timestamp) stay reachable through `latest` without stretching the axis. */
export function timeline(store: Store): { min: number; max: number; latest: number } {
  const all = store.cameras.flatMap((c) => c.frames.map((f) => f.ts)).sort((a, b) => a - b);
  if (!all.length) return { min: 0, max: 1, latest: 1 };
  const mid = all[all.length >> 1];
  const near = all.filter((t) => Math.abs(t - mid) < 36 * 3600);
  return { min: near[0], max: Math.max(near[near.length - 1], near[0] + 1), latest: all[all.length - 1] };
}

/** Add (or replace) one analysed image in a camera's day, keeping the frames in time order. */
export function withFrame(store: Store, camId: string, frame: Frame): Store {
  return {
    ...store,
    cameras: store.cameras.map((c) =>
      c.id !== camId ? c : { ...c, frames: [...c.frames.filter((f) => f.file !== frame.file), frame].sort((a, b) => a.ts - b.ts) },
    ),
  };
}

export function runFrames(store: Store): { cam: Camera; frame: Frame }[] {
  return store.cameras.flatMap((cam) => cam.frames.filter((f) => f.origin === "run").map((frame) => ({ cam, frame })));
}

export function tally(cam: Camera, frame: Frame): Record<Status, number> {
  const n: Record<Status, number> = { empty: 0, wrong: 0, low: 0, ok: 0 };
  for (const a of cam.areas) if (frame.areas[a.id]) n[statusOf(frame.areas[a.id])]++;
  return n;
}

export function productName(store: Store, id: string): string {
  const known = store.products?.[id]?.name;
  if (known) return known;
  for (const c of store.cameras) for (const a of c.areas) if (a.productId === id) return a.product;
  return `#${id}`;
}

export const frameSrc = (store: Store, cam: Camera, frame: Frame) => `${store.base ?? ""}/frames/${cam.id}/${encodeURIComponent(frame.file)}`;

const fmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Lisbon" });
export const clock = (ts: number) => fmt.format(new Date(ts * 1000));

export function duration(seconds: number): string {
  const m = Math.round(seconds / 60);
  if (m < 50) return `${Math.max(m, 1)} min`;
  const h = Math.round(m / 60);
  return `${h} h`;
}

export function millis(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

export function bbox(quad: [number, number][], w: number, h: number, pad = 0.18) {
  const xs = quad.map((p) => p[0]);
  const ys = quad.map((p) => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const px = (x1 - x0) * pad, py = (y1 - y0) * pad;
  x0 = Math.max(0, x0 - px); y0 = Math.max(0, y0 - py);
  x1 = Math.min(w, x1 + px); y1 = Math.min(h, y1 + py);
  return { x: x0, y: y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) };
}

export function centroid(quad: [number, number][], w: number, h: number): [number, number] {
  const x = quad.reduce((s, p) => s + p[0], 0) / quad.length;
  const y = quad.reduce((s, p) => s + p[1], 0) / quad.length;
  return [Math.min(w - 14, Math.max(14, x)), Math.min(h - 14, Math.max(14, y))];
}

export const points = (quad: [number, number][]) => quad.map((q) => q.join(",")).join(" ");
