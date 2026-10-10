"use client";

import type React from "react";
import { Fragment, useId, useMemo, useState } from "react";
import { CountUp, Crop } from "./components";
import { AreaDef, Camera, ISSUES, LEVEL_VALUE, ORDER, STATUS, Status, Store, Task, clock, confidence, duration, frameAt, since, statusOf } from "./lib";
import { ProductImage } from "./product-image";

type Line = { min: number; max: number; latest: number };
/** Where in the analytics you are: the whole store, one camera, one product, or one slot. */
type Scope = { kind: "all" } | { kind: "camera"; cam: string } | { kind: "product"; id: string } | { kind: "area"; cam: string; area: string; via?: string };
type Row = { cam: Camera; area: AreaDef; runs: { s: Status | null; n: number }[]; bad: number; stock: number };
type Mode = "attention" | "stock" | "compliant" | "cover";
type Day = ReturnType<typeof readDay>;

/** How many moments of the day the charts are drawn from. */
const N = 72;
const W = 1000;
const H = 260;
/** Where the confidence chart starts: three stock levels, so a call is never below a third. */
const BINS = [30, 40, 50, 60, 70, 80, 90];
const MODES: Record<Mode, { name: string; title: string }> = {
  attention: { name: "Attention", title: "Areas needing attention" },
  stock: { name: "Stock", title: "Average stock level" },
  compliant: { name: "Compliant", title: "Share of areas full and in place" },
  cover: { name: "Covered", title: "Share of the shelf showing product" },
};
const delay = (i: number) => ({ "--i": i }) as React.CSSProperties;
const slot = (area: AreaDef) => area.id.split("_")[1];
const pct = (v: number) => Math.round(v * 100);

/** The day read once for a set of areas: their state at N moments, and what changed between captures. */
function readDay(store: Store, line: Line, keep: (cam: Camera, area: AreaDef) => boolean) {
  const span = line.max - line.min;
  const times = Array.from({ length: N }, (_, i) => line.min + (span * i) / (N - 1));
  const counts = times.map(() => ({ empty: 0, wrong: 0, low: 0, ok: 0 }) as Record<Status, number>);
  const level = times.map(() => 0);
  const cover = times.map(() => 0);
  const mapped = times.map(() => 0);
  const rows: Row[] = [];
  const events: { t: number; fixed: boolean }[] = [];
  const fixes: number[] = [];
  let fixedRaised = 0; // fixes of problems that were counted as raised
  let captures = 0;
  for (const cam of store.cameras) {
    const areas = cam.areas.filter((a) => keep(cam, a));
    if (!areas.length) continue;
    const at = times.map((t) => frameAt(cam, t));
    const frames = cam.frames.filter((f) => f.ts >= line.min && f.ts <= line.max);
    captures += frames.length;
    for (const area of areas) {
      const runs: Row["runs"] = [];
      let bad = 0;
      let stock = 0;
      let seen = 0;
      at.forEach((f, i) => {
        const p = f.areas[area.id];
        const s = p ? statusOf(p) : null;
        if (p && s) {
          counts[i][s]++;
          level[i] += LEVEL_VALUE[p.level];
          stock += LEVEL_VALUE[p.level];
          seen++;
          if (p.map.length) {
            cover[i] += p.occ;
            mapped[i]++;
          }
          if (s !== "ok") bad++;
        }
        const last = runs[runs.length - 1];
        if (last && last.s === s) last.n++;
        else runs.push({ s, n: 1 });
      });
      rows.push({ cam, area, runs, bad, stock: seen ? stock / seen : 0 });
      // a problem is raised when a capture first shows it, and fixed when a later one shows the area in shape
      let started: number | null = null;
      let counted = false; // a problem already there in the first capture was not raised during the day
      frames.forEach((f, i) => {
        const p = f.areas[area.id];
        if (!p) return;
        const ok = statusOf(p) === "ok";
        if (!ok && started === null) {
          started = f.ts;
          counted = i > 0;
          if (counted) events.push({ t: f.ts, fixed: false });
        } else if (ok && started !== null) {
          fixes.push(f.ts - started);
          events.push({ t: f.ts, fixed: true });
          if (counted) fixedRaised++;
          started = null;
        }
      });
    }
  }
  const per = counts.map((n) => Math.max(1, n.empty + n.wrong + n.low + n.ok));
  const issues = counts.map((n) => n.empty + n.wrong + n.low);
  const peak = Math.max(...issues);
  const spent = { empty: 0, wrong: 0, low: 0, ok: 0 } as Record<Status, number>;
  for (const n of counts) for (const s of ORDER) spent[s] += n[s];
  fixes.sort((a, b) => a - b);
  return {
    times, counts, peak, captures, events, spent,
    worst: issues.indexOf(peak),
    total: rows.length,
    raised: events.filter((e) => !e.fixed).length,
    fixed: fixedRaised,
    medianFix: fixes.length ? fixes[fixes.length >> 1] : null,
    available: counts.reduce((sum, n, i) => sum + (per[i] - n.empty) / per[i], 0) / N,
    lowest: Math.min(...counts.map((n, i) => (per[i] - n.empty) / per[i])),
    series: {
      stock: level.map((v, i) => v / per[i]),
      compliant: counts.map((n, i) => n.ok / per[i]),
      cover: cover.map((v, i) => (mapped[i] ? v / mapped[i] : 0)),
    },
    hasCover: mapped.some(Boolean),
    rows: rows.sort((a, b) => b.bad - a.bad),
    step: span / (N - 1),
  };
}

