"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { apiBase } from "./api";
import { clock, frameAt, statusOf, STATUS, Status, Store } from "./lib";
import { ProductImage } from "./product-image";

type AreaCard = { area: string; camera: string; product: string; status: Status; captured_at: number; product_id?: string };
type WidgetData = { changes: { now_full: number; new_empty: number; compared: number }; quality: { memory: number; obstructed: number; uncertain: number } };
type Message = { role: "user" | "assistant"; content: string; cards?: AreaCard[]; widgets?: WidgetData; timestamp?: number };
function AssistantIcon({ size = 22 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 4.5h8a4.5 4.5 0 0 1 4.5 4.5v5a4.5 4.5 0 0 1-4.5 4.5h-5l-4 3v-3A4.5 4.5 0 0 1 3.5 14V9A4.5 4.5 0 0 1 8 4.5Z"/><path d="M8.5 10v3m3.5-5v7m3.5-5v3"/></svg>;
}

function Thinking() {
  return <div className="ai-thinking" role="status" aria-label="Thinking with your store data"><div className="ai-thinking-core" aria-hidden="true"><span className="ai-thinking-ring"/><div className="ai-thinking-wave"><i/><i/><i/><i/><i/></div></div><div className="ai-thinking-copy"><span>Thinking</span><small>With your store data</small></div></div>;
}

function MiniStats({ title, values }: { title: string; values: [string,number,string][] }) {
  return <div className="ai-mini-stats"><small>{title}</small><div>{values.map(([label,value,color]) => <span key={label}><b style={{ color }}>{value}</b><small>{label}</small></span>)}</div></div>;
}

function Answer({ text, cards, widgets, timestamp, store, onArea }: { text: string; cards?: AreaCard[]; widgets?: WidgetData; timestamp: number; store: Store; onArea: (camera: string, area: string) => void }) {
  const [showAll, setShowAll] = useState(false);
  const ids = [...new Set([...text.matchAll(/\[\[area:(\d{4}_\d+)\]\]|\b(\d{4}_\d+)\b/g)].map(m => m[1] ?? m[2]))];
  const known = new Map(store.cameras.flatMap(c => c.areas.map(a => [a.id, c.id] as const)));
  const available = cards ?? store.cameras.flatMap(c => {
    if (!c.frames.length) return [];
    const frame = frameAt(c, timestamp);
    return c.areas.filter(a => frame.areas[a.id]).map(a => ({ area: a.id, camera: c.id, product: a.product, product_id: a.productId, status: statusOf(frame.areas[a.id]), captured_at: frame.ts }));
  });
  const referenced = ids.map(id => available.find(a => a.area === id)).filter((a): a is AreaCard => !!a);
  const tokens = [...new Set([...text.matchAll(/\[\[(overview|changes|quality|camera:[A-Za-z0-9_-]+|product:[A-Za-z0-9_-]+)\]\]/g)].map(m => m[1]))];
  const statValues = (rows: AreaCard[]): [string,number,string][] => [
    ["Empty", rows.filter(a => a.status === "empty").length, STATUS.empty.color],
    ["Wrong", rows.filter(a => a.status === "wrong").length, STATUS.wrong.color],
    ["Low", rows.filter(a => a.status === "low").length, STATUS.low.color],
  ];
  const prose = text.replace(/\[\[(?:area:[^\]]+|overview|changes|quality|camera:[^\]]+|product:[^\]]+)\]\]/g, "").replace(/\[\[[^\]]*$/, "").trim();
  return <><div className="ai-answer">{prose.split(/(\*\*[^*]+\*\*|\b\d{4}_\d+\b)/g).map((part, i) => part.startsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : known.has(part) ? <button className="ai-area-link" key={i} onClick={() => onArea(known.get(part)!, part)}>{part} ↗</button> : part.split(/(\s+)/).map((word,j) => /^\s+$/.test(word) ? word : <span className="ai-word" key={j}>{word}</span>))}</div>
    {tokens.length > 0 && <div className="ai-summary-widgets">{tokens.slice(0,3).map(token => {
      if (token === "overview" && available.length) return <MiniStats key={token} title={`${available.length} areas · current snapshot`} values={statValues(available)}/>;
      if (token === "changes" && widgets) return <MiniStats key={token} title={widgets.changes.compared ? "Since earliest captures · predictions" : "No earlier images to compare"} values={[["Now full",widgets.changes.now_full,STATUS.ok.color],["New empty",widgets.changes.new_empty,STATUS.empty.color],["Compared",widgets.changes.compared,"var(--muted)"]]}/>;
      if (token === "quality" && widgets) return <MiniStats key={token} title="Worth verifying · confidence <65%, obstruction >25%" values={[["Low confidence",widgets.quality.uncertain,STATUS.low.color],["Obstructed",widgets.quality.obstructed,STATUS.wrong.color],["From memory",widgets.quality.memory,"var(--muted)"]]}/>;
      const [kind,id] = token.split(":");
      const rows = available.filter(a => kind === "camera" ? a.camera === id : a.product_id === id);
      if (!rows.length) return null;
      if (kind === "camera") return <button key={token} className="ai-camera-widget" onClick={() => onArea(id,rows[0].area)} aria-label={`Open camera ${id}`}><MiniStats title={`Cam ${id} · ${rows.length} areas · ${clock(rows[0].captured_at)} ↗`} values={statValues(rows)}/></button>;
      return <div key={token} className="ai-product-summary"><div><ProductImage name={rows[0].product}/><strong>{rows[0].product}</strong></div><MiniStats title={`${rows.length} areas · current snapshot`} values={statValues(rows)}/></div>;
    })}</div>}
    {referenced.length > 0 && <div className="ai-product-cards">{(showAll ? referenced : referenced.slice(0,3)).map(card => <button key={card.area} className="ai-product-card" onClick={() => onArea(card.camera,card.area)} aria-label={`Open ${card.product}, area ${card.area}`}><ProductImage name={card.product}/><span className="ai-product-info"><strong>{card.product}</strong><span><i style={{ background: STATUS[card.status].color }}/>{STATUS[card.status].action}</span><small>Cam {card.camera} · {card.area.split("_")[1]} · {clock(card.captured_at)}</small></span><span className="ai-card-arrow" aria-hidden="true">↗</span></button>)}{referenced.length > 3 && <button className="ai-more-cards" onClick={() => setShowAll(v => !v)}>{showAll ? "Show less" : `+${referenced.length - 3} more`}</button>}</div>}
  </>;
}

