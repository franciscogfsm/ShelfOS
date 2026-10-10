"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Health, RunEvent, Score, Upload, analyzeFiles, analyzeFolder, fromDrop, loadHealth, loadStore, resetRun, scoreAgainst, setPolicy, sort } from "./api";
import { AreaDetail, AreaList, Badges, CameraStage, Crop, DayStrip, FrameView, Kpi } from "./components";
import { Camera, Frame, ISSUES, LEVEL_VALUE, ORDER, STATUS, Status, Store, Task, clock, confidence, duration, frameAt, since, statusOf, tally, tasksAt, timeline, withFrame } from "./lib";
import { IDLE, RunState, RunView } from "./run";
import Loading from "./loading";

type View = "tasks" | "wall" | "camera" | "run";
type Tab = "tasks" | "products";
// "tasks" is a view of its own on a phone; on a wide screen the work queue is always on the right
const VIEWS: [View, string][] = [["tasks", "Tasks"], ["wall", "Store wall"], ["camera", "Camera"], ["run", "Test images"]];
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export default function Page() {
  const [raw, setStore] = useState<Store | null>(null);
  const [failed, setFailed] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [ts, setTs] = useState(0);
  const [view, setView] = useState<View>("wall");
  const [camId, setCamId] = useState("");
  const [areaId, setAreaId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");
  const [tab, setTab] = useState<Tab>("tasks");
  const [done, setDone] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<{ key: string; product: string } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [run, setRun] = useState<RunState>(IDLE);
  const [score, setScore] = useState<Score | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [truth, setTruth] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // cameras that have at least one image; a camera with none has nothing to show yet
  const store = useMemo(() => (raw ? { ...raw, cameras: raw.cameras.filter((c) => c.frames.length) } : null), [raw]);
  const line = useMemo(() => (store ? timeline(store) : { min: 0, max: 1, latest: 1 }), [store]);
  const tasks = useMemo(() => (store ? tasksAt(store, ts) : []), [store, ts]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    loadStore()
      .then((s) => {
        setStore(s);
        const cams = s.cameras.filter((c) => c.frames.length);
        setCamId(cams.find((c) => c.id === q.get("cam"))?.id ?? cams[0]?.id ?? "");
        setAreaId(q.get("area"));
        setTs(Number(q.get("ts")) || timeline({ ...s, cameras: cams }).latest);
        const v = q.get("view") as View | null;
        setView(!cams.length ? "run" : v && VIEWS.some(([id]) => id === v) ? v : window.innerWidth < 1024 ? "tasks" : "wall");
        if (s.run) setRun({ ...IDLE, phase: "done", images: s.run.images, areas: s.run.areas, ms: s.run.ms });
        if (s.live) loadHealth().then(setHealth);
      })
      .catch(() => setFailed(true));
  }, []);

  // ── the day, played back ───────────────────────────────────────────────────────
  const isLive = ts >= line.latest;
  const playingNow = playing && !isLive;
  useEffect(() => {
    if (!playingNow) return;
    const id = setInterval(() => setTs((t) => (t + 600 >= line.max ? line.latest : t + 600)), 110);
    return () => clearInterval(id);
  }, [playingNow, line.max, line.latest]);

  const scrub = useCallback((t: number) => {
    setPlaying(false);
    setTs(t);
  }, []);
  const togglePlay = useCallback(() => {
    if (playingNow) return setPlaying(false);
    if (isLive) setTs(line.min);
    setPlaying(true);
  }, [playingNow, isLive, line.min]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        const dir = e.key === "ArrowLeft" ? -1 : 1;
        setPlaying(false);
        setTs((t) => {
          const next = Math.min(t, line.max) + dir * 3600;
          return next >= line.max ? line.latest : Math.max(line.min, next);
        });
      } else if (e.key === " ") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "Escape") {
        // first Esc closes the area, the next one goes back to the wall
        if (areaId) setAreaId(null);
        else setView("wall");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [line.min, line.max, line.latest, togglePlay, areaId]);

  // ── testing new images ─────────────────────────────────────────────────────────
  const begin = useCallback(async (job: (on: (e: RunEvent) => void, signal: AbortSignal) => Promise<void>, expected: number | null, seed: Partial<RunState>) => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setView("run");
    setPlaying(false);
    setScore(null);
    setScoreError(null);
    setRun((r) => ({ ...IDLE, phase: "running", expected, startedAt: performance.now(), order: r.order, annotations: seed.annotations ?? r.annotations, skipped: seed.skipped ?? [] }));
    let newest = 0;
    const finish = (extra: Partial<RunState>) => setRun((r) => (r.phase === "running" ? { ...r, phase: "done", ms: Math.round(performance.now() - r.startedAt), ...extra } : r));
    try {
      await job((e) => {
        if (e.type === "frame") {
          const frame: Frame = { ...e.frame, origin: "run", ms: e.ms, cameraSource: e.cameraSource, warnings: e.warnings ?? [] };
          const key = `${e.camera}/${frame.file}`;
          newest = Math.max(newest, frame.ts);
          setStore((s) => s && withFrame(s, e.camera, frame));
          setRun((r) => ({ ...r, images: r.images + 1, areas: r.areas + Object.keys(frame.areas).length, order: [...r.order.filter((k) => k !== key), key] }));
        } else if (e.type === "skip") setRun((r) => ({ ...r, skipped: [...r.skipped, { file: e.file, reason: e.reason }] }));
        else if (e.type === "done") setRun((r) => ({ ...r, phase: "done", ms: e.ms }));
      }, ctrl.signal);
      finish({});
    } catch (err) {
      if (ctrl.signal.aborted) finish({});
      else setRun((r) => ({ ...r, phase: "error", error: message(err) }));
    }
    if (newest) setTs(newest);
  }, []);

  const doScore = useCallback(async (annotations: string) => {
    setScoreError(null);
    try {
      setScore(await scoreAgainst(annotations));
      setTruth(annotations);
    } catch (err) {
      setScore(null);
      setScoreError(`Could not score that file: ${message(err)}`);
    }
  }, []);

  const hasRun = !!raw?.cameras.some((c) => c.frames.some((f) => f.origin === "run"));
  const startFiles = useCallback(
    async (items: Upload[]) => {
      setView("run");
      if (!raw?.live) return;
      const picked = await sort(items);
      if (!picked.uploads.length) {
        if (picked.annotations && hasRun) return doScore(picked.annotations);
        return setRun((r) => ({ ...r, phase: "error", error: "there were no images in what was dropped", skipped: picked.ignored }));
      }
      const archive = picked.uploads.some((u) => /\.zip$/i.test(u.path));
      begin((on, signal) => analyzeFiles(picked.uploads, on, signal), archive ? null : picked.uploads.length, { annotations: picked.annotations, skipped: picked.ignored });
    },
    [raw?.live, hasRun, begin, doScore],
  );
  const startFolder = useCallback((path: string) => begin((on, signal) => analyzeFolder(path, on, signal), null, {}), [begin]);

  const refresh = useCallback(async () => {
    const s = await loadStore();
    setStore(s);
    return s;
  }, []);
  const changePolicy = useCallback(
    async (emptyCompliant: boolean) => {
      try {
        await setPolicy(emptyCompliant);
        await refresh();
        if (truth) await doScore(truth);
      } catch (err) {
        setScoreError(`Could not change the rule: ${message(err)}`);
      }
    },
    [refresh, truth, doScore],
  );
  const clearRun = useCallback(async () => {
    abort.current?.abort();
    try {
      await resetRun();
      const s = await refresh();
      setTs(timeline({ ...s, cameras: s.cameras.filter((c) => c.frames.length) }).latest);
    } catch {}
    setRun(IDLE);
    setScore(null);
    setScoreError(null);
    setTruth(null);
  }, [refresh]);

  // dropping files anywhere on the page starts a test run
  useEffect(() => {
    let depth = 0;
    const files = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!files(e)) return;
      depth++;
      setDragging(true);
    };
    const over = (e: DragEvent) => {
      if (files(e)) e.preventDefault();
    };
    const leave = (e: DragEvent) => {
      if (!files(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      if (!files(e) || !e.dataTransfer) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      fromDrop(e.dataTransfer).then(startFiles);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [startFiles]);

  if (failed)
    return (
      <div className="h-full grid place-items-center text-sm text-muted">
        <div className="max-w-md text-center leading-relaxed">
          No shelf data yet. Start ShelfOS with <code className="font-mono text-ok">python run.py</code> in the project folder, then reload.
        </div>
      </div>
    );
  if (!store) return <Loading />;

  const blank = store.cameras.length === 0;
  const shown = view === "tasks" ? "wall" : view; // what the main pane shows on a wide screen
  const cam = store.cameras.find((c) => c.id === camId) ?? store.cameras[0];
  const frame = cam && frameAt(cam, ts);
  const counts = Object.fromEntries(ORDER.map((s) => [s, tasks.filter((t) => t.status === s).length])) as Record<Status, number>;
  const open = tasks.filter((t) => t.status !== "ok" && !done.has(t.key));
  const queue = open.filter((t) => filter === "all" || t.status === filter);
  const total = tasks.length || 1;
  const selected = areaId && cam ? cam.areas.find((a) => a.id === areaId) : undefined;

  const openFrame = (c: Camera, f: Frame, area: string | null = null) => {
    setPlaying(false);
    setCamId(c.id);
    setAreaId(area);
    setTs(f.ts);
    setView("camera");
  };
  const focus = (t: Task) => {
    setCamId(t.cam.id);
    setAreaId(t.area.id);
    setView("camera");
  };
  const toggleDone = (key: string) => {
    const task = tasks.find((t) => t.key === key);
    if (task && !done.has(key)) setNotice({ key, product: task.area.product });
    setDone((d) => {
      const n = new Set(d);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  };

  return (
    <div className={`app-shell h-full grid ${blank ? "grid-rows-[auto_1fr]" : "grid-rows-[auto_auto_1fr]"}`}>
      {/* ── top bar ───────────────────────────────────────────── */}
      <header className="app-header flex flex-wrap items-center gap-x-6 gap-y-2 px-4 lg:px-6 py-2.5 lg:py-0 lg:h-18 border-b border-line bg-panel/80 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="brand-mark"><Logo /></div>
          <span className="text-[17px] font-semibold tracking-tight">
            Shelf<span className="text-ok">OS</span>
          </span>
          <span className="hidden xl:inline text-xs text-muted border-l border-line pl-3">
            {store.store} · {store.section}
          </span>
        </div>
        <div className="main-nav order-last lg:order-none flex w-full lg:w-auto rounded-lg border border-line p-0.5 text-xs">
          {VIEWS.filter(([v]) => !blank || v === "run").map(([v, name]) => (
            <button
              key={v}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`flex flex-1 lg:flex-none items-center justify-center gap-1.5 px-3 py-1.5 rounded-md whitespace-nowrap transition-colors ${v === "tasks" ? "lg:hidden" : ""} ${view === v ? (v === "run" ? "bg-accent/15 text-accent" : "bg-raised text-white") : v === "wall" && view === "tasks" ? "text-muted lg:bg-raised lg:text-white" : v === "run" ? "text-accent hover:bg-accent/10" : "text-muted hover:text-white"}`}
            >
              {v === "run" && (
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8V1.5m0 0L3.5 4M6 1.5 8.5 4M1.5 8v1.5a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V8" /></svg>
              )}
              {name}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {!blank && (
          <div className="hidden md:flex gap-1.5">
            {ORDER.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(filter === s ? "all" : s)}
                className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors ${filter === s ? "bg-raised" : "border-line hover:border-white/20"}`}
                style={filter === s ? { borderColor: STATUS[s].color } : undefined}
              >
                <span className="size-2 rounded-full" style={{ background: STATUS[s].color, boxShadow: `0 0 10px ${STATUS[s].color}` }} />
                <span className="font-mono tabular-nums text-sm">{counts[s]}</span>
                <span className="hidden xl:inline text-muted">{STATUS[s].label}</span>
              </button>
            ))}
          </div>
        )}
      </header>

      {/* ── the day ───────────────────────────────────────────── */}
      {!blank && (
        <div className="timeline-bar flex items-center gap-3 lg:gap-4 px-4 lg:px-6 py-3 border-b border-line bg-panel/40">
          <button onClick={togglePlay} aria-label={playingNow ? "Pause" : "Play the day"} className="size-9 shrink-0 grid place-items-center rounded-full border border-line hover:border-ok/60 hover:text-ok transition-colors">
            {playingNow ? (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><rect x="1.5" y="1" width="3" height="10" rx="1" /><rect x="7.5" y="1" width="3" height="10" rx="1" /></svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M2.5 1.2v9.6a.6.6 0 0 0 .9.5l8-4.8a.6.6 0 0 0 0-1L3.4.7a.6.6 0 0 0-.9.5Z" /></svg>
            )}
          </button>
          <div className="w-[76px] lg:w-[92px] shrink-0">
            <div className="font-mono text-xl lg:text-2xl leading-none tabular-nums tracking-tight">{clock(ts)}</div>
            <div className={`mt-1 text-[10px] uppercase tracking-[0.14em] ${isLive ? "text-ok" : "text-muted"}`}>{isLive ? "● Latest" : "History"}</div>
          </div>
          <DayStrip store={store} ts={ts} line={line} onChange={scrub} />
          <button onClick={() => scrub(line.latest)} disabled={isLive} className="hidden sm:block shrink-0 text-xs rounded-lg border border-line px-3 py-2 text-muted enabled:hover:text-white enabled:hover:border-white/25 disabled:opacity-40">
            Jump to latest
          </button>
        </div>
      )}

      <div className={`grid min-h-0 ${blank ? "" : "lg:grid-cols-[minmax(0,1fr)_384px]"}`}>
        {/* ── main ─────────────────────────────────────────────── */}
        <main className={`workspace min-h-0 min-w-0 overflow-y-auto p-4 lg:p-7 ${view === "tasks" && !blank ? "hidden lg:block" : ""}`}>
          <div key={shown} className="view-enter">
          {shown === "run" || blank ? (
            <RunView
              store={store}
              health={health}
              run={run}
              score={score}
              scoreError={scoreError}
              onFiles={startFiles}
              onFolder={startFolder}
              onCancel={() => abort.current?.abort()}
              onOpen={openFrame}
              onFocus={(c, f, a) => openFrame(c, f, a)}
              onPolicy={changePolicy}
              onScore={doScore}
              onReset={clearRun}
            />
          ) : shown === "wall" ? (
            <div className="flex flex-col gap-5">
              <section className="overview-heading">
                <div>
                  <div className="eyebrow"><span /> SHELF INTELLIGENCE / OVERVIEW</div>
                  <h1>Every shelf. <span>In sight.</span></h1>
                  <p>{store.store} · {store.section} <span className="heading-divider">/</span> A clear picture. A smarter shift.</p>
                </div>
                <div className="snapshot-chip"><span className="status-beacon" />{isLive ? "Latest snapshot" : "Historical snapshot"}<span className="font-mono">{clock(ts)}</span></div>
              </section>
              <div className="metrics-grid grid grid-cols-2 xl:grid-cols-4 gap-3">
                <Kpi label="On the shelf" value={`${Math.round(((total - counts.empty) / total) * 100)}%`} sub={`${total - counts.empty} of ${total} areas have product`} tone={counts.empty ? "empty" : "ok"} />
                <Kpi label="Fully stocked" value={`${Math.round((tasks.filter((t) => t.pred.level === "full").length / total) * 100)}%`} sub={`${counts.low} running low`} tone={counts.low ? "low" : "ok"} />
                <Kpi label="Planogram match" value={`${Math.round(((total - counts.wrong) / total) * 100)}%`} sub={counts.wrong ? `${counts.wrong} holding the wrong product` : "everything in its place"} tone={counts.wrong ? "wrong" : "ok"} />
                <Kpi label="To do now" value={String(open.length)} sub={done.size ? `${done.size} done this shift` : "open tasks across the store"} tone={open.length ? "accent" : "ok"} />
              </div>
              <div className="section-heading"><div><span className="eyebrow">VISUAL MONITORING</span><h2>Store wall <span>{store.cameras.length.toString().padStart(2, "0")}</span></h2></div><span className="text-xs text-muted">Select a camera to inspect <span aria-hidden="true">↗</span></span></div>
              <div className="camera-grid grid sm:grid-cols-2 2xl:grid-cols-3 gap-4">
                {store.cameras.map((c) => {
                  const f = frameAt(c, ts);
                  const n = tally(c, f);
                  const worst = ISSUES.find((s) => n[s]) ?? "ok";
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setCamId(c.id);
                        setAreaId(null);
                        setView("camera");
                      }}
                      className="camera-card group relative text-left rounded-xl overflow-hidden border border-line bg-black transition-all hover:border-white/30 hover:-translate-y-0.5 hover:shadow-[0_18px_50px_-20px_rgba(47,224,160,0.35)]"
                    >
                      <div className="camera-caption"><span><svg className="camera-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="3" /><path d="m16 10 5-3v10l-5-3" /></svg> Camera {c.id}</span><span>{c.areas.length} areas <span className="camera-arrow" aria-hidden="true">↗</span></span></div>
                      <div className="relative camera-image">
                      <FrameView store={store} cam={c} frame={f} filter={filter} compact />
                      <div className="absolute inset-x-0 top-0 flex items-center justify-between p-2 bg-gradient-to-b from-black/70 to-transparent">
                        <span className="flex items-center gap-2 rounded-md bg-black/60 px-2 py-1 font-mono text-[11px] backdrop-blur-sm">
                          <span className="size-1.5 rounded-full" style={{ background: STATUS[worst].color, boxShadow: `0 0 8px ${STATUS[worst].color}` }} />
                          CAM {c.id}
                          <span className="text-white/60">{clock(f.ts)}</span>
                          {f.origin === "run" && <span className="text-accent">tested</span>}
                        </span>
                        <Badges n={n} />
                      </div>
                      <div className="absolute inset-x-0 bottom-0 flex gap-[3px] px-2.5 pb-2.5 pt-6 bg-gradient-to-t from-black/85 to-transparent">
                        {c.areas.map((a) => {
                          const p = f.areas[a.id];
                          const s = p ? statusOf(p) : "ok";
                          return <span key={a.id} className="h-1 flex-1 rounded-sm" style={{ background: STATUS[s].color, opacity: s === "ok" ? 0.45 : 1 }} />;
                        })}
                      </div>
                      </div>
                      <div className="camera-footer"><span style={{ color: STATUS[worst].color }}><span aria-hidden="true">● </span>{worst === "ok" ? "All areas in good shape" : `${n.empty + n.wrong + n.low} areas need attention`}</span><span>Inspect feed <span aria-hidden="true">→</span></span></div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex gap-2 overflow-x-auto pb-1">
                {store.cameras.map((c) => {
                  const n = tally(c, frameAt(c, ts));
                  const worst = ISSUES.find((s) => n[s]) ?? "ok";
                  const todo = n.empty + n.wrong + n.low;
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setCamId(c.id);
                        setAreaId(null);
                      }}
                      className={`shrink-0 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-mono transition-colors ${c.id === cam.id ? "border-ok/70 bg-ok/10 text-white" : "border-line text-muted hover:text-white hover:border-white/25"}`}
                    >
                      <span className="size-1.5 rounded-full" style={{ background: STATUS[worst].color }} />
                      {c.id}
                      {todo > 0 && <span style={{ color: STATUS[worst].color }}>{todo}</span>}
                    </button>
                  );
                })}
              </div>
              <div key={cam.id} className="camera-detail-enter grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
                <CameraStage store={store} cam={cam} frame={frame} areaId={areaId} filter={filter} onSelect={setAreaId} />
                {selected && frame.areas[selected.id] ? (
                  <AreaDetail key={selected.id} store={store} cam={cam} frame={frame} area={selected} onPick={scrub} onClose={() => setAreaId(null)} />
                ) : (
                  <AreaList cam={cam} frame={frame} onSelect={setAreaId} />
                )}
              </div>
            </div>
          )}
          </div>
        </main>

        {/* ── work queue ───────────────────────────────────────── */}
        {!blank && (
          <aside className={`task-panel ${view === "tasks" ? "flex" : "hidden"} lg:flex border-l border-line min-h-0 flex-col bg-panel`}>
            <div className="px-5 pt-4 border-b border-line">
              <div className="flex items-end justify-between">
                <div>
                  <div className="eyebrow">YOUR NEXT MOVES · {clock(ts)}</div>
                  <div className="mt-1 text-xl font-medium tracking-tight">
                    {open.length ? (
                      <>
                        {open.length} <span className="text-muted">task{open.length === 1 ? "" : "s"} to tackle</span>
                      </>
                    ) : (
                      <span className="text-ok">All shelves compliant</span>
                    )}
                  </div>
                </div>
                {done.size > 0 && (
                  <button onClick={() => { setDone(new Set()); setNotice(null); }} className="text-[11px] text-muted hover:text-white mb-1">
                    {done.size} done · reset
                  </button>
                )}
              </div>
              <div className="mt-3 flex gap-5 text-xs">
                {(["tasks", "products"] as Tab[]).map((t) => (
                  <button key={t} onClick={() => setTab(t)} className={`pb-2.5 border-b-2 -mb-px transition-colors ${tab === t ? "border-ok text-white" : "border-transparent text-muted hover:text-white"}`}>
                    {t === "tasks" ? "Tasks" : "Stock by product"}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              <div key={tab} className="queue-enter">
              {tab === "tasks" ? (
                <>
                  {ISSUES.map((s) => {
                    const group = queue.filter((t) => t.status === s);
                    if (!group.length) return null;
                    return (
                      <section key={s}>
                        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-2 bg-panel/95 backdrop-blur text-[11px] border-b border-line/60">
                          <span className="font-medium uppercase tracking-[0.12em]" style={{ color: STATUS[s].color }}>
                            {STATUS[s].action}
                          </span>
                          <span className="font-mono text-muted">
                            {group.length} {STATUS[s].label.toLowerCase()}
                          </span>
                        </div>
                        {group.map((t) => {
                          const held = Math.max(ts, t.frame.ts) - since(t.cam, t.area.id, t.frame);
                          return (
                            <div key={t.key} className={`task-row group flex items-center gap-3 pl-5 pr-3 py-2.5 border-b border-line/50 transition-colors ${t.area.id === areaId && shown === "camera" ? "bg-raised" : "hover:bg-raised/60"}`}>
                              <button onClick={() => focus(t)} className="flex items-center gap-3 min-w-0 flex-1 text-left">
                                <div className="relative shrink-0">
                                  <Crop store={store} cam={t.cam} frame={t.frame} area={t.area} className="w-14 h-14 rounded-lg" />
                                  <span className="absolute -left-1 -top-1 size-4 grid place-items-center rounded-full text-[10px] font-bold text-black" style={{ background: STATUS[s].color }}>
                                    {STATUS[s].glyph}
                                  </span>
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="truncate text-sm">{t.area.product}</div>
                                  <div className="text-[11px] text-muted">
                                    {STATUS[s].hint}
                                    {held >= 60 && ` · for ${duration(held)}`}
                                  </div>
                                  <div className="text-[10px] text-muted/80 font-mono">
                                    cam {t.cam.id} · slot {t.area.id.split("_")[1]} · {Math.round(confidence(t.pred) * 100)}% sure
                                  </div>
                                </div>
                              </button>
                              <button
                                onClick={() => toggleDone(t.key)}
                                aria-label="Mark done"
                                title="Mark done"
                                className="size-8 shrink-0 grid place-items-center rounded-full border border-line text-muted hover:border-ok hover:text-ok hover:bg-ok/10 transition-colors"
                              >
                                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m2.5 7 2.8 2.8 5.2-6" /></svg>
                              </button>
                            </div>
                          );
                        })}
                      </section>
                    );
                  })}
                  {queue.length === 0 && <div className="px-5 py-10 text-sm text-muted text-center">Nothing to do in this view.</div>}
                </>
              ) : (
                <Products tasks={tasks} onPick={focus} />
              )}
              </div>
            </div>
            <div className="px-5 py-2.5 border-t border-line text-[10px] text-muted font-mono flex justify-between">
              <span className="hidden lg:inline">← → hour · space play · esc wall</span>
              <span>
                {store.cameras.length} cams · {total} areas
              </span>
            </div>
          </aside>
        )}
      </div>

      {notice && (
        <div className="completion-toast" role="status">
          <span className="toast-check" aria-hidden="true">✓</span>
          <div><strong>Task complete</strong><span>{notice.product}</span></div>
          <button onClick={() => {
            setDone((d) => { const next = new Set(d); next.delete(notice.key); return next; });
            setNotice(null);
          }}>Undo</button>
        </div>
      )}
      {dragging && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/85 backdrop-blur-sm pointer-events-none">
          <div className="rounded-3xl border-2 border-dashed border-accent px-16 py-12 text-center shadow-[0_0_120px_-20px_rgba(34,211,238,0.6)]">
            <div className="text-2xl font-medium tracking-tight">Drop to analyse</div>
            <div className="mt-2 text-sm text-muted">A folder, images or a .zip. Add annotations.json to score the run.</div>
          </div>
        </div>
      )}
    </div>
  );
}

/** The brief: stock is counted per area and then added up per product. */
function Products({ tasks, onPick }: { tasks: Task[]; onPick: (t: Task) => void }) {
  const rows = useMemo(() => {
    const by = new Map<string, Task[]>();
    for (const t of tasks) by.set(t.area.productId, [...(by.get(t.area.productId) ?? []), t]);
    return [...by.values()]
      .map((ts) => ({ ts, name: ts[0].area.product, stock: ts.reduce((s, t) => s + LEVEL_VALUE[t.pred.level], 0) / ts.length }))
      .sort((a, b) => a.stock - b.stock || a.name.localeCompare(b.name));
  }, [tasks]);
  return (
    <div>
      {rows.map((r) => {
        const color = r.stock <= 0.01 ? STATUS.empty.color : r.stock < 0.75 ? STATUS.low.color : STATUS.ok.color;
        const worst = r.ts[0];
        return (
          <button key={worst.area.productId} onClick={() => onPick(worst)} className="w-full text-left px-5 py-2.5 border-b border-line/50 hover:bg-raised/60 transition-colors">
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-sm">{r.name}</span>
              <span className="font-mono text-xs tabular-nums" style={{ color }}>
                {Math.round(r.stock * 100)}%
              </span>
            </div>
            <div className="mt-1.5 flex gap-[3px]">
              {r.ts
                .slice()
                .sort((a, b) => a.area.id.localeCompare(b.area.id, undefined, { numeric: true }))
                .map((t) => (
                  <span key={t.area.id} className="h-1.5 flex-1 max-w-10 rounded-sm bg-line overflow-hidden" title={`${t.area.id} · ${t.pred.level}`}>
                    <span className="block h-full" style={{ width: `${LEVEL_VALUE[t.pred.level] * 100}%`, background: t.pred.ok ? STATUS[t.pred.level === "full" ? "ok" : "low"].color : STATUS.wrong.color }} />
                  </span>
                ))}
            </div>
            <div className="mt-1 text-[10px] text-muted font-mono">
              {r.ts.length} slot{r.ts.length === 1 ? "" : "s"} · cam {[...new Set(r.ts.map((t) => t.cam.id))].join(", ")}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
      <rect x="1" y="1" width="20" height="20" rx="6" stroke="#2fe0a0" strokeOpacity=".5" />
      <rect x="5" y="6" width="12" height="2.2" rx="1.1" fill="#2fe0a0" />
      <rect x="5" y="10" width="8" height="2.2" rx="1.1" fill="#ffb938" />
      <rect x="5" y="14" width="3" height="2.2" rx="1.1" fill="#ff5d73" />
    </svg>
  );
}
