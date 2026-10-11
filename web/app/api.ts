import { AreaPred, Frame, Store } from "./lib";

export const STATIC_DEMO = process.env.NEXT_PUBLIC_DEMO === "true";

/** Where the inference server lives. Same origin when the server hosts the app; NEXT_PUBLIC_API
 *  (or ?api=http://localhost:PORT while developing) when the app runs under `next dev`. */
export function apiBase(): string {
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search).get("api");
    if (q && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(q)) return q;
  }
  return (process.env.NEXT_PUBLIC_API ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "")).replace(/\/$/, "");
}

export interface Health {
  ready: boolean;
  device: string;
  model: string;
  cameras: number;
  areas: number;
  emptyCompliant: boolean;
}

export type RunEvent =
  | { type: "frame"; camera: string; file: string; ms: number; cameraSource: Frame["cameraSource"]; warnings: string[]; frame: Frame }
  | { type: "skip"; file: string; reason: string }
  | { type: "done"; images: number; areas: number; ms: number }
  | { type: "error"; message?: string; detail?: string };

export interface Mistake {
  camera: string;
  file: string;
  area: string;
  field: "id" | "stock" | "missing";
  predicted: string | number | boolean | null;
  truth: string | number | boolean | object;
  points: number;
}
export interface Score {
  score: number;
  max: number;
  areas: number;
  id_correct: number;
  id_wrong: number;
  stock_correct: number;
  stock_below: number;
  stock_above: number;
  missing: number;
  mistakes: Mistake[];
}

async function fail(res: Response): Promise<never> {
  let text = "";
  try {
    const body = await res.text();
    try {
      const j = JSON.parse(body);
      text = typeof j.detail === "string" ? j.detail : j.message ?? body;
    } catch {
      text = body;
    }
  } catch {}
  throw new Error(text.slice(0, 300) || `The server answered ${res.status}`);
}

/** What the screen calls compliant is what the output file says: the server sends that verdict
 *  (it weighs in the chance that the slot is empty) next to the raw product match. */
function tidy(frame: Frame): Frame {
  for (const p of Object.values(frame.areas) as (AreaPred & { official?: { planogram_compliant?: boolean } })[])
    if (typeof p.official?.planogram_compliant === "boolean") p.ok = p.official.planogram_compliant;
  return frame;
}

/** The live store from the inference server, or the bundled snapshot when no server answers. */
export async function loadStore(): Promise<Store> {
  if (STATIC_DEMO) {
    const r = await fetch("/data/store.json");
    if (!r.ok) throw new Error("no shelf data");
    return { ...(await r.json()), base: "", live: false };
  }
  const base = apiBase();
  try {
    const r = await fetch(`${base}/api/store`, { cache: "no-store", signal: AbortSignal.timeout(30000) }); // the body is a few MB: a server that is down still fails at once
    if (r.ok && (r.headers.get("content-type") ?? "").includes("json")) {
      const s: Store = await r.json();
      for (const c of s.cameras) c.frames.forEach(tidy);
      return { ...s, base, live: true };
    }
  } catch {}
  const r = await fetch("/data/store.json");
  if (!r.ok) throw new Error("no shelf data");
  return { ...(await r.json()), base: "", live: false };
}

export interface CountBox {
  x: number;
  y: number;
  w: number;
  h: number;
  /** less than about half of the unit shows */
  partial: boolean;
}
export interface UnitCount {
  area: string;
  unit: "item" | "pack" | "bunch";
  count: number;
  partial: number;
  /** units of another product seen inside the slot, left out of the count */
  other: number;
  boxes: CountBox[];
  cached: boolean;
}
export interface CountPolicy {
  configured: boolean;
  /** productId -> unit, for the products the "Count units" button may count */
  enabled: Record<string, UnitCount["unit"]>;
}

let policy: Promise<CountPolicy | null> | null = null;
/** Which products may be counted; asked once per page load. null when the server does not offer counting. */
export function countPolicy(): Promise<CountPolicy | null> {
  policy ??= fetch(`${apiBase()}/api/count/policy`, { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return policy;
}

/** Visible units of one slot in one frame, with a box around each (vision model, on demand; the engine is not involved). */
export async function countArea(camera: string, file: string, area: string): Promise<UnitCount> {
  const r = await fetch(`${apiBase()}/api/count`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ camera, file, area }) });
  if (!r.ok) await fail(r);
  return r.json();
}

