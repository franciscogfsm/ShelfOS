"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Health, Mistake, Score, Upload, fromInput, predictionsUrl } from "./api";
import { Badges, Crop, FrameView } from "./components";
import { ACCENT, Camera, Frame, ORDER, STATUS, Status, Store, clock, millis, runFrames, statusOf, tally } from "./lib";

export interface RunState {
  phase: "idle" | "running" | "done" | "error";
  /** images sent, when known up front (not for archives or a folder read by the server) */
  expected: number | null;
  images: number;
  areas: number;
  ms: number | null;
  startedAt: number;
  skipped: { file: string; reason: string }[];
  /** "camera/file" in the order the answers arrived */
  order: string[];
  error?: string;
  /** an annotations.json that came along with the images */
  annotations?: string | null;
}

export const IDLE: RunState = { phase: "idle", expected: null, images: 0, areas: 0, ms: null, startedAt: 0, skipped: [], order: [] };

const LEVEL_NAME: Record<string, string> = { "0": "empty", "0.5": "half", "1": "full" };
const say = (m: Mistake, v: Mistake["predicted"] | Mistake["truth"]) =>
  v === null || v === undefined || typeof v === "object" ? "nothing" : m.field === "id" ? (v === true || v === "true" ? "compliant" : "not compliant") : LEVEL_NAME[String(v)] ?? String(v);

