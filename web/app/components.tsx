"use client";

import type React from "react";
import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import { ACCENT, AreaDef, Camera, Frame, ISSUES, ORDER, STATUS, Status, Store, bbox, centroid, clock, duration, frameAt, frameSrc, points, productName, since, statusOf } from "./lib";

/** Camera image with the planogram areas drawn on it. */
export const FrameView = memo(function FrameView({
  store, cam, frame, filter = "all", compact = false, fit = false, areaId, hover, onHover, onSelect,
}: {
  store: Store; cam: Camera; frame: Frame; filter?: Status | "all"; compact?: boolean; fit?: boolean;
  areaId?: string | null; hover?: string | null; onHover?: (id: string | null) => void; onSelect?: (id: string) => void;
}) {
  const { width: w, height: h } = store;
  const svg = useRef<SVGSVGElement>(null);
  const [visible, setVisible] = useState(!compact);
  const [loaded, setLoaded] = useState(false);
  const vignette = useId();
  useEffect(() => {
    if (visible || !svg.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "300px" });
    observer.observe(svg.current);
    return () => observer.disconnect();
  }, [visible]);
  return (
    <svg ref={svg} viewBox={`0 0 ${w} ${h}`} className={`frame-view select-none ${fit ? "camera-frame-fit" : "block w-full h-auto"}`} data-loaded={loaded}>
      <rect width={w} height={h} fill="none" />
      {visible && <image className="frame-image" href={frameSrc(store, cam, frame)} width={w} height={h} onLoad={() => setLoaded(true)} />}
      {!compact && <rect width={w} height={h} fill={`url(#${vignette})`} pointerEvents="none" />}
      <defs>
        <radialGradient id={vignette} cx="50%" cy="50%" r="75%">
          <stop offset="60%" stopColor="#000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000" stopOpacity="0.45" />
        </radialGradient>
      </defs>
      {visible && cam.areas.map((a) => {
        const p = frame.areas[a.id];
        if (!p) return null;
        const s = statusOf(p);
        const active = a.id === areaId || a.id === hover;
        const dim = filter !== "all" && filter !== s;
        const quiet = s === "ok";
        const [cx, cy] = centroid(a.quad, w, h);
        return (
          <g key={a.id} opacity={dim ? 0.18 : 1} className="transition-opacity">
            <polygon
              points={points(a.quad)}
              fill={STATUS[s].color}
              fillOpacity={active ? 0.25 : quiet ? 0 : 0.13}
              stroke={STATUS[s].color}
              strokeWidth={active ? 4.5 : quiet ? (compact ? 1.5 : 1.25) : compact ? 4 : 2.75}
              strokeOpacity={quiet && !active ? 0.5 : 1}
              strokeDasharray={p.source === "memory" ? "10 7" : undefined}
              strokeLinejoin="round"
              className={`shelf-region ${onSelect ? "cursor-pointer" : ""} ${s === "empty" && !active && !compact ? "pulse" : ""}`}
              onMouseEnter={onHover && (() => onHover(a.id))}
              onMouseLeave={onHover && (() => onHover(null))}
              onClick={onSelect && (() => onSelect(a.id))}
            />
            {!quiet && !compact && (
              <g pointerEvents="none">
                <circle cx={cx} cy={cy} r={13} fill="#05070a" fillOpacity={0.85} stroke={STATUS[s].color} strokeWidth={2} />
                <text x={cx} y={cy + 5.5} textAnchor="middle" fontSize={16} fontWeight={700} fill={STATUS[s].color}>
                  {STATUS[s].glyph}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
});

export function CameraStage({
  store, cam, frame, areaId, filter, onSelect,
}: { store: Store; cam: Camera; frame: Frame; areaId: string | null; filter: Status | "all"; onSelect: (id: string | null) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const hovered = hover ? cam.areas.find((a) => a.id === hover) : undefined;
  const hp = hovered && frame.areas[hovered.id];
  return (
    <div className="camera-fit-slot">
    <div className="camera-stage fitted relative overflow-hidden bg-black" style={{ "--frame-ar": store.width / store.height } as React.CSSProperties}>
      <FrameView store={store} cam={cam} frame={frame} filter={filter} fit areaId={areaId} hover={hover} onHover={setHover} onSelect={(id) => onSelect(id === areaId ? null : id)} />
      <div className="glass-chip absolute left-3 top-3 font-mono">
        CAM {cam.id} · {clock(frame.ts)}
        {frame.origin === "run" && <span className="text-white/60">· tested image</span>}
      </div>
      {hovered && hp && (
        <div className="glass-chip absolute right-3 top-3 text-xs">
          <span className="size-2 rounded-full" style={{ background: STATUS[statusOf(hp)].color }} />
          <span>{hovered.product}</span>
          <span className="text-muted">· {STATUS[statusOf(hp)].label}</span>
        </div>
      )}
      <div className="glass-chip absolute left-3 bottom-3 max-sm:hidden gap-3 text-[10px] text-white/80">
        {ORDER.map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full" style={{ background: STATUS[s].color }} />
            {STATUS[s].label}
          </span>
        ))}
      </div>
      {!!frame.warnings?.length && (
        <div className="glass-chip absolute right-3 bottom-3 max-w-[60%] text-low">⚠ {frame.warnings.join(" · ")}</div>
      )}
    </div>
    </div>
  );
}

export const Crop = memo(function Crop({ store, cam, frame, area, className }: { store: Store; cam: Camera; frame: Frame; area: AreaDef; className?: string }) {
  const b = bbox(area.quad, store.width, store.height);
  return (
    <svg viewBox={`${b.x} ${b.y} ${b.w} ${b.h}`} preserveAspectRatio="xMidYMid slice" className={`crop ${className ?? ""}`}>
      <image href={frameSrc(store, cam, frame)} width={store.width} height={store.height} />
    </svg>
  );
});

/** One headline number, a ring for how far it is from perfect, and how it moved over the day. */
export const Kpi = memo(function Kpi({
  label, value, sub, tone, share, trend, at, children,
}: { label: string; value: string; sub: string; tone: Status | "accent"; share?: number; trend?: number[]; at?: number; children?: React.ReactNode }) {
  const color = tone === "accent" ? ACCENT : STATUS[tone].color;
  const fill = useId();
  const lo = trend ? Math.min(...trend) : 0;
  const span = trend ? Math.max(1e-6, Math.max(...trend) - lo) : 1;
  // Leave room for the marker's radius and halo at both vertical extremes.
  const y = (v: number) => 24 - ((v - lo) / span) * 16;
  const pts = trend?.map((v, i) => `${((i / (trend.length - 1)) * 100).toFixed(2)},${y(v).toFixed(2)}`).join(" ");
  const now = trend && at !== undefined ? trend[Math.round(at * (trend.length - 1))] : undefined;
  return (
    <div className="metric-card glass-card relative overflow-hidden" style={{ "--tone": color } as React.CSSProperties}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-muted"><span className="size-1.5 rounded-full" style={{ background: color }} />{label}</div>
          <div className="metric-value leading-none tabular-nums"><Count text={value} /></div>
          <div className="text-xs text-muted truncate">{sub}</div>
        </div>
        {share !== undefined && (
          <svg className="metric-ring" viewBox="0 0 44 44" aria-hidden="true">
            <circle cx="22" cy="22" r="18" fill="none" stroke="rgb(var(--fg) / .08)" strokeWidth="4" />
            <circle cx="22" cy="22" r="18" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" pathLength={100} strokeDasharray={`${Math.max(0.01, share * 100)} 100`} transform="rotate(-90 22 22)" />
          </svg>
        )}
        {children}
      </div>
      {pts && (
        <div className="metric-spark" title="Over the day">
          <svg viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id={fill} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={color} stopOpacity="0.28" />
                <stop offset="1" stopColor={color} stopOpacity="0" />
              </linearGradient>
            </defs>
            <polygon points={`0,32 ${pts} 100,32`} fill={`url(#${fill})`} />
            <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </svg>
          {now !== undefined && at !== undefined && <i style={{ left: `calc(${at * 100}% + ${10 - at * 20}px)`, top: `${(y(now) / 32) * 100}%`, background: color }} />}
        </div>
      )}
    </div>
  );
});

const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

/** One column of an odometer: the ten digits stacked, slid so the right one shows. */
function Digit({ d, delay }: { d: number; delay: number }) {
  const [at, setAt] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setAt(d));
    return () => cancelAnimationFrame(id);
  }, [d]);
  return (
    <span className="roll-digit">
      <span style={{ transform: `translateY(${-at * 10}%)`, transitionDelay: `${delay}ms` }}>
        {DIGITS.map((n) => <span key={n}>{n}</span>)}
      </span>
    </span>
  );
}

/** A number whose digits roll into place like an odometer, and roll on when the value changes. */
export function CountUp({ value }: { value: number }) {
  const digits = String(Math.max(0, Math.round(value))).split("");
  return (
    <>
      <span className="sr-only">{value}</span>
      <span className="roll" aria-hidden="true">
        {/* keyed by place from the right, so the units column stays the units column */}
        {digits.map((d, i) => <Digit key={digits.length - i} d={Number(d)} delay={i * 55} />)}
      </span>
    </>
  );
}

/** Text that starts with a number ("93%"): the number counts up, the rest stays. */
function Count({ text }: { text: string }) {
  const m = /^(\d+)(.*)$/.exec(text);
  return m ? <><CountUp value={Number(m[1])} />{m[2]}</> : <>{text}</>;
}

/** Small count badges for one camera frame: how many areas need each action. */
export function Badges({ n }: { n: Record<Status, number> }) {
  const any = ISSUES.some((s) => n[s]);
  return (
    <span className="flex gap-1">
      {ISSUES.map((s) =>
        n[s] ? (
          <span key={s} className="glass-chip font-mono" title={`${n[s]} ${STATUS[s].label.toLowerCase()}`}>
            <span className="size-1.5 rounded-full" style={{ background: STATUS[s].color }} />
            {n[s]}
          </span>
        ) : null,
      )}
      {!any && <span className="glass-chip text-white/75">all compliant</span>}
    </span>
  );
}

/** The whole day at a glance: open issues over time, with the scrubber on top. */
export function DayStrip({ store, ts, line, onChange }: { store: Store; ts: number; line: { min: number; max: number; latest: number }; onChange: (ts: number) => void }) {
  const N = 84;
  const bins = useMemo(() => {
    const out: { t: number; n: Record<Status, number> }[] = [];
    for (let i = 0; i < N; i++) {
      const t = i === N - 1 ? line.latest : line.min + ((line.max - line.min) * i) / (N - 1);
      const n: Record<Status, number> = { empty: 0, wrong: 0, low: 0, ok: 0 };
      for (const cam of store.cameras) {
        const f = frameAt(cam, t);
        for (const a of cam.areas) if (f.areas[a.id]) n[statusOf(f.areas[a.id])]++;
      }
      out.push({ t: line.min + ((line.max - line.min) * i) / (N - 1), n });
    }
    return out;
  }, [store, line.min, line.max, line.latest]);
  const peak = Math.max(1, ...bins.map((b) => b.n.empty + b.n.wrong + b.n.low));
  const hours = useMemo(() => {
    const out: number[] = [];
    for (let t = Math.ceil(line.min / 3600) * 3600; t <= line.max; t += 3600) out.push(t);
    return out;
  }, [line.min, line.max]);
  const tested = useMemo(() => store.cameras.flatMap((c) => c.frames.filter((f) => f.origin === "run").map((f) => f.ts)), [store]);
  const pos = (t: number) => Math.min(100, Math.max(0, ((t - line.min) / Math.max(1, line.max - line.min)) * 100));
  return (
    <div className="relative flex-1 h-[60px] min-w-0">
      <div className="absolute inset-x-0 top-0 h-9 flex items-end gap-px overflow-hidden">
        {bins.map((b, i) => (
          <div key={i} className="flex-1 flex flex-col-reverse" style={{ opacity: b.t <= ts ? 1 : 0.28 }}>
            {ISSUES.map((s) => (
              <span key={s} style={{ height: `${(b.n[s] / peak) * 36}px`, background: STATUS[s].color }} />
            ))}
          </div>
        ))}
      </div>
      {tested.map((t, i) => (
        <span key={i} className="absolute top-[35px] h-[5px] w-[2px] -translate-x-1/2 rounded-full pointer-events-none" style={{ left: `${pos(t)}%`, background: ACCENT }} />
      ))}
      <div className="absolute top-0 h-9 w-px bg-white/90 pointer-events-none" style={{ left: `${pos(ts)}%` }}>
        <span className="absolute -top-0.5 -left-[4px] size-[9px] rounded-full bg-white shadow-[0_0_12px_rgb(var(--fg)_/_0.8)]" />
      </div>
      <div className="absolute inset-x-0 top-9 h-px bg-line" />
      {hours.map((t, i) => (
        <span key={t} className={`absolute top-[46px] -translate-x-1/2 text-[9px] leading-none font-mono text-muted ${i % 3 ? "hidden md:inline" : ""}`} style={{ left: `${pos(t)}%` }}>
          {clock(t).slice(0, 2)}h
        </span>
      ))}
      <input
        aria-label="Time of day"
        className="scrub absolute inset-x-0 top-0 h-9 opacity-0"
        type="range"
        min={line.min}
        max={line.max}
        step={60}
        value={Math.min(ts, line.max)}
        onChange={(e) => onChange(Number(e.target.value) >= line.max ? line.latest : Number(e.target.value))}
      />
    </div>
  );
}

export function AreaDetail({ store, cam, frame, area, onPick, onClose }: { store: Store; cam: Camera; frame: Frame; area: AreaDef; onPick: (ts: number) => void; onClose: () => void }) {
  const p = frame.areas[area.id];
  const s = statusOf(p);
  const b = bbox(area.quad, store.width, store.height);
  const [showMap, setShowMap] = useState(false);
  // the frame where this area looked best today, as a visual reference
  const best = useMemo(() => {
    let top = cam.frames[0];
    for (const f of cam.frames) {
      const q = f.areas[area.id];
      const r = top.areas[area.id];
      if (q && q.ok && q.level === "full" && (!r || !(r.ok && r.level === "full") || q.occ > r.occ)) top = f;
    }
    return top;
  }, [cam, area.id]);
  const started = since(cam, area.id, frame);
  const hasMap = p.map.length > 0;
  const looks = (p.looks ?? []).filter(([id]) => id !== area.productId).slice(0, 2);
  return (
    <div className="popup-backdrop" onClick={onClose}>
    <section role="dialog" aria-modal="true" aria-label={area.product} onClick={(e) => e.stopPropagation()} className="popup glass px-5 sm:px-6 pb-6 pt-4 grid md:grid-cols-[minmax(0,300px)_1fr] gap-x-7 gap-y-3">
      <div className="col-span-full flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">
          Camera {cam.id} · slot {area.id.split("_")[1]}
        </span>
        <button onClick={onClose} aria-label="Close" title="Back to all areas (Esc)" className="-mr-2 size-8 grid place-items-center rounded-full text-muted hover:text-white hover:bg-raised">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="m1.5 1.5 8 8m0-8-8 8" /></svg>
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 self-start">
        <figure>
          <div className="relative">
            <svg viewBox={`${b.x} ${b.y} ${b.w} ${b.h}`} className="w-full aspect-square rounded-lg bg-black" preserveAspectRatio="xMidYMid slice">
              <image href={frameSrc(store, cam, frame)} width={store.width} height={store.height} />
              <polygon points={points(area.quad)} fill="none" stroke={STATUS[s].color} strokeWidth={Math.max(b.w, b.h) / 90} strokeLinejoin="round" />
            </svg>
            {showMap && hasMap && (
              <div className="absolute inset-[9%] grid rounded overflow-hidden mix-blend-screen" style={{ gridTemplateColumns: `repeat(${p.map.length}, 1fr)` }}>
                {p.map.flat().map((v, i) => (
                  <span key={i} style={{ background: `rgb(var(--fg) / ${v * 0.6})` }} />
                ))}
              </div>
            )}
          </div>
          <figcaption className="mt-1.5 text-[10px] uppercase tracking-[0.12em] text-muted">Now · {clock(frame.ts)}</figcaption>
        </figure>
        <figure>
          <button onClick={() => onPick(best.ts)} className="block w-full" title="Jump to this moment">
            <svg viewBox={`${b.x} ${b.y} ${b.w} ${b.h}`} className="w-full aspect-square rounded-lg bg-black opacity-90 hover:opacity-100" preserveAspectRatio="xMidYMid slice">
              <image href={frameSrc(store, cam, best)} width={store.width} height={store.height} />
            </svg>
          </button>
          <figcaption className="mt-1.5 text-[10px] uppercase tracking-[0.12em] text-muted">At its best · {clock(best.ts)}</figcaption>
        </figure>
        {hasMap && (
          <button onClick={() => setShowMap(!showMap)} className={`col-span-2 mt-1 rounded-md border px-2.5 py-1.5 text-[11px] transition-colors ${showMap ? "border-white/30 text-white bg-white/10" : "border-line text-muted hover:text-white"}`}>
            {showMap ? "Hide" : "Show"} what ShelfOS sees as product
          </button>
        )}
      </div>

      <div className="min-w-0 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-medium whitespace-nowrap" style={{ color: STATUS[s].color }}>
              <span className="size-4 grid place-items-center rounded-full text-[10px] font-bold text-[#09090b]" style={{ background: STATUS[s].color }}>
                {STATUS[s].glyph}
              </span>
              {STATUS[s].label} · {STATUS[s].action}
            </div>
            <h2 className="mt-1 text-2xl font-medium tracking-tight truncate">{area.product}</h2>
            <div className="text-[11px] text-muted font-mono truncate">
              {area.rawName} · #{area.productId}
            </div>
            {s !== "ok" && frame.ts > started && <div className="mt-1 text-[11px] text-muted">Like this for {duration(frame.ts - started)}</div>}
          </div>
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted whitespace-nowrap">Shelf covered</div>
            <div className="font-mono text-3xl tabular-nums tracking-tight">{hasMap ? `${Math.round(p.occ * 100)}%` : "–"}</div>
          </div>
        </div>

        {p.source === "memory" && (
          <div className="rounded-md border border-low/40 bg-low/10 px-3 py-2 text-xs text-low">
            This image could not be read here. The answer is the last known state of the slot, so the output file is still complete.
          </div>
        )}
        {p.source !== "memory" && (p.obstruction ?? 0) >= 0.3 && (
          <div className="rounded-md border border-low/40 bg-low/10 px-3 py-2 text-xs text-low">
            About {Math.round((p.obstruction ?? 0) * 100)}% of this slot is covered by something that was never on this shelf today (a shopper, a cart, boxes, a cloth). What is underneath cannot be seen, so the stock level is answered on the low side.
          </div>
        )}

        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted mb-2">Stock level</div>
            {(["Empty", "Half", "Full"] as const).map((name, i) => {
              const on = p.level === name.toLowerCase();
              return (
                <div key={name} className="flex items-center gap-2 text-xs mb-1.5">
                  <span className={`w-10 ${on ? "text-white font-medium" : "text-muted"}`}>{name}</span>
                  <div className="flex-1 h-1.5 rounded bg-line overflow-hidden">
                    <div className="h-full rounded transition-[width] duration-300" style={{ width: `${p.probs[i] * 100}%`, background: on ? STATUS[s === "wrong" ? (p.level === "half" ? "low" : "ok") : s].color : "#3b4754" }} />
                  </div>
                  <span className="font-mono tabular-nums w-9 text-right text-muted">{Math.round(p.probs[i] * 100)}%</span>
                </div>
              );
            })}
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted mb-2">Planogram match</div>
            <div className="flex items-center gap-2 text-xs">
              <div className="flex-1 h-1.5 rounded bg-line overflow-hidden">
                <div className="h-full rounded transition-[width] duration-300" style={{ width: `${p.level === "empty" ? 0 : p.pOk * 100}%`, background: p.ok ? STATUS.ok.color : STATUS.wrong.color }} />
              </div>
              <span className="font-mono tabular-nums w-9 text-right text-muted">{p.level === "empty" ? "–" : `${Math.round(p.pOk * 100)}%`}</span>
            </div>
            <p className="mt-2 text-xs text-muted leading-relaxed">
              {p.level === "empty"
                ? `Nothing on the shelf to compare with the planogram. Reported as ${p.ok ? "compliant" : "not compliant"}.`
                : p.ok
                  ? `Looks like ${area.product}, as planned.`
                  : `Does not look like ${area.product}.`}
              {!p.ok && p.level !== "empty" && looks.length > 0 && (
                <>
                  {" "}
                  Looks most like{" "}
                  {looks.map(([id, sim], i) => (
                    <span key={id}>
                      {i > 0 && " or "}
                      <span className="text-white">{productName(store, id)}</span> <span className="font-mono text-[10px]">{Math.round(sim * 100)}%</span>
                    </span>
                  ))}
                  .
                </>
              )}
            </p>
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-muted mb-2">This slot today</div>
          <div className="flex gap-1">
            {cam.frames.map((f) => {
              const q = f.areas[area.id];
              if (!q) return null;
              const st = statusOf(q);
              const current = f.file === frame.file;
              return (
                <button key={f.file} onClick={() => onPick(f.ts)} className="flex-1 group" title={`${clock(f.ts)} · ${STATUS[st].label}${f.origin === "run" ? " · tested image" : ""}`}>
                  <div className={`h-10 rounded-sm flex items-end overflow-hidden bg-line ${current ? "ring-1 ring-white/70" : ""}`}>
                    <div className="w-full transition-[height]" style={{ height: `${Math.max(6, (q.map.length ? q.occ : LEVEL_FILL[q.level]) * 100)}%`, background: STATUS[st].color, opacity: current ? 1 : 0.55 }} />
                  </div>
                  <div className={`mt-1 text-[9px] font-mono text-center ${f.origin === "run" ? "text-accent" : current ? "text-white" : "text-muted group-hover:text-white"}`}>{clock(f.ts).slice(0, 2)}h</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
    </div>
  );
}

const LEVEL_FILL = { empty: 0.06, half: 0.5, full: 1 };

/** Every planogram area of one camera image, worst first: the way in when nothing is selected. */
export function AreaList({ cam, frame, onSelect }: { cam: Camera; frame: Frame; onSelect: (id: string) => void }) {
  const rows = cam.areas
    .filter((a) => frame.areas[a.id])
    .map((a) => ({ a, p: frame.areas[a.id], s: statusOf(frame.areas[a.id]) }))
    .sort((x, y) => STATUS[x.s].rank - STATUS[y.s].rank || x.a.id.localeCompare(y.a.id, undefined, { numeric: true }));
  const todo = rows.filter((r) => r.s !== "ok").length;
  const groups = ORDER.map((s) => ({ s, rows: rows.filter((r) => r.s === s) })).filter((g) => g.rows.length);
  return (
    <section className="camera-areas glass-card" aria-label={`Camera ${cam.id} planogram`}>
      <div className="camera-areas-head">
        <div className="text-[10px] uppercase tracking-[0.14em] text-muted">
          Camera {cam.id} · {clock(frame.ts)}
        </div>
        <div className="mt-1 text-[15px] font-medium tracking-tight leading-snug">
          {rows.length} planogram areas
          {todo ? <span style={{ color: STATUS[rows[0].s].color }}> · {todo} need attention</span> : <span className="text-muted"> · all compliant</span>}
        </div>
      </div>
      <div className="camera-area-scroll">
        {groups.map((g) => (
          <div key={g.s}>
            <div className="area-group"><i style={{ background: STATUS[g.s].color }} />{STATUS[g.s].label}<span>{g.rows.length}</span></div>
            {g.rows.map(({ a, s }) => (
              <button key={a.id} onClick={() => onSelect(a.id)} className="area-row" title={STATUS[s].hint}>
                <span className="area-dot" style={{ background: STATUS[s].color, opacity: s === "ok" ? 0.45 : 1 }} />
                <span className="area-copy">
                  <strong>{a.product}</strong>
                  <small>slot {a.id.split("_")[1]} · {STATUS[s].hint}</small>
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
