/**
 * Backtest of the run-out forecast the app shows (web/app/forecast.ts), against the silver labels.
 *
 * At every capture of every area, forecast from the captures up to then only, and compare with the
 * first capture labelled empty afterwards. The pass mark was fixed before any result was seen
 * (docs/Plano.md, idea C): median error at most 60 min, at least 15 distinct run-outs forecast, and at
 * most a third of the judged forecasts announcing a run-out that never came.
 *
 * usage: node --experimental-strip-types tools/forecast_backtest.ts cache/forecast_series.json [--signal fill|occ] [--area 6215_9]
 *        (Node >= 22.12; or: npx tsx tools/forecast_backtest.ts ...)
 * input: python tools/forecast_series.py (out-of-fold readings, so the model never saw the frame it reads)
 */
import { readFileSync } from "node:fs";
import { forecast, MIN_POINTS, type Point, type Signal } from "../web/app/forecast.ts";

type Reading = Point & { label: 0 | 1 | 2 | null };

const MAX_ERROR = 60 * 60;
const MIN_EVENTS = 15;
const MAX_FALSE_ALARMS = 1 / 3;

const args = process.argv.slice(2);
const flag = (name: string) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const path = args.find((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
if (!path) {
  console.error("usage: tools/forecast_backtest.ts <forecast_series.json> [--signal fill|occ] [--area <id>]");
  process.exit(2);
}
const signal = (flag("--signal") ?? "fill") as Signal;
const only = flag("--area");
const series: Record<string, Reading[]> = JSON.parse(readFileSync(path, "utf8"));

const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Lisbon" });
const median = (v: number[]) => {
  if (!v.length) return NaN;
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

const errors: number[] = [];
const predicted = new Set<string>(); // run-outs with at least one forecast pointing at them
let forecasts = 0, falseAlarms = 0, censored = 0, stable = 0, silent = 0;
let events = 0, caught = 0; // run-outs, and those forecast at the last capture before them

for (const [area, pts] of Object.entries(series)) {
  if (only && area !== only) continue;
  const labels = pts.map((p) => p.label);
  for (let i = 0; i < pts.length; i++) {
    const lab = labels[i];
    if (lab === null || lab === 0) continue;
    const out = forecast(pts.slice(0, i + 1), pts[i].ts, signal);
    if (only) console.log(`${area} ${hhmm(pts[i].ts)} label ${"EHF"[lab]}: ${out === null ? "-" : out.kind === "stable" ? "stable" : `empty by ${hhmm(out.at)}`}`);

    // was this capture the last one before a run-out?
    let next = i + 1;
    while (next < pts.length && labels[next] === null) next++;
    const lastBeforeEmpty = next < pts.length && labels[next] === 0;
    if (lastBeforeEmpty) {
      events++;
      if (out?.kind === "empties") caught++;
    }

    if (out === null) { silent++; continue; }
    if (out.kind === "stable") { stable++; continue; }
    forecasts++;

    // truth: the first capture labelled empty, unless the slot is restocked or the day ends first
    let prev: number = lab, end = pts[pts.length - 1].ts, hit = -1;
    for (let j = i + 1; j < pts.length; j++) {
      const l = labels[j];
      if (l === null) continue;
      if (l === 0) { hit = j; break; }
      if (l > prev) { end = pts[j].ts; break; } // any step up in the labels is a restock
      prev = l;
    }
    if (hit >= 0) {
      errors.push(out.at - pts[hit].ts);
      predicted.add(`${area}@${pts[hit].ts}`);
    } else if (out.at <= end) falseAlarms++;
    else censored++;
  }
}

const abs = errors.map(Math.abs);
const judged = errors.length + falseAlarms;
const medAbs = median(abs);
const faRate = judged ? falseAlarms / judged : NaN;
const min = (s: number) => `${Math.round(s / 60)} min`;
const pass = medAbs <= MAX_ERROR && predicted.size >= MIN_EVENTS && faRate <= MAX_FALSE_ALARMS;

console.log(`
run-out forecast backtest · signal ${signal} · MIN_POINTS ${MIN_POINTS}${only ? ` · area ${only}` : ""}
captures judged          ${forecasts + stable + silent} (no forecast ${silent}, stable ${stable}, empties ${forecasts})
forecasts with a run-out ${errors.length}   false alarms ${falseAlarms}   beyond the day ${censored}
distinct run-outs        ${predicted.size} forecast, of ${events} in the labels; ${caught} forecast at the last capture before
median error             ${min(medAbs)} (signed ${min(median(errors))}; positive = forecast too late)
within ±60 min           ${errors.length ? Math.round((100 * abs.filter((e) => e <= MAX_ERROR).length) / errors.length) : 0}%
false alarm rate         ${Number.isNaN(faRate) ? "-" : `${Math.round(100 * faRate)}%`}

pass mark: median ≤ 60 min, ≥ ${MIN_EVENTS} distinct run-outs, false alarms ≤ 33%   →   ${pass ? "PASS" : "FAIL"}
note: one capture every ~70 min, so the "true" run-out time is itself only known to about ±35 min.`);
