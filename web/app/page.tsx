"use client";

import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Health, RunEvent, Score, ShelfModel, Upload, analyzeFiles, analyzeFolder, fromDrop, loadHealth, loadStore, resetRun, scoreAgainst, sort } from "./api";
import { AreaDetail, AreaList, Badges, CameraStage, CountUp, Crop, DayStrip, FrameView, Kpi } from "./components";
import { Camera, Frame, ISSUES, LEVEL_VALUE, ORDER, STATUS, Status, Store, Task, byImpact, clock, confidence, duration, frameAt, gain, since, statusOf, storeScore, tally, tasksAt, timeline, withFrame } from "./lib";
import { IDLE, RunState, RunView } from "./run";
import Loading from "./loading";
import { Search } from "./search";
import { Analytics } from "./analytics";
import { ThemeToggle } from "./theme";
import { ProductImage, preloadProductImages } from "./product-image";
import { ShelfAssistant } from "./assistant";
import { Pace, paceAt } from "./forecast";

type View = "tasks" | "wall" | "camera" | "analytics" | "run";
type Tab = "tasks" | "products";
const VIEWS: [View, string][] = [["tasks", "Tasks"], ["wall", "Store wall"], ["camera", "Camera"], ["analytics", "Analytics"], ["run", "Test images"]];
const NAV_ICON: Record<View, React.ReactNode> = {
  tasks: <path d="M4 6.5 5.5 8 8 5m3 1.5h9M4 12.5l1.5 1.5L8 11m3 1.5h9M4 18.5 5.5 20 8 17m3 1.5h9" />,
  wall: <><rect x="4" y="4" width="6.5" height="6.5" rx="2" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="2" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="2" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="2" /></>,
  camera: <><path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.2l1.3-2h6l1.3 2h1.2A2.5 2.5 0 0 1 20 8.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5Z" /><circle cx="12" cy="12.5" r="3.2" /></>,
  analytics: <path d="M4 20h16M6.5 16v-4m5.5 4V6m5.5 10V9.5" />,
  run: <path d="M12 15V4m0 0L8 8m4-4 4 4M5 15v2.5A1.5 1.5 0 0 0 6.5 19h11a1.5 1.5 0 0 0 1.5-1.5V15" />,
};
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
  const [shelfModel, setShelfModel] = useState<ShelfModel>("full");
  const [score, setScore] = useState<Score | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [searching, setSearching] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // cameras that have at least one image; a camera with none has nothing to show yet
  const store = useMemo(() => (raw ? { ...raw, cameras: raw.cameras.filter((c) => c.frames.length) } : null), [raw]);
  const line = useMemo(() => (store ? timeline(store) : { min: 0, max: 1, latest: 1 }), [store]);
  const tasks = useMemo(() => (store ? tasksAt(store, ts) : []), [store, ts]);
  // how fast each half-empty slot went from full to half today
  const paces = useMemo(() => (store ? paceAt(store, ts) : new Map<string, Pace>()), [store, ts]);
  useEffect(() => {
    preloadProductImages(tasks.map((task) => task.area.rawName || task.area.product));
  }, [tasks]);
  // the four headline numbers at 40 moments of the day, for the small charts under them
  const trend = useMemo(() => {
    const out = { shelf: [] as number[], full: [] as number[], match: [] as number[], todo: [] as number[] };
    if (!store?.cameras.length) return out;
    for (let i = 0; i < 40; i++) {
      const all = tasksAt(store, i === 39 ? line.latest : line.min + ((line.max - line.min) * i) / 39);
      const n = all.length || 1;
      out.shelf.push(all.filter((t) => t.status !== "empty").length / n);
      out.full.push(all.filter((t) => t.pred.level === "full").length / n);
      out.match.push(all.filter((t) => t.status !== "wrong").length / n);
      out.todo.push(all.filter((t) => t.status !== "ok").length);
    }
    return out;
  }, [store, line.min, line.max, line.latest]);

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
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        return setSearching((s) => !s);
      }
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "/") {
        e.preventDefault();
        return setSearching(true);
      }
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
      if (abort.current !== ctrl) return; // a newer run has started: this one must not close it
      finish({});
    } catch (err) {
      if (abort.current !== ctrl) return;
      if (ctrl.signal.aborted) finish({});
      else setRun((r) => ({ ...r, phase: "error", error: message(err) }));
    }
    if (newest) setTs(newest);
  }, []);

  const doScore = useCallback(async (annotations: string) => {
    setScoreError(null);
    try {
      setScore(await scoreAgainst(annotations));
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
      begin((on, signal) => analyzeFiles(picked.uploads, on, signal, shelfModel), archive ? null : picked.uploads.length, { annotations: picked.annotations, skipped: picked.ignored });
    },
    [raw?.live, hasRun, begin, doScore, shelfModel],
  );
  const startFolder = useCallback((path: string) => begin((on, signal) => analyzeFolder(path, on, signal, shelfModel), null, {}), [begin, shelfModel]);

  const refresh = useCallback(async () => {
    const s = await loadStore();
    setStore(s);
    return s;
  }, []);
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
          No shelf data yet. Start ShelfOS with <code className="font-mono text-white">python run.py</code> in the project folder, then reload.
        </div>
      </div>
    );
  if (!store) return <Loading />;

  const blank = store.cameras.length === 0;
  const shown = view;
  const cam = store.cameras.find((c) => c.id === camId) ?? store.cameras[0];
  const frame = cam && frameAt(cam, ts);
  const counts = Object.fromEntries(ORDER.map((s) => [s, tasks.filter((t) => t.status === s).length])) as Record<Status, number>;
  // among "Restock soon" tasks of equal impact, the slots that sold down fastest come first
  const sellTime = (t: Task) => (t.status === "low" ? paces.get(t.area.id)?.seconds : undefined) ?? Number.MAX_SAFE_INTEGER;
  const open = tasks
    .filter((t) => t.status !== "ok" && !done.has(t.key))
    .sort((a, b) => STATUS[a.status].rank - STATUS[b.status].rank || sellTime(a) - sellTime(b));
  const queue = byImpact(open.filter((t) => filter === "all" || t.status === filter));
  // "if you do this": what each task, and the next three, add to the store score
  const grade = storeScore(tasks, done);
  const next = queue.slice(0, 3);
  const after = Math.min(1, grade + next.reduce((sum, t) => sum + gain(t), 0) / (tasks.length || 1));
  const points = (t: Task) => `+${((gain(t) / (tasks.length || 1)) * 100).toFixed(1)} pts`;
  const lift = next.length > 0 && (
    <p className="score-lift">
      {next.length === 1 ? "The next task takes" : `The next ${next.length} tasks take`} the store from <b>{Math.round(grade * 100)}%</b> to <b>{Math.round(after * 100)}%</b>
    </p>
  );
  const total = tasks.length || 1;
  const shelf = (total - counts.empty) / total;
  const full = tasks.filter((t) => t.pred.level === "full").length / total;
  const match = (total - counts.wrong) / total;
  const dayAt = Math.min(1, Math.max(0, (Math.min(ts, line.max) - line.min) / Math.max(1, line.max - line.min)));
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
  const openCamera = (id: string) => {
    setCamId(id);
    setAreaId(null);
    setView("camera");
  };
  const showStatus = (s: Status) => {
    setTab("tasks");
    setFilter(s);
    setView("tasks");
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
    <div className={`app-shell app-enter h-full overflow-hidden grid ${blank ? "grid-rows-[auto_1fr]" : "grid-rows-[auto_auto_1fr]"}`}>
      {/* ── top bar ───────────────────────────────────────────── */}
      <header className="app-header flex flex-wrap items-center gap-x-6 gap-y-3 px-4 lg:px-6 py-3 lg:py-0 lg:h-[76px]">
        <div className="flex min-w-0 items-center lg:flex-1">
          <span className="wordmark" title={[store.store, store.section].filter(Boolean).join(" · ")}>Shelf<span>OS</span></span>
        </div>
        <nav className="main-nav glass order-last lg:order-none flex w-full lg:w-auto" aria-label="Views">
          {VIEWS.filter(([v]) => !blank || v === "run").map(([v, name]) => (
            <button
              key={v}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className="nav-item flex-1 lg:flex-none"
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{NAV_ICON[v]}</svg>
              {name}
            </button>
          ))}
          <ShelfAssistant store={store} timestamp={ts} camera={camId} area={areaId} completed={done} onArea={(camera, area) => { setCamId(camera); setAreaId(area); setView("camera"); }} />
        </nav>
        <div className="flex lg:flex-1 items-center justify-end gap-2.5">
          <a href="/colaboradores" className="nav-item" title="Demo mobile para colaboradores" aria-label="Abrir demo dos colaboradores">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="3" /><path d="M10 18h4" /></svg>
          </a>
          {!blank && (
            <button onClick={() => setSearching(true)} className="search-trigger glass" aria-label="Search" title="Search (Ctrl K)">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
              <span>Search</span>
              <kbd>Ctrl K</kbd>
            </button>
          )}
          {!blank && (
            <div className="status-pills glass hidden md:flex">
              {ORDER.map((s) => (
                <button key={s} aria-pressed={filter === s} title={STATUS[s].label} onClick={() => setFilter(filter === s ? "all" : s)} style={{ color: STATUS[s].color }}>
                  <span className="size-1.5 rounded-full bg-current" />
                  <span className="font-mono tabular-nums text-[13px] text-white/90"><CountUp value={counts[s]} /></span>
                  <span className="hidden 2xl:inline text-[11px] text-muted">{STATUS[s].label}</span>
                </button>
              ))}
            </div>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* ── the day ───────────────────────────────────────────── */}
      {!blank && (
        <div className="timeline-bar flex items-center gap-3 lg:gap-4 px-4 lg:px-6 py-3">
          <button onClick={togglePlay} aria-label={playingNow ? "Pause" : "Play the day"} className="size-9 shrink-0 grid place-items-center rounded-full glass text-white/80 hover:text-white transition-colors">
            {playingNow ? (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><rect x="1.5" y="1" width="3" height="10" rx="1" /><rect x="7.5" y="1" width="3" height="10" rx="1" /></svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M2.5 1.2v9.6a.6.6 0 0 0 .9.5l8-4.8a.6.6 0 0 0 0-1L3.4.7a.6.6 0 0 0-.9.5Z" /></svg>
            )}
          </button>
          <div className="w-[76px] lg:w-[92px] shrink-0">
            <div className="font-mono text-xl lg:text-2xl leading-none tabular-nums tracking-tight">{clock(ts)}</div>
            <div className={`mt-1 text-[10px] uppercase tracking-[0.14em] ${isLive ? "text-white/80" : "text-muted"}`}>{isLive ? "Latest" : "History"}</div>
          </div>
          <DayStrip store={store} ts={ts} line={line} onChange={scrub} />
          <button onClick={() => scrub(line.latest)} disabled={isLive} className="glass hidden sm:block shrink-0 text-xs rounded-full px-4 py-2 text-white/80 enabled:hover:text-white disabled:opacity-40">
            Jump to latest
          </button>
        </div>
      )}

      <div className={`grid h-full min-h-0 overflow-hidden ${blank || view === "tasks" || view === "analytics" ? "" : "lg:grid-cols-[minmax(0,1fr)_384px]"}`}>
        {/* ── main ─────────────────────────────────────────────── */}
        <main className={`workspace h-full min-h-0 min-w-0 p-4 lg:p-7 ${shown === "camera" ? "flex flex-col overflow-hidden" : "overflow-y-auto"}`}>
          <div key={shown} className={`view-enter ${shown === "camera" ? "camera-page" : ""}`}>
          {shown === "run" || blank ? (
            <RunView
              store={store}
              health={health}
              run={run}
              model={shelfModel}
              onModel={setShelfModel}
              score={score}
              scoreError={scoreError}
              onFiles={startFiles}
              onFolder={startFolder}
              onCancel={() => abort.current?.abort()}
              onOpen={openFrame}
              onFocus={(c, f, a) => openFrame(c, f, a)}
              onScore={doScore}
              onReset={clearRun}
            />
          ) : shown === "analytics" ? (
            <Analytics
              store={store}
              tasks={tasks}
              line={line}
              ts={ts}
              onTime={scrub}
              onArea={(c, a) => {
                setCamId(c.id);
                setAreaId(a.id);
                setView("camera");
              }}
              onCameraAt={(id, t) => {
                scrub(t);
                openCamera(id);
              }}
            />
          ) : shown === "tasks" ? (
            <div className="tasks-page flex flex-col gap-5">
              <section className="overview-heading">
                <div>
                  <div className="eyebrow">TASKS · {clock(ts)}</div>
                  <h1>{open.length ? <><CountUp value={open.length} /> <span>to do</span></> : <>All done. <span>Shelves are in shape.</span></>}</h1>
                  <p>Biggest impact first. Tap a task to see the shelf. Tick it when it is done.</p>
                </div>
                <div className="shift-progress glass-card">
                  <div className="flex items-baseline justify-between gap-6 text-xs"><span className="text-muted">Store score</span><span className="font-mono tabular-nums text-lg"><CountUp value={Math.round(grade * 100)} />%</span></div>
                  <div className="shift-bar"><span style={{ width: `${grade * 100}%` }} /></div>
                  {lift}
                  <div className="mt-2 flex items-baseline justify-between gap-6 text-[11px] text-muted">
                    <span>Done this shift <span className="font-mono tabular-nums">{done.size} / {done.size + open.length}</span></span>
                    {done.size > 0 && <button onClick={() => { setDone(new Set()); setNotice(null); }} className="hover:text-white">Reset</button>}
                  </div>
                </div>
              </section>
              <div className="filter-row">
                <button aria-pressed={tab === "tasks" && filter === "all"} onClick={() => { setTab("tasks"); setFilter("all"); }}>All <span>{open.length}</span></button>
                {ISSUES.map((s) => (
                  <button key={s} aria-pressed={tab === "tasks" && filter === s} onClick={() => { setTab("tasks"); setFilter(s); }}>
                    <i style={{ background: STATUS[s].color }} />{STATUS[s].action} <span>{open.filter((t) => t.status === s).length}</span>
                  </button>
                ))}
                <button aria-pressed={tab === "products"} onClick={() => setTab("products")}>Stock by product</button>
              </div>
              {tab === "products" ? (
                <div className="glass-card overflow-hidden"><Products tasks={tasks} onPick={focus} /></div>
              ) : (
                <>
                  <div className="task-grid">
                    {queue.map((t, i) => {
                      const s = t.status;
                      const held = Math.max(ts, t.frame.ts) - since(t.cam, t.area.id, t.frame);
                      const pace = t.status === "low" ? paces.get(t.area.id) : undefined;
                      return (
                        <div key={t.key} className="task-card glass-card" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
                          <button onClick={() => focus(t)} className="flex min-w-0 flex-1 items-center gap-3.5 text-left">
                            <Crop store={store} cam={t.cam} frame={t.frame} area={t.area} className="size-[68px] shrink-0 rounded-2xl" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[15px] font-medium">{t.area.product}</div>
                              <div className="mt-0.5 flex items-center gap-1.5 text-xs" style={{ color: STATUS[s].color }}>
                                {STATUS[s].hint}
                                {held >= 60 && <span className="text-muted">· for {duration(held)}</span>}
                              </div>
                              <div className="mt-1 text-[11px] text-muted font-mono">cam {t.cam.id} · slot {t.area.id.split("_")[1]}{pace && ` · full → half in ${duration(pace.seconds)}`}</div>
                            </div>
                          </button>
                          <span className="task-gain" title="Store score gained by doing this task">{points(t)}</span>
                          <button onClick={() => toggleDone(t.key)} aria-label={`Mark ${t.area.product} done`} title="Mark done" className="task-done">
                            <svg width="16" height="16" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m2.5 7 2.8 2.8 5.2-6" /></svg>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  {queue.length === 0 && <div className="glass-card px-5 py-14 text-center text-sm text-muted">Nothing to do in this view.</div>}
                </>
              )}
            </div>
          ) : shown === "wall" ? (
            <div className="flex flex-col gap-5">
              <section className="overview-heading">
                <div>
                  <div className="eyebrow">OVERVIEW</div>
                  <h1>Every shelf. <span>In sight.</span></h1>
                  <p>{store.section}, area by area.</p>
                </div>
                <div className="snapshot-chip glass"><span className="status-beacon" />{isLive ? "Latest snapshot" : "Historical snapshot"}<span className="font-mono">{clock(ts)}</span></div>
              </section>
              <div className="metrics-grid grid grid-cols-2 xl:grid-cols-4 gap-3">
                <Kpi label="On the shelf" value={`${Math.round(shelf * 100)}%`} share={shelf} trend={trend.shelf} at={dayAt} sub={counts.empty ? `${counts.empty} of ${total} areas are empty` : `all ${total} areas have product`} tone={counts.empty ? "empty" : "ok"} />
                <Kpi label="Fully stocked" value={`${Math.round(full * 100)}%`} share={full} trend={trend.full} at={dayAt} sub={counts.low ? `${counts.low} running low` : "nothing running low"} tone={counts.low ? "low" : "ok"} />
                <Kpi label="Planogram match" value={`${Math.round(match * 100)}%`} share={match} trend={trend.match} at={dayAt} sub={counts.wrong ? `${counts.wrong} holding the wrong product` : "everything in its place"} tone={counts.wrong ? "wrong" : "ok"} />
                <Kpi label="To do now" value={String(open.length)} trend={trend.todo} at={dayAt} sub={done.size ? `${done.size} done this shift` : "open tasks across the store"} tone="accent">
                  <button onClick={() => setView("tasks")} className="metric-mix" title="Open tasks">
                    {ISSUES.map((s) => (
                      <span key={s}><i style={{ background: STATUS[s].color }} />{open.filter((t) => t.status === s).length}</span>
                    ))}
                  </button>
                </Kpi>
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
                      className="camera-card group relative text-left"
                    >
                      <div className="camera-caption"><span><svg className="camera-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="3" /><path d="m16 10 5-3v10l-5-3" /></svg> Camera {c.id}</span><span>{c.areas.length} areas <span className="camera-arrow" aria-hidden="true">↗</span></span></div>
                      <div className="relative camera-image">
                      <FrameView store={store} cam={c} frame={f} filter={filter} compact />
                      <div className="absolute inset-x-0 top-0 flex items-center justify-between p-2.5">
                        <span className="glass-chip font-mono">
                          CAM {c.id}
                          <span className="text-white/60">{clock(f.ts)}</span>
                          {f.origin === "run" && <span className="text-white/60">tested</span>}
                        </span>
                        <Badges n={n} />
                      </div>
                      <div className="absolute inset-x-0 bottom-0 flex gap-[3px] px-3 pb-3 pt-6 bg-gradient-to-t from-black/60 to-transparent">
                        {c.areas.map((a) => {
                          const p = f.areas[a.id];
                          const s = p ? statusOf(p) : "ok";
                          return <span key={a.id} className="h-1 flex-1 rounded-sm" style={{ background: STATUS[s].color, opacity: s === "ok" ? 0.3 : 1 }} />;
                        })}
                      </div>
                      </div>
                      <div className="camera-footer"><span className="flex items-center gap-2"><span className="size-1.5 rounded-full" style={{ background: STATUS[worst].color, opacity: worst === "ok" ? 0.4 : 1 }} />{worst === "ok" ? "All areas in good shape" : `${n.empty + n.wrong + n.low} areas need attention`}</span><span>Inspect feed <span aria-hidden="true">→</span></span></div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <>
              <div className="flex shrink-0 gap-2 overflow-x-auto pb-1">
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
                      className={`shrink-0 flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-mono transition-colors ${c.id === cam.id ? "border-white/30 bg-white/10 text-white" : "border-line text-muted hover:text-white hover:border-white/25"}`}
                    >
                      <span className="size-1.5 rounded-full" style={{ background: STATUS[worst].color }} />
                      {c.id}
                      {todo > 0 && <span style={{ color: STATUS[worst].color }}>{todo}</span>}
                    </button>
                  );
                })}
              </div>
              <div key={cam.id} className="camera-detail-enter camera-stage-row">
                <CameraStage store={store} cam={cam} frame={frame} areaId={areaId} filter={filter} onSelect={setAreaId}>
                  {selected && frame.areas[selected.id] && <AreaDetail key={selected.id} store={store} cam={cam} frame={frame} area={selected} onPick={scrub} onClose={() => setAreaId(null)} />}
                </CameraStage>
                <AreaList cam={cam} frame={frame} onSelect={setAreaId} />
              </div>
            </>
          )}
          </div>
        </main>

        {/* ── work queue ───────────────────────────────────────── */}
        {!blank && view !== "tasks" && view !== "analytics" && (
          <aside className="task-panel glass-card hidden lg:flex min-h-0 flex-col">
            <div className="px-5 pt-4 border-b border-line">
              <div className="flex items-end justify-between">
                <div>
                  <div className="eyebrow">YOUR NEXT MOVES · {clock(ts)}</div>
                  <div className="mt-1 text-xl font-medium tracking-tight">
                    {open.length ? (
                      <>
                        <CountUp value={open.length} /> <span className="text-muted">task{open.length === 1 ? "" : "s"} to tackle</span>
                      </>
                    ) : (
                      <span>All shelves compliant</span>
                    )}
                  </div>
                  {lift}
                </div>
                {done.size > 0 && (
                  <button onClick={() => { setDone(new Set()); setNotice(null); }} className="text-[11px] text-muted hover:text-white mb-1">
                    {done.size} done · reset
                  </button>
                )}
              </div>
              <div className="mt-3 flex gap-5 text-xs">
                {(["tasks", "products"] as Tab[]).map((t) => (
                  <button key={t} onClick={() => setTab(t)} className={`pb-2.5 border-b-2 -mb-px transition-colors ${tab === t ? "border-white text-white" : "border-transparent text-muted hover:text-white"}`}>
                    {t === "tasks" ? "Tasks" : "Stock by product"}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              <div key={tab} className="queue-enter">
              {tab === "tasks" ? (
                <>
                  {queue.map((t) => {
                    const s = t.status;
                    const held = Math.max(ts, t.frame.ts) - since(t.cam, t.area.id, t.frame);
                    const pace = t.status === "low" ? paces.get(t.area.id) : undefined;
                    return (
                      <div key={t.key} className={`task-row group flex items-center gap-3 ${t.area.id === areaId && shown === "camera" ? "bg-raised" : ""}`}>
                        <button onClick={() => focus(t)} className="flex items-center gap-3 min-w-0 flex-1 text-left">
                          <div className="relative shrink-0">
                            <Crop store={store} cam={t.cam} frame={t.frame} area={t.area} className="w-12 h-12 rounded-xl" />
                            <span className="absolute -left-0.5 -top-0.5 size-2.5 rounded-full ring-2 ring-[var(--bg)]" style={{ background: STATUS[s].color }} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm">{t.area.product}</div>
                            <div className="text-[11px]" style={{ color: STATUS[s].color }}>
                              {STATUS[s].hint}
                              {held >= 60 && <span className="text-muted"> · for {duration(held)}</span>}
                            </div>
                            <div className="text-[10px] text-muted/80 font-mono">
                              cam {t.cam.id} · slot {t.area.id.split("_")[1]} · {Math.round(confidence(t.pred) * 100)}% sure{pace && ` · full → half in ${duration(pace.seconds)}`}
                            </div>
                          </div>
                        </button>
                        <span className="task-gain" title="Store score gained by doing this task">{points(t)}</span>
                        <button
                          onClick={() => toggleDone(t.key)}
                          aria-label="Mark done"
                          title="Mark done"
                          className="size-8 shrink-0 grid place-items-center rounded-full border border-line text-muted hover:border-white/40 hover:text-white hover:bg-white/10 transition-colors"
                        >
                          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m2.5 7 2.8 2.8 5.2-6" /></svg>
                        </button>
                      </div>
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

      {searching && <Search store={store} tasks={tasks} line={line} playing={playingNow} onClose={() => setSearching(false)} onTask={focus} onCamera={openCamera} onView={setView} onTime={scrub} onFilter={showStatus} onPlay={togglePlay} />}
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
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-md pointer-events-none">
          <div className="glass rounded-3xl px-16 py-12 text-center">
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
          <button key={worst.area.productId} onClick={() => onPick(worst)} className="product-row w-full text-left px-5 py-2.5 border-b border-line/50 hover:bg-raised/60 transition-colors">
            <ProductImage name={worst.area.rawName || r.name} />
            <div className="min-w-0 flex-1">
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
            </div>
          </button>
        );
      })}
    </div>
  );
}