/** A line through the points that eases between them and never overshoots. */
function curve(ys: number[], back = false): string {
  const x = (i: number) => (i / (N - 1)) * W;
  const order = ys.map((_, i) => i);
  if (back) order.reverse();
  let d = "";
  order.forEach((i, k) => {
    if (k === 0) {
      d = `${x(i).toFixed(1)},${ys[i].toFixed(1)}`;
      return;
    }
    const prev = order[k - 1];
    const mid = ((x(prev) + x(i)) / 2).toFixed(1);
    d += ` C${mid},${ys[prev].toFixed(1)} ${mid},${ys[i].toFixed(1)} ${x(i).toFixed(1)},${ys[i].toFixed(1)}`;
  });
  return d;
}

/** The hours of the day as columns; twelve even steps when the day is shorter than two hours. */
function hourCols(line: Line): number[] {
  const out: number[] = [];
  for (let t = Math.ceil(line.min / 3600) * 3600; t <= line.max; t += 3600) out.push(t);
  return out.length >= 2 ? out : Array.from({ length: 12 }, (_, i) => line.min + ((line.max - line.min) * i) / 11);
}

function Dur({ seconds }: { seconds: number }) {
  const [n, unit] = duration(seconds).split(" ");
  return <><CountUp value={Number(n)} /><small>{unit}</small></>;
}

function Tile({ label, sub, onClick, title, children }: { label: string; sub: React.ReactNode; onClick?: () => void; title?: string; children: React.ReactNode }) {
  const body = (
    <>
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className="metric-value leading-none tabular-nums">{children}</div>
      <div className="text-xs text-muted truncate">{sub}</div>
    </>
  );
  return onClick ? <button onClick={onClick} title={title} className="metric-card an-tile glass-card">{body}</button> : <div className="metric-card an-tile glass-card">{body}</div>;
}

function Legend() {
  return <div className="an-legend">{ISSUES.map((s) => <span key={s}><i style={{ background: STATUS[s].color }} />{STATUS[s].label}</span>)}</div>;
}

