"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { loadStore } from "../api";
import { clock, STATUS, Store, Task, tasksAt, timeline } from "../lib";
import { ProductImage, preloadProductImages } from "../product-image";
import { ThemeToggle } from "../theme";
import { ENTRY, locationOf, walkingOrder } from "./locations";
import { StoreMap } from "./store-map";
import { cameraConfirmed } from "./verification";
import "./staff.css";

const SAVE = "shelfos-staff-demo-v1";
const ACTION = { empty: "Repor agora", wrong: "Corrigir produto", low: "Repor stock", ok: "Tudo certo" };
function Icon({ kind }: { kind: "arrow" | "check" | "pin" | "list" | "reset" }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{kind === "arrow" ? <path d="M12 20V4m-6 6 6-6 6 6" /> : kind === "check" ? <path d="m5 12 4 4L19 6" /> : kind === "pin" ? <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></> : kind === "reset" ? <><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6" /></> : <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />}</svg>;
}

function FloorMap({ task, from, onPick, tasks, section }: { task?: Task; from: typeof ENTRY; onPick: (t: Task) => void; tasks: Task[]; section: string }) {
  const target = task && locationOf(task.cam.id);
  return <section className="staff-map glass-card"><div className="section-heading staff-map-heading"><div><span className="eyebrow">A TUA SECÇÃO</span><h2>{section}</h2></div><span className="snapshot-chip glass staff-map-demo"><Icon kind="pin" />Mapa demo</span></div>
    <div className="staff-map-destination"><span><i />Tu estás aqui</span><span>{target ? `Destino · ${target.zone}${target.bay}` : "Escolhe uma tarefa"}</span></div>
    <StoreMap task={task} from={from} tasks={tasks} />
    <div className="staff-map-picker filter-row" aria-label="Escolher zona">{[...new Set(tasks.map(t => t.cam.id))].map(id => { const l = locationOf(id); return <button key={id} aria-pressed={task?.cam.id === id} onClick={() => onPick(tasks.find(t => t.cam.id === id)!)}>{l ? `${l.zone}${l.bay}` : `Ref. ${id}`}</button>; })}</div>
  </section>;
}

function ShelfPosition({ task }: { task: Task }) {
  const all = task.cam.areas.flatMap(a => a.quad);
  const minX = Math.min(...all.map(p => p[0])), minY = Math.min(...all.map(p => p[1]));
  const w = Math.max(...all.map(p => p[0])) - minX || 1, h = Math.max(...all.map(p => p[1])) - minY || 1;
  return <div className="staff-shelf"><div><small>Encontra este lugar</small><span>Posição {task.area.id.split("_").pop()}</span></div><svg viewBox="0 0 280 105" role="img" aria-label={`Lugar ${task.area.id.split("_").pop()} destacado na prateleira`}>
    {task.cam.areas.map(a => <polygon key={a.id} points={a.quad.map(([x, y]) => `${12 + (x-minX)/w*256},${8+(y-minY)/h*89}`).join(" ")} className={a.id === task.area.id ? "shelf-active" : ""} />)}
  </svg></div>;
}

export default function Collaborators() {
  const [store, setStore] = useState<Store | null>(null);
  const [failed, setFailed] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [from, setFrom] = useState(ENTRY);
  const [selected, setSelected] = useState<string | null>(null);
  const [arrived, setArrived] = useState(false);
  const [tab, setTab] = useState<"route" | "tasks" | "done">("route");
  const [notice, setNotice] = useState("");
  const [ready, setReady] = useState(false);
  const [verified, setVerified] = useState<Task[]>([]);
  const [checking, setChecking] = useState(false);
  const [demoMode, setDemoMode] = useState(true);
  const [scanStage, setScanStage] = useState<"watching" | "analyzing" | "confirmed">("watching");
  const demoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeKey = useRef<string | null>(null); // the task on screen, for the polling effect below
  const cancelDemo = () => { if (demoTimer.current) clearTimeout(demoTimer.current); demoTimer.current = null; setChecking(false); };
  useEffect(() => {
    let alive = true, fetching = false;
    let previous: Store | null = null;
    const refresh = async () => {
      if (fetching || document.visibilityState === "hidden") return;
      fetching = true;
      try {
        const s = await loadStore();
        if (!alive || (previous?.live && !s.live)) return;
        const next = { ...s, cameras: s.cameras.filter(c => c.frames.length) };
        if (!previous) {
          try { const saved = JSON.parse(localStorage.getItem(SAVE) ?? "[]"); if (Array.isArray(saved)) setDone(saved.filter(v => typeof v === "string")); } catch {}
          setReady(true);
        } else if (next.live) {
          const fixed = cameraConfirmed(previous, next);
          if (fixed.length) {
            setVerified(old => [...old, ...fixed.filter(t => !old.some(v => v.key === t.key))]);
            setDone(old => [...new Set([...old, ...fixed.map(t => t.key)])]);
            setNotice(`${fixed.length} ${fixed.length === 1 ? "tarefa confirmada" : "tarefas confirmadas"} pela nova leitura`);
            if (fixed.some(t => t.key === activeKey.current)) { // the task on screen is done: the next one starts on the way, not "arrived"
              if (demoTimer.current) clearTimeout(demoTimer.current);
              demoTimer.current = null;
              setSelected(null); setArrived(false); setChecking(false);
            }
          }
        }
        previous = next;
        setStore(next);
        setFailed(false);
      } catch { if (alive && !previous) setFailed(true); }
      finally { fetching = false; }
    };
    void refresh();
    const poll = setInterval(() => void refresh(), 8000);
    return () => { alive = false; clearInterval(poll); if (demoTimer.current) clearTimeout(demoTimer.current); };
  }, []);
  useEffect(() => { if (ready) try { localStorage.setItem(SAVE, JSON.stringify(done)); } catch {} }, [done, ready]);
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(""), 3200); return () => clearTimeout(id); }, [notice]);
  const tasks = useMemo(() => {
    const current = store ? tasksAt(store, timeline(store).latest).filter(t => t.status !== "ok") : [];
    return [...current, ...verified.filter(t => !current.some(v => v.key === t.key))];
  }, [store, verified]);
  const completed = tasks.filter(t => done.includes(t.key));
  const open = useMemo(() => walkingOrder(tasks.filter(t => !done.includes(t.key)), from), [tasks, done, from]);
  const active = open.find(t => t.key === selected) ?? open[0];
  const activeId = active?.key ?? null;
  useEffect(() => { activeKey.current = activeId; }, [activeId]);
  useEffect(() => { preloadProductImages(tasks.map(t => t.area.rawName)); }, [tasks]);
  const pick = (t: Task) => { cancelDemo(); setSelected(t.key); setArrived(false); setTab("route"); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const simulate = () => {
    if (!active || checking) return;
    const task = active;
    setChecking(true); setScanStage("watching");
    demoTimer.current = setTimeout(() => {
      setScanStage("analyzing");
      demoTimer.current = setTimeout(() => {
        setScanStage("confirmed");
        setNotice("Reposição confirmada · simulação");
        demoTimer.current = setTimeout(() => {
      setDone(prev => [...new Set([...prev, task.key])]);
      setFrom(locationOf(task.cam.id) ?? ENTRY);
      setSelected(null); setArrived(false); setChecking(false);
      setNotice(`${task.area.product} · reposição detetada (simulação)`);
      demoTimer.current = null;
        }, 1400);
      }, 2200);
    }, 1800);
  };
  const reset = () => { cancelDemo(); setDone([]); setVerified([]); setFrom(ENTRY); setSelected(null); setArrived(false); setNotice("Demo reiniciada"); };
  const place = active && locationOf(active.cam.id);
  const arrive = () => {
    if (!active) return;
    setArrived(true); setFrom(locationOf(active.cam.id) ?? from);
    setScanStage("watching");
    if (demoMode) simulate();
    else setChecking(true);
  };
  const scanTitle = scanStage === "confirmed" ? "Reposição confirmada." : scanStage === "analyzing" ? "A analisar nova imagem…" : "A acompanhar a prateleira…";
  const percent = tasks.length ? Math.round(completed.length / tasks.length * 100) : store ? 100 : 0;
  return <main className="staff-app app-shell app-enter" lang="pt">
    <header className="staff-header app-header"><Link href="/" className="wordmark">Shelf<span>OS</span></Link><span className="staff-demo eyebrow">EQUIPA · DEMO</span><ThemeToggle /></header>
    <div className="staff-body">
      <section className="staff-greeting overview-heading"><div><span className="eyebrow">O TEU TURNO · {store ? clock(timeline(store).latest) : "SHELFOS"}</span><h1>O próximo passo.<br /><span>Mesmo à tua frente.</span></h1><p>{store ? `${open.length} tarefas por resolver · ${store.section || "Frutas e legumes"}` : "A preparar o teu percurso…"}</p></div></section>
      <div className="staff-progress shift-progress glass-card"><div><span>Resolvidas neste turno</span><span className="font-mono tabular-nums">{completed.length} / {tasks.length}</span></div><div className="shift-bar" role="progressbar" aria-label="Tarefas concluídas" aria-valuemin={0} aria-valuemax={tasks.length || 1} aria-valuenow={completed.length}><span style={{ width: `${percent}%` }} /></div></div>
      <div className="staff-mode"><span><i />{demoMode ? "Demo automática · resposta em segundos" : "Câmara ao vivo · aguarda novas imagens"}</span><button role="switch" aria-checked={demoMode} aria-label="Demo automática" onClick={() => { cancelDemo(); setArrived(false); setDemoMode(v=>!v); }}>{demoMode ? "Usar câmara real" : "Usar demo"}</button></div>
      <nav className="staff-tabs main-nav glass" aria-label="Vistas do colaborador">{([["route", "Percurso"], ["tasks", `Tarefas ${open.length}`], ["done", `Resolvidas ${completed.length}`]] as const).map(([id, label]) => <button className="nav-item" key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</nav>
      {failed ? <div className="staff-empty"><h2>Não conseguimos carregar as tarefas.</h2><button onClick={() => window.location.reload()}>Tentar novamente</button></div> : !store ? <div className="staff-skeleton" aria-label="A carregar tarefas" /> : tab === "route" && active ? <>
        <section className="staff-next glass-card" key={active.key}><div className="staff-next-top"><span><i style={{ background: STATUS[active.status].color }} />{ACTION[active.status]}</span><span>{checking ? demoMode ? "LEITURA SIMULADA" : "CÂMARA AO VIVO" : arrived ? "NO LOCAL" : "PRÓXIMA PARAGEM"}</span></div><div className="staff-product"><ProductImage name={active.area.rawName} /><div><h2>{active.area.product}</h2><p>{place ? `Zona ${place.zone} · Módulo ${place.bay}` : `Local por configurar · Ref. ${active.cam.id}`}</p></div></div>
          <div className="staff-direction"><Icon kind={arrived ? "check" : "arrow"} /><div><b>{arrived ? "Repõe. A câmara confirma." : place ? `Segue para a zona ${place.zone}.` : "Confirma a localização com a equipa."}</b><p>{arrived ? active.status === "wrong" ? "Coloca aqui o produto indicado." : "A tarefa desaparece quando uma nova leitura mostrar o produto correto e stock completo." : place ? `Procura o módulo ${place.bay}, na ${place.zone === "A" ? "esquerda" : "direita"} da secção.` : `Prateleira identificada pela câmara ${active.cam.id}.`}</p></div></div>
          {arrived && <><ShelfPosition task={active} /><div className={`staff-auto-check ${checking ? "is-checking" : ""}`} role="status"><span className="staff-scan-icon"><Icon kind="check" /></span><div><b>{checking ? scanTitle : "Confirmação automática"}</b><p>{demoMode ? scanStage === "confirmed" ? "Produto correto · stock completo · demo" : "Simulação automática · sem alterar previsões" : "À espera de uma nova imagem real da câmara"}</p></div></div></>}
        </section>
        <FloorMap task={active} from={from} onPick={pick} tasks={open} section={store.section || "Frutas e Legumes"} />
        <div className="staff-data-note">Leitura {clock(active.frame.ts)} · {active.pred.source === "memory" ? "Último estado conhecido — verifica no local" : "Confirma o estado no local"}</div>
        {open[1] && <button className="staff-following" onClick={() => pick(open[1])}><span>A seguir</span><ProductImage name={open[1].area.rawName} /><b>{open[1].area.product}</b><span>↗</span></button>}
      </> : tab === "route" ? <div className="staff-empty"><div className="staff-complete-icon"><Icon kind="check" /></div><h2>{tasks.length ? "Turno impecável." : "Tudo em ordem."}</h2><p>{tasks.length ? "Todas as tarefas desta leitura estão concluídas." : "Não há tarefas nesta leitura."}</p><button onClick={reset}>Reiniciar demo</button></div> : <div className="staff-list">{(tab === "done" ? completed : open).map(t => { const l = locationOf(t.cam.id); return <button className="task-card glass-card" key={t.key} onClick={() => { if (tab !== "done") pick(t); }}><ProductImage name={t.area.rawName} /><div><b>{t.area.product}</b><small>{l ? `Zona ${l.zone} · Módulo ${l.bay}` : `Ref. ${t.cam.id}`} · {tab === "done" ? verified.some(v => v.key === t.key) ? "Confirmado pela câmara" : "Confirmado na simulação" : ACTION[t.status]}</small></div><span style={{ color: STATUS[t.status].color }}><Icon kind={tab === "done" ? "check" : "pin"} /></span></button>; })}{!(tab === "done" ? completed : open).length && <div className="staff-empty"><h2>{tab === "done" ? "O primeiro passo é teu." : "Tudo em ordem."}</h2><p>{tab === "done" ? "As tarefas concluídas aparecem aqui." : "Não há tarefas pendentes."}</p></div>}</div>}
      <footer className="staff-footnote">Planta e deslocação simuladas. Novas leituras confirmam as tarefas automaticamente. A simulação não altera as previsões.<button onClick={reset}><Icon kind="reset" /> Reiniciar demo</button></footer>
    </div>
    {store && tab === "route" && active && <div className="staff-bottom glass"><div><small>{place ? `ZONA ${place.zone} / ${place.bay}` : `REF. ${active.cam.id}`}</small><b>{arrived ? scanStage === "confirmed" ? "Reposição confirmada." : "A câmara está a acompanhar." : "Vamos a isso."}</b></div>{arrived ? <span className={`staff-live-status ${scanStage === "confirmed" ? "is-confirmed" : ""}`}><i />{scanStage === "confirmed" ? "Confirmado" : "A analisar"}<small>{demoMode ? "DEMO" : "AO VIVO"}</small></span> : <button className="nav-item" onClick={arrive}><Icon kind="pin" />Já estou aqui</button>}</div>}
    <div className={`staff-toast ${notice ? "visible" : ""}`} role="status" aria-live="polite"><Icon kind="check" />{notice}</div>
  </main>;
}
