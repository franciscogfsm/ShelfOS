import { useState } from "react";
import { STATUS, Task } from "../lib";
import { ENTRY, LOCATIONS, locationOf } from "./locations";

// A few SVG faces give depth without WebGL, textures or an extra dependency.
const project = (x: number, y: number, z = 0) => [260 + (x - 400) * .40 + (y - 325) * .26, 180 + (y - 325) * .24 - (x - 400) * .14 - z];
const point = (x: number, y: number, z = 0) => project(x, y, z).join(",");
function Fixture({ x, y, w, d, selected = false, label, color }: { x: number; y: number; w: number; d: number; selected?: boolean; label?: string; color?: string }) {
  const labelAt = project(x + w / 2, y + d / 2, 12);
  return <g className={`iso-fixture ${selected ? "is-destination" : ""}`}>
    <polygon className="iso-side" points={[point(x,y+d), point(x+w,y+d), point(x+w,y+d,12), point(x,y+d,12)].join(" ")} />
    <polygon className="iso-end" points={[point(x+w,y), point(x+w,y+d), point(x+w,y+d,12), point(x+w,y,12)].join(" ")} />
    <polygon className="iso-top" points={[point(x,y,12),point(x+w,y,12),point(x+w,y+d,12),point(x,y+d,12)].join(" ")} />
    {label && <text x={labelAt[0]} y={labelAt[1]+2} textAnchor="middle" className="iso-bay-label">{label}</text>}
    {color && <circle cx={labelAt[0]+19} cy={labelAt[1]-3} r="2.5" fill={color} />}
  </g>;
}

export function StoreMap({ task, from, tasks }: { task?: Task; from: typeof ENTRY; tasks: Task[] }) {
  const [focused, setFocused] = useState(false);
  const target = task && locationOf(task.cam.id);
  const atEntry = from.x === ENTRY.x && from.y === ENTRY.y;
  const worldFrom = atEntry ? { x: 400, y: 620 } : { x: from.x + 40, y: from.y + 240 };
  const start = project(worldFrom.x, worldFrom.y);
  const end = target && project(target.x+40, target.y+240, 14);
  const route = target ? atEntry
    ? [project(400,620),project(400,560),project(200,560),project(200,target.y+240),project(target.x < 160 ? target.x+74 : target.x+6,target.y+240)]
    : [start,project(200,worldFrom.y),project(200,target.y+240),project(target.x < 160 ? target.x+74 : target.x+6,target.y+240)] : [];
  const departments = [
    { x:40,y:30,w:150,d:50,name:"PADARIA" }, { x:245,y:30,w:215,d:50,name:"TALHO · PEIXARIA" },
    { x:515,y:30,w:245,d:50,name:"LACTICÍNIOS" },
  ];
  return <><div className="staff-map-zoom filter-row" aria-label="Escala do mapa"><button aria-pressed={!focused} onClick={()=>setFocused(false)}>Loja inteira</button><button aria-pressed={focused} onClick={()=>setFocused(true)}>Ver destino</button></div>
  <svg className={`staff-isometric ${focused ? "is-focused" : ""}`} viewBox={focused ? "92 152 230 178" : "0 0 520 370"} role="img" aria-label={target ? `Mapa isométrico de um supermercado grande: percurso até à zona ${target.zone}, módulo ${target.bay}` : "Mapa de demonstração do supermercado"}>
    <defs><filter id="staff-map-shadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="9" stdDeviation="8" floodOpacity=".13" /></filter></defs>
    <g filter="url(#staff-map-shadow)"><polygon className="iso-floor-edge" points={[point(0,650),point(800,650),point(800,650,-9),point(0,650,-9)].join(" ")} /><polygon className="iso-floor" points={[point(0,0),point(800,0),point(800,650),point(0,650)].join(" ")} /></g>
    {[140,240,550].map(y=><path key={y} className="iso-floor-line" d={`M${point(0,y)} L${point(800,y)}`} />)}
    <polygon className="iso-section" points={[point(70,268),point(325,268),point(325,520),point(70,520)].join(" ")} />
    {departments.map(d => { const pos=project(d.x+d.w/2,d.y+20,17);return <g key={d.name}><Fixture x={d.x} y={d.y} w={d.w} d={d.d} /><text x={pos[0]} y={pos[1]} textAnchor="middle" className="iso-department">{d.name}</text></g>; })}
    {[370,470,570,670].map((x,i)=><g key={x}>{[155,245,335,425].map(y=><Fixture key={y} x={x} y={y} w={48} d={65} />)}<text x={project(x+24,122)[0]} y={project(x+24,122)[1]} textAnchor="middle" className="iso-context-label">{["MERCEARIA","BEBIDAS","HIGIENE","CONGELADOS"][i]}</text></g>)}
    {[135,180,225].map(y=><Fixture key={y} x={90} y={y} w={175} d={27} />)}
    <text x={project(165,110)[0]} y={project(165,110)[1]} textAnchor="middle" className="iso-context-label">PROMOÇÕES</text>
    <text x={project(200,252)[0]} y={project(200,252)[1]} textAnchor="middle" className="iso-department">FRUTAS & LEGUMES</text>
    {target && <polyline className="iso-route-under" points={route.map(p=>p.join(",")).join(" ")} />}
    {target && <polyline className="floor-route iso-route" points={route.map(p=>p.join(",")).join(" ")} />}
    {Object.entries(LOCATIONS).sort(([,a],[,b]) => project(a.x,a.y)[1]-project(b.x,b.y)[1]).map(([id,p]) => {
      const first = tasks.find(t=>t.cam.id===id);
      return <Fixture key={id} x={p.x+9} y={p.y+230} w={62} d={21} label={`${p.zone}${p.bay}`} selected={task?.cam.id===id} color={first && STATUS[first.status].color} />;
    })}
    {[90,165,240,500,575,650,725].map(x=><g key={x}><Fixture x={x} y={585} w={42} d={22} /><Fixture x={x+5} y={615} w={12} d={10} /></g>)}
    <text x={project(585,565)[0]} y={project(585,565)[1]} textAnchor="middle" className="iso-context-label">CAIXAS</text>
    <circle cx={start[0]} cy={start[1]} r="9" className="floor-you-halo" /><circle cx={start[0]} cy={start[1]} r="4" className="floor-you" />
    {end && <><path className="iso-pin-stem" d={`M${end[0]},${end[1]-5} v-15`} /><circle cx={end[0]} cy={end[1]-22} r="12" className="iso-pin" /><text x={end[0]} y={end[1]-18} textAnchor="middle" className="iso-pin-label">{target?.zone}{target?.bay}</text></>}
    <text x={project(400,650)[0]} y={project(400,650)[1]+20} textAnchor="middle" className="iso-context-label">ENTRADA</text>
  </svg></>;
}