export async function loadHealth(): Promise<Health | null> {
  if (STATIC_DEMO) return null;
  try {
    const r = await fetch(`${apiBase()}/api/health`, { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export interface RipenessResult {
  stage_counts?: Record<"green" | "turning" | "ripe" | "very_ripe", number>;
  state: "green" | "turning" | "ripe" | "very_ripe" | "mixed" | "unclear" | "no_bananas";
  label: string;
  action: string;
  review: boolean;
  quality: "clear" | "limited" | "poor";
  cached: boolean;
}

const ripenessRequests = new Map<string, Promise<RipenessResult>>();
export function checkRipeness(camera: string, file: string, area: string): Promise<RipenessResult> {
  const base = apiBase(), key = JSON.stringify([base, camera, file, area]);
  const pending = ripenessRequests.get(key);
  if (pending) return pending;
  const request = (async () => {
    const r = await fetch(`${base}/api/ripeness`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ camera, file, area }) });
    if (!r.ok) await fail(r);
    return r.json() as Promise<RipenessResult>;
  })();
  ripenessRequests.set(key, request);
  void request.then(() => ripenessRequests.delete(key), () => ripenessRequests.delete(key));
  return request;
}

/** Read a newline-delimited JSON stream, one event per image as it finishes. */
async function stream(res: Response, onEvent: (e: RunEvent) => void) {
  if (!res.ok || !res.body) await fail(res);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const emit = (line: string) => {
    if (!line.trim()) return;
    let e: RunEvent;
    try {
      e = JSON.parse(line);
    } catch {
      return;
    }
    if (e.type === "error") throw new Error(e.message ?? e.detail ?? "The server stopped the run");
    if (e.type === "frame") tidy(e.frame);
    onEvent(e);
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (value) buf += decoder.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      emit(buf.slice(0, i));
      buf = buf.slice(i + 1);
    }
    if (done) break;
  }
  emit(buf);
}

export interface Upload {
  file: File;
  /** path relative to what was dropped, e.g. "6215/1751052241.jpg": the folder names the camera */
  path: string;
}

export type ShelfModel = "full" | "lite";

export async function analyzeFiles(items: Upload[], onEvent: (e: RunEvent) => void, signal?: AbortSignal, model: ShelfModel = "full") {
  const body = new FormData();
  body.append("model", model);
  for (const it of items) {
    body.append("files", it.file, it.file.name);
    body.append("paths", it.path);
  }
  await stream(await fetch(`${apiBase()}/api/analyze`, { method: "POST", body, signal }), onEvent);
}

export async function analyzeFolder(path: string, onEvent: (e: RunEvent) => void, signal?: AbortSignal, model: ShelfModel = "full") {
  const res = await fetch(`${apiBase()}/api/analyze-folder`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, model }), signal });
  await stream(res, onEvent);
}

export const predictionsUrl = (scope: "run" | "all", download = true) =>
  `${apiBase()}/api/predictions?scope=${scope}${download ? "&download=1" : ""}`;

export async function loadPredictions(scope: "run" | "all"): Promise<Record<string, Record<string, Record<string, unknown>>>> {
  const r = await fetch(predictionsUrl(scope, false), { cache: "no-store" });
  if (!r.ok) await fail(r);
  return r.json();
}

export async function scoreAgainst(annotations: string): Promise<Score> {
  const r = await fetch(`${apiBase()}/api/score`, { method: "POST", headers: { "Content-Type": "application/json" }, body: annotations });
  if (!r.ok) await fail(r);
  return r.json();
}

export async function resetRun(): Promise<void> {
  const r = await fetch(`${apiBase()}/api/reset`, { method: "POST" });
  if (!r.ok) await fail(r);
}

const IMAGE = /\.(jpe?g|png|webp|bmp)$/i;
const ZIP = /\.zip$/i;
const JUNK = /(^|\/)(\.|__MACOSX\/|Thumbs\.db$|desktop\.ini$)/;

export interface Picked {
  uploads: Upload[];
  /** an annotations.json found next to the images: its text, ready to score against */
  annotations: string | null;
  ignored: { file: string; reason: string }[];
}

/** Keep the images and archives, pull out an annotations file, name everything else. */
export async function sort(items: Upload[]): Promise<Picked> {
  const out: Picked = { uploads: [], annotations: null, ignored: [] };
  for (const it of items) {
    if (JUNK.test(it.path)) continue;
    if (IMAGE.test(it.path) || ZIP.test(it.path)) out.uploads.push(it);
    else if (/\.json$/i.test(it.path) && it.file.size < 5e6) {
      const text = await it.file.text();
      if (/"stock_value"|"planogram_compliant"/.test(text)) out.annotations = text;
      else out.ignored.push({ file: it.path, reason: "not an image" });
    } else out.ignored.push({ file: it.path, reason: "not an image" });
  }
  out.uploads.sort((a, b) => a.path.localeCompare(b.path, undefined, { numeric: true }));
  return out;
}

/** Everything inside a drop: loose files, and folders walked recursively with their relative paths. */
export async function fromDrop(dt: DataTransfer): Promise<Upload[]> {
  const entries = Array.from(dt.items ?? [])
    .map((it) => (it.kind === "file" ? it.webkitGetAsEntry?.() : null))
    .filter((e): e is FileSystemEntry => !!e);
  if (!entries.length) return Array.from(dt.files).map((file) => ({ file, path: file.name }));
  const out: Upload[] = [];
  const walk = async (entry: FileSystemEntry, prefix: string) => {
    if (entry.isFile) {
      const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
      out.push({ file, path: prefix + entry.name });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const e of batch) await walk(e, `${prefix}${entry.name}/`);
      }
    }
  };
  for (const e of entries) await walk(e, "");
  return out;
}

export const fromInput = (files: FileList | null): Upload[] =>
  Array.from(files ?? []).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