/** The day as one curve, in whichever measure is picked. */
function Chart({ day, line, ts, modes, onJump, i }: { day: Day; line: Line; ts: number; modes: Mode[]; onJump: (t: number) => void; i: number }) {
  const [picked, setMode] = useState<Mode>(modes[0]);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const mode = modes.includes(picked) ? picked : modes[0];
  const span = Math.max(1, line.max - line.min);
  const pos = (t: number) => Math.min(100, Math.max(0, ((t - line.min) / span) * 100));
  const top = Math.max(1, day.peak);
  const layers = useMemo(() => {
    if (mode !== "attention") {
      const ys = day.series[mode].map((v) => H - v * (H - 24));
      return [{ key: mode, color: "var(--ink)", line: `M${curve(ys)}`, area: `M${curve(ys)} L${W},${H} L0,${H} Z` }];
    }
    const y = (v: number) => H - (v / top) * (H - 24);
    return ISSUES.map((s, k) => {
      // each state sits on top of the ones before it
      const base = day.counts.map((n) => ISSUES.slice(0, k).reduce((sum, below) => sum + n[below], 0));
      const upper = base.map((b, j) => b + day.counts[j][s]);
      return { key: s as string, color: STATUS[s].color, line: `M${curve(upper.map(y))}`, area: `M${curve(upper.map(y))} L${curve(base.map(y), true)} Z` };
    });
  }, [day, mode, top]);
  const hours = useMemo(() => {
    const out: number[] = [];
    for (let t = Math.ceil(line.min / 3600) * 3600; t <= line.max; t += 3600) out.push(t);
    return out;
  }, [line.min, line.max]);
  const point = hover === null ? null : { t: day.times[hover], n: day.counts[hover], x: (hover / (N - 1)) * 100 };
  return (
    <section className="an-card glass-card" style={delay(i)}>
      <div className="an-head">
        <div><span className="eyebrow">OVER THE DAY</span><h3>{MODES[mode].title}</h3><p>Hover to read a moment, click to go there.</p></div>
        {modes.length > 1 && (
          <div className="an-seg">
            {modes.map((m) => <button key={m} aria-pressed={m === mode} onClick={() => setMode(m)}>{MODES[m].name}</button>)}
          </div>
        )}
      </div>
      <div
        className="an-chart"
        onPointerMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          setHover(Math.min(N - 1, Math.max(0, Math.round(((e.clientX - box.left) / box.width) * (N - 1)))));
        }}
        onPointerLeave={() => setHover(null)}
        onClick={() => hover !== null && onJump(day.times[hover])}
      >
        {[1, 0.5, 0].map((f) => (
          <div key={f} className="an-gridline" style={{ top: `${((H - f * (H - 24)) / H) * 100}%` }}><span>{mode === "attention" ? Math.round(top * f) : `${f * 100}%`}</span></div>
        ))}
        <svg key={mode} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <defs>
            {layers.map((l) => (
              <linearGradient key={l.key} id={`${id}${l.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={l.color} stopOpacity={mode === "attention" ? 0.55 : 0.22} />
                <stop offset="1" stopColor={l.color} stopOpacity={mode === "attention" ? 0.08 : 0} />
              </linearGradient>
            ))}
          </defs>
          {layers.map((l) => <path key={l.key} d={l.area} fill={`url(#${id}${l.key})`} />)}
          {layers.map((l) => <path key={l.key} d={l.line} fill="none" stroke={l.color} strokeWidth="1.6" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />)}
        </svg>
        <div className="an-now" style={{ left: `${pos(ts)}%` }} />
        {point && hover !== null && (
          <>
            <div className="an-cross" style={{ left: `${point.x}%` }} />
            <div className="an-tip glass" style={{ left: `clamp(84px, ${point.x}%, calc(100% - 84px))` }}>
              <div className="font-mono text-sm text-white">{clock(point.t)}{mode !== "attention" && <b>{pct(day.series[mode][hover])}%</b>}</div>
              {ORDER.map((s) => (
                <div key={s}><i style={{ background: STATUS[s].color }} />{STATUS[s].label}<b>{point.n[s]}</b></div>
              ))}
            </div>
          </>
        )}
      </div>
      <div className="an-hours">{hours.map((t, k) => <span key={t} className={k % 2 ? "max-md:hidden" : ""} style={{ left: `${pos(t)}%` }}>{clock(t).slice(0, 2)}h</span>)}</div>
    </section>
  );
}

type HeatRow = { key: string; label: string; open?: () => void; cell: (t: number) => { share: number; worst?: Status; tip: string }; pick: (t: number) => void };

/** One row per thing, one column per hour: the stronger the colour, the more of it needed attention. */
function Heat({ rows, cols, now, label }: { rows: HeatRow[]; cols: number[]; now: number; label: number }) {
  return (
    <div className="an-heat" style={{ gridTemplateColumns: `${label}px repeat(${cols.length}, minmax(18px, 1fr))` }}>
      <span />
      {cols.map((t, i) => <span key={t} className="an-heat-hour" data-now={i === now}>{clock(t).slice(0, 2)}</span>)}
      {rows.map((row, r) => (
        <div key={row.key} className="contents">
          {row.open ? <button onClick={row.open} className="an-heat-cam" title={`Open ${row.label}`}>{row.label}</button> : <span className="an-heat-cam">{row.label}</span>}
          {cols.map((t, i) => {
            const c = row.cell(t);
            return (
              <button
                key={t}
                onClick={() => row.pick(t)}
                className="an-cell"
                title={`${row.label} at ${clock(t)} · ${c.tip}`}
                style={{ ...delay(Math.min(r, 14) + i), background: c.worst ? `color-mix(in srgb, ${STATUS[c.worst].color} ${Math.round(22 + c.share * 78)}%, rgb(var(--fg) / .06))` : undefined }}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

function Ribbon({ runs }: { runs: Row["runs"] }) {
  return <span className="an-ribbon">{runs.map((run, k) => <i key={k} style={{ flexGrow: run.n, background: run.s && run.s !== "ok" ? STATUS[run.s].color : undefined }} />)}</span>;
}

export function Analytics({
  store, tasks, line, ts, onTime, onArea, onCameraAt,
}: {
  store: Store; tasks: Task[]; line: Line; ts: number;
  onTime: (ts: number) => void; onArea: (cam: Camera, area: AreaDef) => void; onCameraAt: (id: string, ts: number) => void;
}) {
  const [wanted, setScope] = useState<Scope>({ kind: "all" });
  const go = (s: Scope) => {
    setScope(s);
    document.querySelector(".workspace")?.scrollTo({ top: 0, behavior: "smooth" });
  };
  const jump = (t: number) => onTime(t >= line.max ? line.latest : t);

  // a scope that no longer exists (the store was reloaded) falls back to the whole store
  const cam = wanted.kind === "camera" || wanted.kind === "area" ? store.cameras.find((c) => c.id === wanted.cam) : undefined;
  const area = wanted.kind === "area" ? cam?.areas.find((a) => a.id === wanted.area) : undefined;
  const productId = wanted.kind === "product" ? wanted.id : wanted.kind === "area" ? wanted.via : undefined;
  const product = productId ? store.cameras.flatMap((c) => c.areas).find((a) => a.productId === productId) : undefined;
  const scope: Scope = (wanted.kind === "camera" && !cam) || (wanted.kind === "product" && !product) || (wanted.kind === "area" && !area) ? { kind: "all" } : wanted;

  const crumbs: { label: string; to: Scope }[] = [{ label: "Analytics", to: { kind: "all" } }];
  if (scope.kind === "camera" && cam) crumbs.push({ label: `Camera ${cam.id}`, to: scope });
  if (scope.kind === "product" && product) crumbs.push({ label: product.product, to: scope });
  if (scope.kind === "area" && cam && area) {
    if (product && scope.via) crumbs.push({ label: product.product, to: { kind: "product", id: product.productId } });
    else crumbs.push({ label: `Camera ${cam.id}`, to: { kind: "camera", cam: cam.id } });
    crumbs.push({ label: scope.via ? `Camera ${cam.id} · slot ${slot(area)}` : `Slot ${slot(area)} · ${area.product}`, to: scope });
  }

  return (
    <div className="analytics-page flex flex-col gap-5">
      <nav className="crumbs glass" aria-label="Breadcrumb">
        {crumbs.length > 1 && (
          <button className="crumb-back" onClick={() => go(crumbs[crumbs.length - 2].to)} aria-label="Back" title="Back">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
          </button>
        )}
        {crumbs.map((c, i) => (
          <Fragment key={`${i}${c.label}`}>
            {i > 0 && <svg className="crumb-sep" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>}
            <button className="crumb" aria-current={i === crumbs.length - 1 ? "page" : undefined} disabled={i === crumbs.length - 1} onClick={() => go(c.to)}>
              {i === 0 && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M4 20h16M6.5 16v-4m5.5 4V6m5.5 10V9.5" /></svg>}
              <span>{c.label}</span>
            </button>
          </Fragment>
        ))}
      </nav>
      <div key={JSON.stringify(scope)} className="view-enter flex flex-col gap-5">
        {scope.kind === "area" && cam && area ? (
          <Slot store={store} cam={cam} area={area} line={line} ts={ts} onJump={jump} onTime={onTime} onOpen={() => onArea(cam, area)} />
        ) : (
          <Group store={store} tasks={tasks} line={line} ts={ts} cam={scope.kind === "camera" ? cam : undefined} product={scope.kind === "product" ? product : undefined} go={go} onJump={jump} onCameraAt={onCameraAt} />
        )}
      </div>
    </div>
  );
}

/** The whole store, one camera or one product: the same reading of the day, over fewer or more areas. */
function Group({
  store, tasks, line, ts, cam, product, go, onJump, onCameraAt,
}: {
  store: Store; tasks: Task[]; line: Line; ts: number; cam?: Camera; product?: AreaDef;
  go: (s: Scope) => void; onJump: (t: number) => void; onCameraAt: (id: string, ts: number) => void;
}) {
  const camId = cam?.id ?? null;
  const productId = product?.productId ?? null;
  const day = useMemo(() => readDay(store, line, (c, a) => (camId === null || c.id === camId) && (productId === null || a.productId === productId)), [store, line, camId, productId]);
  const cols = useMemo(() => hourCols(line), [line]);
  const [allProducts, setAllProducts] = useState(false);
  const nowCol = cols.reduce((best, t, i) => (t <= ts ? i : best), 0);
  const mine = tasks.filter((t) => (camId === null || t.cam.id === camId) && (productId === null || t.area.productId === productId));
  const via = productId ?? undefined;

  // ── right now ─────────────────────────────────────────────────────────────────
  const total = mine.length || 1;
  const mix = ORDER.map((s, i) => ({
    s,
    n: mine.filter((t) => t.status === s).length,
    // where its arc starts on the ring: after every state before it
    from: (mine.filter((t) => ORDER.indexOf(t.status) < i).length / total) * 100,
  }));
  const okNow = mix.find((m) => m.s === "ok")?.n ?? 0;
  const sure = mine.map((t) => confidence(t.pred));
  const meanSure = sure.reduce((a, b) => a + b, 0) / Math.max(1, sure.length);
  const hist = BINS.map((lo, i) => sure.filter((c) => Math.min(BINS.length - 1, Math.max(0, Math.floor((c * 100 - 30) / 10))) === i).length);
  const histTop = Math.max(1, ...hist);
  const unsure = sure.filter((c) => c < 0.6).length;
  const mixups = mine
    .filter((t) => t.status === "wrong")
    .map((t) => ({ t, like: (t.pred.looks ?? []).find(([id]) => id !== t.area.productId) }))
    .filter((m) => m.like);

  // ── rankings ──────────────────────────────────────────────────────────────────
  const groups = useMemo(() => {
    const by = (key: (r: Row) => string) => {
      const map = new Map<string, Row[]>();
      for (const r of day.rows) map.set(key(r), [...(map.get(key(r)) ?? []), r]);
      return [...map.values()].map((rows) => ({
        rows,
        inShape: 1 - rows.reduce((sum, r) => sum + r.bad, 0) / (rows.length * N),
        stock: rows.reduce((sum, r) => sum + r.stock, 0) / rows.length,
        off: (rows.reduce((sum, r) => sum + r.bad, 0) / rows.length) * day.step,
      }));
    };
    return {
      cameras: by((r) => r.cam.id).sort((a, b) => a.inShape - b.inShape),
      products: by((r) => r.area.productId).sort((a, b) => a.stock - b.stock || a.inShape - b.inShape),
    };
  }, [day]);

  // ── problems raised and fixed, hour by hour ───────────────────────────────────
  const stepCol = Math.max(1, cols[1] - cols[0]);
  const flow = cols.map((t, i) => {
    const here = day.events.filter((e) => Math.min(cols.length - 1, Math.max(0, Math.floor((e.t - cols[0]) / stepCol))) === i);
    return { t, raised: here.filter((e) => !e.fixed).length, fixed: here.filter((e) => e.fixed).length };
  });
  const flowTop = Math.max(1, ...flow.map((f) => Math.max(f.raised, f.fixed)));
  const spentAll = Math.max(1, ORDER.reduce((sum, s) => sum + day.spent[s], 0));

  const heat: HeatRow[] = cam || product
    ? day.rows
        .slice()
        .sort((a, b) => a.cam.id.localeCompare(b.cam.id, undefined, { numeric: true }) || a.area.id.localeCompare(b.area.id, undefined, { numeric: true }))
        .map((r) => ({
          key: `${r.cam.id}/${r.area.id}`,
          label: product ? `cam ${r.cam.id} · ${slot(r.area)}` : `slot ${slot(r.area)}`,
          open: () => go({ kind: "area", cam: r.cam.id, area: r.area.id, via }),
          cell: (t) => {
            const p = frameAt(r.cam, t).areas[r.area.id];
            const s = p ? statusOf(p) : "ok";
            return { share: 1, worst: s === "ok" ? undefined : s, tip: p ? STATUS[s].label : "not seen" };
          },
          pick: onJump,
        }))
    : store.cameras.map((c) => ({
        key: c.id,
        label: `cam ${c.id}`,
        open: () => go({ kind: "camera", cam: c.id }),
        cell: (t) => {
          const f = frameAt(c, t);
          const n = { empty: 0, wrong: 0, low: 0, ok: 0 } as Record<Status, number>;
          for (const a of c.areas) if (f.areas[a.id]) n[statusOf(f.areas[a.id])]++;
          const todo = n.empty + n.wrong + n.low;
          return { share: todo / Math.max(1, c.areas.length), worst: ISSUES.find((s) => n[s]), tip: todo ? `${todo} of ${c.areas.length} need attention` : "all in shape" };
        },
        pick: (t) => onCameraAt(c.id, t >= line.max ? line.latest : t),
      }));

  const ribbons = cam || product ? day.rows : day.rows.filter((r) => r.bad).slice(0, 8);
  const shownProducts = allProducts ? groups.products : groups.products.slice(0, 7);

  return (
    <>
      <section className="overview-heading">
        <div>
          <div className="eyebrow">{cam ? "CAMERA" : product ? "PRODUCT" : "ANALYTICS"} · {clock(line.min)} – {clock(line.max)}</div>
          <h1>{cam ? <>Camera {cam.id}. <span>{day.total} areas.</span></> : product ? <>{product.product}. <span>{day.total} slot{day.total === 1 ? "" : "s"}.</span></> : <>The day. <span>In numbers.</span></>}</h1>
          <p>{cam ? "Everything this camera saw today, slot by slot." : product ? `Where it sits and how it held up. Planogram name ${product.rawName}.` : `What the cameras saw across ${store.cameras.length} cameras and ${day.total} planogram areas.`}</p>
        </div>
        {cam ? (
          <button onClick={() => onCameraAt(cam.id, ts)} className="snapshot-chip glass"><span className="status-beacon" />Open the camera<span className="font-mono">↗</span></button>
        ) : (
          <div className="snapshot-chip glass"><span className="status-beacon" />{day.captures} captures read<span className="font-mono">{clock(ts)}</span></div>
        )}
      </section>

      {cam && (
        <div className="filter-row">
          {store.cameras.map((c) => <button key={c.id} aria-pressed={c.id === cam.id} onClick={() => go({ kind: "camera", cam: c.id })}>Camera {c.id} <span>{c.areas.length}</span></button>)}
        </div>
      )}

      <div className="metrics-grid grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Tile label="Average availability" sub={`lowest point of the day ${pct(day.lowest)}%`}><CountUp value={pct(day.available)} />%</Tile>
        <Tile label="Problems raised" sub={`${day.fixed} seen back in shape later`}><CountUp value={day.raised} /></Tile>
        <Tile label="Typical time to fix" sub={day.medianFix === null ? "nothing was fixed between captures" : "median, from first sighting to fixed"}>{day.medianFix === null ? "–" : <Dur seconds={day.medianFix} />}</Tile>
        <Tile label="Hardest moment" sub={<>{day.peak} area{day.peak === 1 ? "" : "s"} needed attention <span aria-hidden="true">↗</span></>} onClick={() => onJump(day.times[day.worst])} title="Jump to this moment"><span className="font-mono">{clock(day.times[day.worst])}</span></Tile>
      </div>

      <div className="an-grid">
        <Chart day={day} line={line} ts={ts} modes={day.hasCover ? ["attention", "stock", "compliant", "cover"] : ["attention", "stock", "compliant"]} onJump={onJump} i={0} />

        {/* ── the mix right now ────────────────────────────────── */}
        <section className="an-card glass-card" style={delay(1)}>
          <div className="an-head"><div><span className="eyebrow">AT {clock(ts)}</span><h3>Shelf mix</h3></div></div>
          <div className="an-donut">
            <svg viewBox="0 0 100 100" aria-hidden="true">
              <circle cx="50" cy="50" r="42" fill="none" stroke="rgb(var(--fg) / .07)" strokeWidth="9" />
              {mix.map(({ s, n, from }) => <circle key={s} cx="50" cy="50" r="42" fill="none" stroke={STATUS[s].color} strokeWidth="9" pathLength={100} strokeDasharray={`${Math.max(0, (n / total) * 100 - 0.8)} 100`} strokeDashoffset={-from} />)}
            </svg>
            <div className="an-donut-mid"><b className="tabular-nums"><CountUp value={pct(okNow / total)} />%</b><span>compliant</span></div>
          </div>
          {mix.map(({ s, n }) => (
            <div key={s} className="an-mix-row">
              <i style={{ background: STATUS[s].color }} />
              <span className="flex-1">{STATUS[s].label}</span>
              <span className="font-mono tabular-nums text-white"><CountUp value={n} /></span>
              <span className="w-10 text-right font-mono text-[11px] text-muted">{pct(n / total)}%</span>
            </div>
          ))}
        </section>

        {/* ── where and when ───────────────────────────────────── */}
        <section className="an-card glass-card" style={delay(2)}>
          <div className="an-head">
            <div><span className="eyebrow">WHERE AND WHEN</span><h3>{cam || product ? "Slot by hour" : "Camera by hour"}</h3><p>{cam || product ? "Each square is one slot at one hour. Click a name to open the slot." : "The stronger the colour, the larger the share of the camera that needed attention. Click a name to open the camera."}</p></div>
          </div>
          <Heat rows={heat} cols={cols} now={nowCol} label={product ? 96 : 56} />
        </section>

        {/* ── how sure the calls are ───────────────────────────── */}
        <section className="an-card glass-card" style={delay(3)}>
          <div className="an-head">
            <div><span className="eyebrow">AT {clock(ts)}</span><h3>How sure ShelfOS is</h3><p>{unsure ? `${unsure} call${unsure === 1 ? "" : "s"} under 60% deserve a second look.` : "Every call is above 60%."}</p></div>
            <div className="text-right shrink-0"><div className="font-mono text-2xl tabular-nums tracking-tight"><CountUp value={pct(meanSure)} />%</div><div className="text-[10px] text-muted">average</div></div>
          </div>
          <div className="an-hist">
            {hist.map((n, i) => (
              <div key={BINS[i]} title={`${n} areas at ${BINS[i]}–${BINS[i] + 10}%`}>
                <b>{n || ""}</b>
                <i style={{ ...delay(i), height: `${(n / histTop) * 92}px`, background: BINS[i] < 60 ? STATUS.low.color : undefined }} />
                <span>{BINS[i]}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── raised and fixed, hour by hour ───────────────────── */}
        <section className="an-card glass-card" style={delay(4)}>
          <div className="an-head">
            <div><span className="eyebrow">WORKLOAD</span><h3>Raised and fixed, hour by hour</h3><p>A problem is raised when a capture first shows it and fixed when a later one shows the area back in shape.</p></div>
            <div className="an-legend"><span><i style={{ background: "var(--ink)" }} />Raised</span><span><i style={{ background: STATUS.ok.color }} />Fixed</span></div>
          </div>
          <div className="an-flow">
            {flow.map((f, i) => (
              <button key={f.t} onClick={() => onJump(f.t)} title={`${clock(f.t)} · ${f.raised} raised, ${f.fixed} fixed`}>
                <div>
                  <i style={{ ...delay(i), height: `${(f.raised / flowTop) * 100}%` }} />
                  <i style={{ ...delay(i), height: `${(f.fixed / flowTop) * 100}%`, background: STATUS.ok.color }} />
                </div>
                <span data-now={i === nowCol}>{clock(f.t).slice(0, 2)}</span>
              </button>
            ))}
          </div>
        </section>

        {/* ── where the day went ───────────────────────────────── */}
        <section className="an-card glass-card" style={delay(5)}>
          <div className="an-head"><div><span className="eyebrow">TIME IN EACH STATE</span><h3>Where the day went</h3><p>Every area, every moment of the day, added up.</p></div></div>
          <div className="an-stack">{ORDER.map((s) => <i key={s} style={{ flexGrow: day.spent[s], background: STATUS[s].color }} />)}</div>
          {ORDER.map((s) => (
            <div key={s} className="an-mix-row">
              <i style={{ background: STATUS[s].color }} />
              <span className="flex-1">{STATUS[s].label}</span>
              <span className="font-mono tabular-nums text-white">{day.spent[s] ? duration(day.spent[s] * day.step) : "0"}</span>
              <span className="w-10 text-right font-mono text-[11px] text-muted">{pct(day.spent[s] / spentAll)}%</span>
            </div>
          ))}
        </section>

        {/* ── rankings ─────────────────────────────────────────── */}
        {!product && (
          <div className="an-wide an-split" style={delay(6)}>
            {!cam && (
              <section className="an-card glass-card">
                <div className="an-head"><div><span className="eyebrow">RANKED</span><h3>Cameras, weakest first</h3><p>Share of the day its areas were full and in place.</p></div></div>
                {groups.cameras.map((g, i) => (
                  <button key={g.rows[0].cam.id} onClick={() => go({ kind: "camera", cam: g.rows[0].cam.id })} className="an-rank" style={delay(i)}>
                    <span className="an-rank-n">{String(i + 1).padStart(2, "0")}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-3"><span className="truncate text-sm">Camera {g.rows[0].cam.id}</span><span className="font-mono text-xs tabular-nums">{pct(g.inShape)}%</span></span>
                      <span className="an-bar"><i style={{ width: `${g.inShape * 100}%` }} /></span>
                      <span className="block text-[10px] text-muted font-mono">{g.rows.length} areas · {g.rows.filter((r) => r.bad).length} had a problem today</span>
                    </span>
                    <span className="an-rank-go" aria-hidden="true">→</span>
                  </button>
                ))}
              </section>
            )}
            <section className="an-card glass-card">
              <div className="an-head"><div><span className="eyebrow">RANKED</span><h3>Products, lowest stock first</h3><p>Average stock level over the day, across all of its slots.</p></div></div>
              {shownProducts.map((g, i) => (
                <button key={g.rows[0].area.productId} onClick={() => go({ kind: "product", id: g.rows[0].area.productId })} className="an-rank" style={delay(i)}>
                  <ProductImage name={g.rows[0].area.rawName || g.rows[0].area.product} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-3"><span className="truncate text-sm">{g.rows[0].area.product}</span><span className="font-mono text-xs tabular-nums">{pct(g.stock)}%</span></span>
                    <span className="an-bar"><i style={{ width: `${g.stock * 100}%` }} /></span>
                    <span className="block text-[10px] text-muted font-mono">{g.rows.length} slot{g.rows.length === 1 ? "" : "s"} · {g.off >= 60 ? `off for ${duration(g.off)} on average` : "in shape all day"}</span>
                  </span>
                  <span className="an-rank-go" aria-hidden="true">→</span>
                </button>
              ))}
              {groups.products.length > 7 && <button onClick={() => setAllProducts(!allProducts)} className="an-more">{allProducts ? "Show fewer" : `Show all ${groups.products.length} products`}</button>}
            </section>
            {mixups.length > 0 && (
              <section className="an-card glass-card">
                <div className="an-head"><div><span className="eyebrow">AT {clock(ts)}</span><h3>Wrong product, and what it looks like</h3><p>The catalogue product each misplaced slot resembles most.</p></div></div>
                {mixups.map(({ t, like }, i) => (
                  <button key={t.key} onClick={() => go({ kind: "area", cam: t.cam.id, area: t.area.id })} className="an-rank" style={delay(i)}>
                    <Crop store={store} cam={t.cam} frame={t.frame} area={t.area} className="size-11 shrink-0 rounded-xl" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">{t.area.product}</span>
                      <span className="block truncate text-[11px]" style={{ color: STATUS.wrong.color }}>looks like {store.products?.[like![0]]?.name ?? `#${like![0]}`} <span className="font-mono text-muted">{pct(like![1])}%</span></span>
                      <span className="block text-[10px] text-muted font-mono">cam {t.cam.id} · slot {slot(t.area)}</span>
                    </span>
                    <span className="an-rank-go" aria-hidden="true">→</span>
                  </button>
                ))}
              </section>
            )}
          </div>
        )}

        {/* ── slot by slot ─────────────────────────────────────── */}
        <section className="an-card an-wide glass-card" style={delay(7)}>
          <div className="an-head">
            <div><span className="eyebrow">{cam || product ? "EVERY SLOT" : "LONGEST RUNNING"}</span><h3>{cam || product ? "The day, slot by slot" : "Areas off the longest"}</h3><p>Each band is the day, left to right. Click one to open the slot.</p></div>
            <Legend />
          </div>
          {ribbons.map((r, i) => (
            <button key={`${r.cam.id}/${r.area.id}`} onClick={() => go({ kind: "area", cam: r.cam.id, area: r.area.id, via })} className="an-row" style={delay(Math.min(i, 14))}>
              <Crop store={store} cam={r.cam} frame={frameAt(r.cam, ts)} area={r.area} className="size-11 rounded-xl" />
              <span className="min-w-0">
                <span className="block truncate text-sm">{r.area.product}</span>
                <span className="block text-[11px] text-muted font-mono">cam {r.cam.id} · slot {slot(r.area)}</span>
              </span>
              <Ribbon runs={r.runs} />
              <span className="text-right">
                <span className="block font-mono text-sm tabular-nums">{r.bad ? duration(r.bad * day.step) : "–"}</span>
                <span className="block text-[10px] text-muted">{r.bad ? `${pct(r.bad / N)}% of the day` : "in shape all day"}</span>
              </span>
            </button>
          ))}
          {ribbons.length === 0 && <div className="py-10 text-center text-sm text-muted">No area needed attention today.</div>}
        </section>
      </div>
    </>
  );
}

/** One slot: what it is now, how it moved, and every capture of it today. */
function Slot({
  store, cam, area, line, ts, onJump, onTime, onOpen,
}: { store: Store; cam: Camera; area: AreaDef; line: Line; ts: number; onJump: (t: number) => void; onTime: (t: number) => void; onOpen: () => void }) {
  const day = useMemo(() => readDay(store, line, (c, a) => c.id === cam.id && a.id === area.id), [store, line, cam.id, area.id]);
  const frame = frameAt(cam, ts);
  const p = frame.areas[area.id];
  const row = day.rows[0];
  const s = p ? statusOf(p) : "ok";
  const started = p ? since(cam, area.id, frame) : frame.ts;
  const held = Math.max(ts, frame.ts) - started;
  const shots = cam.frames.filter((f) => f.areas[area.id]);
  return (
    <>
      <section className="overview-heading">
        <div>
          <div className="eyebrow">CAMERA {cam.id} · SLOT {slot(area)} · {clock(frame.ts)}</div>
          <h1>{area.product}. <span>Slot {slot(area)}.</span></h1>
          <p>Planogram name {area.rawName} · product #{area.productId}</p>
        </div>
        <button onClick={onOpen} className="snapshot-chip glass"><span className="status-beacon" />See it on the camera<span className="font-mono">↗</span></button>
      </section>

      {!p ? (
        <div className="glass-card px-5 py-14 text-center text-sm text-muted">This slot was not read at {clock(ts)}.</div>
      ) : (
        <>
          <div className="metrics-grid grid grid-cols-2 xl:grid-cols-4 gap-3">
            <Tile label="State now" sub={STATUS[s].hint}><span className="an-tile-text" style={{ color: STATUS[s].color }}>{STATUS[s].label}</span></Tile>
            <Tile label="Shelf covered" sub="of the slot shows product">{p.map.length ? <><CountUp value={pct(p.occ)} />%</> : "–"}</Tile>
            <Tile label="In this state for" sub={`since ${clock(started)}`}>{held >= 60 ? <Dur seconds={held} /> : "–"}</Tile>
            <Tile label="Confidence" sub={row?.bad ? `off for ${duration(row.bad * day.step)} today` : "in shape all day"}><CountUp value={pct(confidence(p))} />%</Tile>
          </div>

          <div className="an-grid">
            <Chart day={day} line={line} ts={ts} modes={day.hasCover ? ["cover", "stock"] : ["stock"]} onJump={onJump} i={0} />

            <section className="an-card glass-card" style={delay(1)}>
              <div className="an-head"><div><span className="eyebrow">AT {clock(frame.ts)}</span><h3>The call</h3><p>What ShelfOS weighed to reach this answer.</p></div></div>
              <Crop store={store} cam={cam} frame={frame} area={area} className="an-shot" />
              {(["Empty", "Half", "Full"] as const).map((name, i) => (
                <div key={name} className="an-prob">
                  <span className={p.level === name.toLowerCase() ? "text-white" : ""}>{name}</span>
                  <span className="an-bar"><i style={{ width: `${p.probs[i] * 100}%`, opacity: p.level === name.toLowerCase() ? 1 : 0.35 }} /></span>
                  <b>{pct(p.probs[i])}%</b>
                </div>
              ))}
              <div className="an-prob an-prob-rule">
                <span className="text-white">Planogram</span>
                <span className="an-bar"><i style={{ width: `${p.level === "empty" ? 0 : p.pOk * 100}%`, background: p.ok ? STATUS.ok.color : STATUS.wrong.color }} /></span>
                <b>{p.level === "empty" ? "–" : `${pct(p.pOk)}%`}</b>
              </div>
            </section>

            <section className="an-card an-wide glass-card" style={delay(2)}>
              <div className="an-head">
                <div><span className="eyebrow">EVERY CAPTURE</span><h3>Through the day</h3><p>{shots.length} captures of this slot. Click one to go to that moment.</p></div>
                <Legend />
              </div>
              {row && <Ribbon runs={row.runs} />}
              <div className="an-film">
                {shots.map((f, i) => {
                  const st = statusOf(f.areas[area.id]);
                  return (
                    <button key={f.file} onClick={() => onTime(f.ts)} data-now={f.file === frame.file} style={delay(Math.min(i, 20))} title={`${clock(f.ts)} · ${STATUS[st].label}`}>
                      <Crop store={store} cam={cam} frame={f} area={area} className="an-film-shot" />
                      <span className="flex items-center justify-between gap-2"><span className="font-mono text-[11px]">{clock(f.ts)}</span><i style={{ background: STATUS[st].color }} /></span>
                      <span className="block truncate text-[10px] text-muted">{STATUS[st].label}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
        </>
      )}
    </>
  );
}