export function ShelfAssistant({ store, timestamp, camera, area, completed, onArea }: {
  store: Store; timestamp: number; camera: string; area: string | null; completed: Set<string>;
  onArea: (camera: string, area: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(false), [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [connection, setConnection] = useState<"checking" | "ready" | "missing" | "offline">("checking");
  const input = useRef<HTMLTextAreaElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const scroll = useRef<HTMLDivElement>(null), controller = useRef<AbortController | null>(null), working = useRef(false), conversation = useRef(0);
  const newChat = () => {
    conversation.current++;
    controller.current?.abort(); controller.current = null; working.current = false;
    setBusy(false); setMessages([]); setError(""); setDraft(""); input.current?.focus();
  };
  const close = () => { setExpanded(false); setOpen(false); trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => input.current?.focus(), 120);
    const abort = new AbortController();
    let retry: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const r = await fetch(`${store.base || apiBase()}/api/assistant`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(3500)]), cache: "no-store" });
        if (!r.ok) throw Error();
        const v = await r.json();
        if (typeof v.configured !== "boolean") throw Error();
        if (!abort.signal.aborted) setConnection(v.configured ? "ready" : "missing");
      } catch { if (!abort.signal.aborted) setConnection("offline"); }
      if (!abort.signal.aborted) retry = setTimeout(check, 5000);
    };
    check();
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); setExpanded(false); setOpen(false); trigger.current?.focus(); } };
    window.addEventListener("keydown", escape, true);
    return () => { clearTimeout(timer); clearTimeout(retry); abort.abort(); window.removeEventListener("keydown", escape, true); };
  }, [open, store.base]);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }, [messages, busy]);
  useEffect(() => () => controller.current?.abort(), []);

  async function send(text = draft) {
    const content = text.trim();
    if (!content || working.current || connection !== "ready") return;
    const generation = conversation.current;
    working.current = true; setBusy(true); setError(""); setDraft("");
    const history: Message[] = [...messages.filter(m => m.content.trim()).slice(-16), { role: "user", content }];
    setMessages([...history, { role: "assistant", content: "" }]);
    const abort = new AbortController(); controller.current = abort;
    let answer = "", done = false; let cards: AreaCard[] = []; let widgets: WidgetData | undefined;
    try {
      const response = await fetch(`${store.base || apiBase()}/api/assistant/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify({ messages: history, selection: { timestamp, camera, area, completedTasks: [...completed] } }) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw Error(typeof data.detail === "string" ? data.detail : "Could not connect. Please try again.");
      }
      if (!response.body) throw Error("No response received.");
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = "";
      const consume = (line: string) => {
        if (generation !== conversation.current) return;
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === "meta" && Array.isArray(event.cards)) cards = event.cards.filter((c: AreaCard) => typeof c.area === "string" && typeof c.camera === "string" && typeof c.product === "string" && c.status in STATUS && Number.isFinite(c.captured_at));
        if (event.type === "meta" && event.widgets?.changes && event.widgets?.quality) widgets = event.widgets;
        if (event.type === "error") throw Error(event.message);
        if (event.type === "done") done = true;
        if (event.type === "delta") { answer += event.text; setMessages([...history, { role: "assistant", content: answer, cards, widgets, timestamp }]); }
      };
      while (true) {
        const { value, done: end } = await reader.read();
        buffer += decoder.decode(value, { stream: !end });
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""; lines.forEach(consume);
        if (end) { consume(buffer); break; }
      }
      if (!done || !answer) throw Error("The reply was interrupted. Please try again.");
    } catch (e) {
      if (generation !== conversation.current) return;
      if (abort.signal.aborted) setError("Response stopped.");
      else setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally { if (generation === conversation.current) { working.current = false; setBusy(false); controller.current = null; input.current?.focus(); } }
  }

  return <>
    <button ref={trigger} className="nav-item ai-trigger" aria-label="Open ShelfOS AI" title="ShelfOS AI" aria-expanded={open} aria-controls="shelfos-ai" onClick={() => setOpen(v => !v)}><AssistantIcon size={19}/></button>
    {typeof document !== "undefined" && createPortal(<section id="shelfos-ai" role="dialog" aria-label="ShelfOS AI assistant" aria-hidden={!open} className="ai-widget" data-open={open} data-expanded={expanded} inert={!open}>
      <header className="ai-header"><div className="ai-avatar"><AssistantIcon/></div><div><b>ShelfOS <span>AI</span></b><p><i/> {connection === "ready" ? "Connected to your store" : connection === "checking" ? "Connecting…" : "Connection needed"}</p></div><div className="ai-header-actions"><button className="ai-icon-button" onClick={newChat} aria-label="New chat" title="New chat"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 4.5h8a4.5 4.5 0 0 1 4.5 4.5v5a4.5 4.5 0 0 1-4.5 4.5h-5l-4 3v-3A4.5 4.5 0 0 1 3.5 14V9A4.5 4.5 0 0 1 8 4.5Z"/><path d="M9 11.5h6m-3-3v6"/></svg></button><button className="ai-icon-button" onClick={() => setExpanded(v => !v)} aria-label={expanded ? "Restore compact chat" : "Expand chat"} aria-pressed={expanded} title={expanded ? "Restore" : "Expand"}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{expanded ? <path d="M9 3v6H3m12-6v6h6M9 21v-6H3m12 6v-6h6"/> : <path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>}</svg></button><button className="ai-icon-button" onClick={close} aria-label="Close assistant"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div></header>
      <div className="ai-context"><span className="ai-context-dot"/> {store.cameras.length} cameras <span>·</span> Snapshot {clock(timestamp)} </div>
      <div ref={scroll} className="ai-messages" aria-live="polite" aria-relevant="additions text">
        {!messages.length && <div className="ai-welcome"><div className="ai-welcome-orb"><AssistantIcon size={32}/></div><h2>A little clarity.<br/><span>For every shelf.</span></h2><p>Ask about stock, priorities or what changed through the day.</p><div className="ai-suggestions">{["What needs attention first?", "Which products are running low?", "What changed since this morning?"].map((q,i) => <button key={q} style={{ animationDelay: `${i * 45}ms` }} onClick={() => send(q)} disabled={connection !== "ready" || busy}>{q}<span>↗</span></button>)}</div></div>}
        {messages.map((m,i) => <div key={i} className={`ai-message ai-message-${m.role}`}><div className="ai-message-label">{m.role === "user" ? "You" : "ShelfOS AI"}</div>{m.content ? m.role === "user" ? <div className="ai-answer">{m.content}</div> : <Answer text={m.content} cards={m.cards} widgets={m.widgets} timestamp={m.timestamp ?? timestamp} store={store} onArea={(cam, id) => { close(); onArea(cam, id); }}/> : busy && i === messages.length - 1 ? <Thinking/> : <div className="ai-answer ai-empty-answer">No reply received.</div>}</div>)}
        {connection === "missing" && <p className="ai-notice">Connect your OpenRouter key in the server’s <code>.env</code> file to start chatting.</p>}
        {connection === "offline" && <p className="ai-notice">The ShelfOS server is unavailable. Start the backend to connect your assistant.</p>}
        {error && <p className="ai-notice" role="alert">{error}</p>}
      </div>
      <form className="ai-compose" onSubmit={e => { e.preventDefault(); send(); }}><div className="ai-input-wrap"><textarea ref={input} value={draft} onChange={e => setDraft(e.target.value)} maxLength={3000} rows={2} placeholder="Ask ShelfOS anything…" aria-label="Message ShelfOS AI" disabled={connection !== "ready"} onKeyDown={e => { if(e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}/>{busy ? <button type="button" className="ai-send" aria-label="Stop response" onClick={() => controller.current?.abort()}><span className="ai-stop"/></button> : <button className="ai-send" type="submit" aria-label="Send message" disabled={!draft.trim() || connection !== "ready"}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-5 5 5-5 5 5"/></svg></button>}</div><footer><span>Based on shelf predictions · verify before acting</span></footer></form>
    </section>, document.body)}
  </>;
}