export function RunView({
  store, health, run, score, scoreError, onFiles, onFolder, onCancel, onOpen, onFocus, onPolicy, onScore, onReset,
}: {
  store: Store; health: Health | null; run: RunState; score: Score | null; scoreError: string | null;
  onFiles: (items: Upload[]) => void; onFolder: (path: string) => void; onCancel: () => void;
  onOpen: (cam: Camera, frame: Frame) => void; onFocus: (cam: Camera, frame: Frame, areaId: string) => void;
  onPolicy: (emptyCompliant: boolean) => void; onScore: (annotations: string) => void; onReset: () => void;
}) {
  const frames = useMemo(() => {
    const all = runFrames(store);
    const at = new Map(run.order.map((k, i) => [k, i]));
    const rank = (x: { cam: Camera; frame: Frame }) => at.get(`${x.cam.id}/${x.frame.file}`) ?? 1e9;
    return all.sort((a, b) => rank(a) - rank(b) || a.cam.id.localeCompare(b.cam.id) || a.frame.ts - b.frame.ts);
  }, [store, run.order]);
  const running = run.phase === "running";
  const elapsed = useElapsed(run.startedAt, running);
  const images = Math.max(run.images, running ? 0 : frames.length);
  const areas = running ? run.areas : frames.reduce((n, x) => n + Object.keys(x.frame.areas).length, 0);
  const total = running ? elapsed : run.ms ?? store.run?.ms ?? null;
  const timed = frames.filter((x) => typeof x.frame.ms === "number");
  const perImage = timed.length ? timed.reduce((s, x) => s + (x.frame.ms as number), 0) / timed.length : null;
  const counts = useMemo(() => {
    const n: Record<Status, number> = { empty: 0, wrong: 0, low: 0, ok: 0 };
    for (const x of frames) for (const p of Object.values(x.frame.areas)) n[statusOf(p)]++;
    return n;
  }, [frames]);
  const recognised = frames.filter((x) => x.frame.cameraSource === "auto").length;
  const fromMemory = frames.reduce((n, x) => n + Object.values(x.frame.areas).filter((p) => p.source === "memory").length, 0);
  const hasRun = frames.length > 0 || running;
  const emptyCompliant = store.emptyCompliant ?? true;

  return (
    <div className="run-workspace flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="eyebrow">SHELF INTELLIGENCE / IMAGE LAB</div>
          <h1 className="mt-2 text-3xl font-medium tracking-tight">New images. Clear answers.</h1>
          <p className="mt-1 text-sm text-muted max-w-2xl">
            Turn shelf images into stock levels, product checks, and a plan for what comes next.
          </p>
        </div>
        <ServerChip live={!!store.live} health={health} />
      </div>

      {!store.live ? (
        <div className="rounded-2xl border border-dashed border-line px-8 py-10 text-center">
          <div className="text-lg">The inference server is not running</div>
          <p className="mt-2 text-sm text-muted">
            This page is showing a saved snapshot of the reference day. To test new images, start ShelfOS with{" "}
            <code className="font-mono text-ok">python run.py</code> in the project folder and open the address it prints.
          </p>
        </div>
      ) : (
        <Dropzone compact={hasRun} busy={running} onFiles={onFiles} onFolder={onFolder} />
      )}

      {run.phase === "error" && (
        <div className="rounded-xl border border-empty/40 bg-empty/10 px-4 py-3 text-sm text-empty">
          The run stopped: {run.error}. {images > 0 ? `${images} image${images === 1 ? "" : "s"} finished before that and are kept below.` : "Nothing was analysed."}
        </div>
      )}

      {hasRun && (
        <section className="glass-card overflow-hidden">
          <div className="flex flex-wrap items-stretch">
            <Stat label="Images" value={String(images)} sub={running && run.expected ? `of ${run.expected}` : `${new Set(frames.map((x) => x.cam.id)).size} cameras`} />
            <Stat label="Planogram areas" value={String(areas)} sub="none missing from the file" />
            <Stat label="Total time" value={total === null ? "–" : millis(total)} sub={health ? `on ${health.device === "cuda" ? "the GPU" : health.device}` : "inference"} live={running} />
            <Stat label="Per image" value={perImage === null ? "–" : millis(perImage)} sub="crop, embed, decide" />
            <div className="flex-1 flex items-center justify-end gap-3 px-5 py-3">
              {running ? (
                <button onClick={onCancel} className="rounded-lg border border-line px-4 py-2.5 text-sm text-muted hover:text-white hover:border-white/25">
                  Stop
                </button>
              ) : (
                <a
                  href={predictionsUrl("run")}
                  download="predictions.json"
                  className="flex items-center gap-2.5 rounded-lg bg-ok px-5 py-3 text-sm font-semibold text-black hover:brightness-110 transition"
                >
                  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 1.5v8.5m0 0L4 6.6m3.5 3.4L11 6.6M2 13.2h11" /></svg>
                  Download predictions.json
                </a>
              )}
            </div>
          </div>
          <div className="h-[3px] bg-line">
            <div
              className={`h-full transition-[width] duration-200 ${running && !run.expected ? "shimmer" : ""}`}
              style={{ width: running ? (run.expected ? `${Math.min(100, (run.images / run.expected) * 100)}%` : "100%") : "100%", background: running ? ACCENT : STATUS.ok.color }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3 text-xs">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              {ORDER.map((s) => (
                <span key={s} className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: STATUS[s].color }} />
                  <span className="font-mono tabular-nums text-sm">{counts[s]}</span>
                  <span className="text-muted">{STATUS[s].label.toLowerCase()}</span>
                </span>
              ))}
            </div>
            {recognised > 0 && <span className="text-muted">{recognised} camera{recognised === 1 ? "" : "s"} recognised from the picture</span>}
            {fromMemory > 0 && <span className="text-low">⚠ {fromMemory} area{fromMemory === 1 ? "" : "s"} answered from the last known state</span>}
            <div className="flex-1" />
            <label className="flex items-center gap-2">
              <span className="text-muted" title="The brief does not say how an empty area is annotated. This switch rewrites planogram_compliant for the empty areas, on screen and in the file.">
                An empty slot counts as
              </span>
              <span className="flex rounded-md border border-line p-0.5">
                {[true, false].map((v) => (
                  <button key={String(v)} disabled={running} onClick={() => onPolicy(v)} className={`px-2.5 py-1 rounded transition-colors ${emptyCompliant === v ? "bg-raised text-white" : "text-muted hover:text-white"}`}>
                    {v ? "compliant" : "not compliant"}
                  </button>
                ))}
              </span>
            </label>
            <button onClick={onReset} disabled={running} className="text-muted hover:text-white disabled:opacity-40">
              Clear run
            </button>
          </div>
        </section>
      )}

      {hasRun && !running && <ScorePanel store={store} score={score} error={scoreError} found={run.annotations ?? null} onScore={onScore} onFocus={onFocus} />}

      {run.skipped.length > 0 && (
        <details className="glass-card px-4 py-3 text-xs">
          <summary className="cursor-pointer text-muted">
            {run.skipped.length} file{run.skipped.length === 1 ? "" : "s"} left out
          </summary>
          <ul className="mt-2 grid sm:grid-cols-2 gap-x-6 gap-y-1 font-mono text-[11px]">
            {run.skipped.slice(0, 60).map((s, i) => (
              <li key={i} className="truncate">
                <span className="text-white/80">{s.file}</span> <span className="text-muted">· {s.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {frames.length > 0 && (
        <div className="grid sm:grid-cols-2 2xl:grid-cols-3 gap-4">
          {frames.map(({ cam, frame }) => (
            <button
              key={`${cam.id}/${frame.file}`}
              onClick={() => onOpen(cam, frame)}
              className="arrive group relative text-left rounded-xl overflow-hidden border border-line bg-black transition-all hover:border-white/30 hover:-translate-y-0.5"
            >
              <FrameView store={store} cam={cam} frame={frame} compact />
              <div className="absolute inset-x-0 top-0 flex items-center justify-between p-2 bg-gradient-to-b from-black/70 to-transparent">
                <span className="flex items-center gap-2 rounded-md bg-black/60 px-2 py-1 font-mono text-[11px] backdrop-blur-sm">
                  <span className="size-1.5 rounded-full bg-accent" />
                  CAM {cam.id}
                  <span className="text-white/60">{clock(frame.ts)}</span>
                </span>
                <Badges n={tally(cam, frame)} />
              </div>
              <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 px-2.5 pb-2 pt-8 bg-gradient-to-t from-black/90 via-black/50 to-transparent font-mono text-[10px]">
                <span className="truncate text-white/70">{frame.file}</span>
                {frame.cameraSource === "auto" && <span className="shrink-0 rounded bg-accent/15 px-1.5 py-0.5 text-accent">camera recognised</span>}
                {!!frame.warnings?.length && (
                  <span className="shrink-0 rounded bg-low/15 px-1.5 py-0.5 text-low" title={frame.warnings.join("\n")}>
                    ⚠ {frame.warnings.length}
                  </span>
                )}
                <span className="flex-1" />
                {typeof frame.ms === "number" && <span className="shrink-0 text-white/70">{millis(frame.ms)}</span>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function useElapsed(startedAt: number, running: boolean) {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(performance.now()), 70);
    return () => clearInterval(id);
  }, [running]);
  return Math.max(0, now - startedAt);
}

function ServerChip({ live, health }: { live: boolean; health: Health | null }) {
  if (!live)
    return (
      <span className="shrink-0 flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs text-muted">
        <span className="size-2 rounded-full bg-muted" /> Snapshot · no server
      </span>
    );
  return (
    <span className="shrink-0 flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-xs">
      <span className="size-2 rounded-full bg-ok" />
      Server ready
      {health && (
        <span className="text-muted font-mono text-[11px]">
          · {health.device} · {health.cameras} cameras · {health.areas} areas
        </span>
      )}
    </span>
  );
}

function Stat({ label, value, sub, live }: { label: string; value: string; sub: string; live?: boolean }) {
  return (
    <div className="px-5 py-4 border-r border-line min-w-[128px]">
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className={`mt-1 font-mono text-[28px] leading-none tracking-tight tabular-nums ${live ? "text-accent" : ""}`}>{value}</div>
      <div className="mt-1.5 text-[11px] text-muted whitespace-nowrap">{sub}</div>
    </div>
  );
}

function Dropzone({ compact, busy, onFiles, onFolder }: { compact: boolean; busy: boolean; onFiles: (items: Upload[]) => void; onFolder: (path: string) => void }) {
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const [path, setPath] = useState("");
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const items = fromInput(e.target.files);
    e.target.value = "";
    if (items.length) onFiles(items);
  };
  const inputs = (
    <>
      <input ref={files} type="file" multiple accept="image/*,.zip,.json" className="hidden" data-pick="files" onChange={pick} />
      <input
        ref={(el) => {
          folder.current = el;
          el?.setAttribute("webkitdirectory", "");
        }}
        type="file"
        multiple
        className="hidden"
        data-pick="folder"
        onChange={pick}
      />
    </>
  );
  const byPath = (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (path.trim() && !busy) onFolder(path.trim().replace(/^"|"$/g, ""));
      }}
    >
      <input
        value={path}
        onChange={(e) => setPath(e.target.value)}
        placeholder="…or paste a folder path on this computer"
        spellCheck={false}
        className="flex-1 min-w-0 rounded-lg border border-line bg-ink px-3 py-2 text-xs font-mono placeholder:text-muted/70 focus:border-accent/60 focus:outline-none"
      />
      <button disabled={busy || !path.trim()} className="rounded-lg border border-line px-3 py-2 text-xs text-muted enabled:hover:text-white enabled:hover:border-white/25 disabled:opacity-40">
        Analyse folder
      </button>
    </form>
  );
  const buttons = (
    <>
      <button disabled={busy} onClick={() => folder.current?.click()} className="rounded-lg border border-accent/50 bg-accent/10 px-4 py-2 text-sm text-accent enabled:hover:bg-accent/20 disabled:opacity-40">
        Choose folder
      </button>
      <button disabled={busy} onClick={() => files.current?.click()} className="rounded-lg border border-line px-4 py-2 text-sm enabled:hover:border-white/30 disabled:opacity-40">
        Choose files
      </button>
    </>
  );
  if (compact)
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-line px-4 py-3">
        {inputs}
        <span className="text-xs text-muted shrink-0">Drop more images anywhere, or</span>
        {buttons}
        <div className="flex-1 min-w-[260px]">{byPath}</div>
      </div>
    );
  return (
    <div className="relative overflow-hidden rounded-2xl border border-dashed border-accent/40 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.07),transparent_60%)] px-5 sm:px-8 py-10">
      {inputs}
      <div className="mx-auto max-w-xl text-center">
        <div className="mx-auto size-12 grid place-items-center rounded-2xl border border-accent/40 bg-accent/10 text-accent">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13.5V3.5m0 0L6 7.4m4-3.9 4 3.9M3 13.5v2A1.5 1.5 0 0 0 4.5 17h11a1.5 1.5 0 0 0 1.5-1.5v-2" /></svg>
        </div>
        <div className="mt-4 text-xl font-medium tracking-tight">Drop a folder, images or a .zip anywhere on this page</div>
        <div className="mt-4 flex justify-center gap-2">{buttons}</div>
        <div className="mt-4">{byPath}</div>
      </div>
      <ul className="mx-auto mt-8 grid max-w-3xl sm:grid-cols-3 gap-6 text-xs text-muted leading-relaxed">
        <li>
          <div className="text-white mb-1">One folder per camera</div>
          <span className="font-mono text-[11px]">6215/1751052241.jpg</span>: the folder names the camera, the file name is the capture time.
        </li>
        <li>
          <div className="text-white mb-1">Loose files work too</div>
          Without a folder, ShelfOS recognises the camera from the picture itself.
        </li>
        <li>
          <div className="text-white mb-1">Nothing goes missing</div>
          An unreadable image is answered from the last known state, because a missing area costs 5 points.
        </li>
      </ul>
    </div>
  );
}

function ScorePanel({
  store, score, error, found, onScore, onFocus,
}: { store: Store; score: Score | null; error: string | null; found: string | null; onScore: (annotations: string) => void; onFocus: (cam: Camera, frame: Frame, areaId: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const choose = (
    <>
      <input
        ref={input}
        type="file"
        accept=".json,application/json"
        className="hidden"
        data-pick="annotations"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onScore(await f.text());
        }}
      />
      <button onClick={() => input.current?.click()} className="rounded-lg border border-line px-3 py-2 text-xs hover:border-white/30">
        {score ? "Score another annotations.json" : "Choose annotations.json"}
      </button>
    </>
  );
  if (!score)
    return (
      <section className="flex flex-wrap items-center gap-4 glass-card px-5 py-3.5">
        <div className="min-w-[240px] flex-1">
          <div className="text-sm">Have the ground truth? Score this run with the official rules</div>
          <div className="text-xs text-muted">
            {error ? <span className="text-empty">{error}</span> : "+1 per correct answer, −2 for a wrong identification or a stock level below the shelf, −3 for a stock level above it."}
          </div>
        </div>
        {found && (
          <button onClick={() => onScore(found)} className="rounded-lg border border-accent/50 bg-accent/10 px-3 py-2 text-xs text-accent hover:bg-accent/20">
            Score with the annotations.json from the folder
          </button>
        )}
        {choose}
      </section>
    );
  const rows: [string, number, number, Status][] = [
    ["Identification correct", score.id_correct, 1, "ok"],
    ["Identification wrong", score.id_wrong, -2, "wrong"],
    ["Stock level correct", score.stock_correct, 1, "ok"],
    ["Stock level below the real stock", score.stock_below, -2, "low"],
    ["Stock level above the real stock", score.stock_above, -3, "empty"],
  ];
  const find = (m: Mistake) => {
    const cam = store.cameras.find((c) => c.id === m.camera);
    const frame = cam?.frames.find((f) => f.file === m.file);
    const area = cam?.areas.find((a) => a.id === m.area);
    return cam && frame && area ? { cam, frame, area } : null;
  };
  const pct = score.max ? (score.score / score.max) * 100 : 0;
  const tone = STATUS[pct >= 70 ? "ok" : pct >= 40 ? "low" : "empty"].color;
  return (
    <section className="glass-card overflow-hidden">
      <div className="grid lg:grid-cols-[auto_1fr]">
        <div className="px-6 py-5 lg:border-r border-line">
          <div className="text-[10px] uppercase tracking-[0.14em] text-muted">Official score</div>
          <div className="mt-1 font-mono tabular-nums tracking-tight">
            <span className="text-5xl" style={{ color: tone }}>{score.score}</span>
            <span className="text-xl text-muted"> / {score.max}</span>
          </div>
          <div className="mt-2 h-1.5 w-48 rounded bg-line overflow-hidden">
            <div className="h-full" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: tone }} />
          </div>
          <div className="mt-2 text-xs text-muted">
            {pct.toFixed(1)}% of the maximum · {score.areas} annotated areas
            {score.missing > 0 && <span className="text-empty"> · {score.missing} missing from the output</span>}
          </div>
          <div className="mt-4">{choose}</div>
        </div>
        <table className="text-xs self-center mx-6 my-4">
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.12em] text-muted text-right">
              <th className="text-left font-normal pb-2">Case</th>
              <th className="font-normal pb-2 w-20">Areas</th>
              <th className="font-normal pb-2 w-24">Points each</th>
              <th className="font-normal pb-2 w-20">Points</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map(([name, n, each, tone]) => (
              <tr key={name} className="border-t border-line/60 text-right">
                <td className="py-1.5 text-left font-sans">
                  <span className="inline-block size-2 rounded-full mr-2" style={{ background: STATUS[tone].color }} />
                  {name}
                </td>
                <td>{n}</td>
                <td className="text-muted">{each > 0 ? `+${each}` : `−${-each}`}</td>
                <td style={{ color: each > 0 ? STATUS.ok.color : n ? STATUS[tone].color : undefined }}>{n * each > 0 ? `+${n * each}` : n * each < 0 ? `−${-n * each}` : "0"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {score.mistakes.length > 0 && (
        <details className="border-t border-line" open={score.mistakes.length <= 12}>
          <summary className="cursor-pointer px-6 py-2.5 text-xs text-muted hover:text-white">
            {score.mistakes.length} answer{score.mistakes.length === 1 ? "" : "s"} that lost points
          </summary>
          <div className="grid sm:grid-cols-2 2xl:grid-cols-3 gap-px bg-line/60 border-t border-line/60">
            {score.mistakes.slice(0, 90).map((m, i) => {
              const hit = find(m);
              return (
                <button key={i} disabled={!hit} onClick={() => hit && onFocus(hit.cam, hit.frame, hit.area.id)} className="flex items-center gap-3 bg-panel px-4 py-2 text-left enabled:hover:bg-raised">
                  {hit ? <Crop store={store} cam={hit.cam} frame={hit.frame} area={hit.area} className="size-10 shrink-0 rounded-md" /> : <span className="size-10 shrink-0 rounded-md bg-line" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs">{hit?.area.product ?? m.area}</span>
                    <span className="block truncate text-[11px] text-muted">
                      {m.field === "missing" ? (
                        "Missing from the output"
                      ) : (
                        <>
                          {m.field === "id" ? "Planogram" : "Stock"}: said <span className="text-white">{say(m, m.predicted)}</span>, was <span className="text-white">{say(m, m.truth)}</span>
                        </>
                      )}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted">{m.area}</span>
                  <span className="shrink-0 font-mono text-xs text-empty w-6 text-right">{m.points}</span>
                </button>
              );
            })}
          </div>
        </details>
      )}
    </section>
  );
}
