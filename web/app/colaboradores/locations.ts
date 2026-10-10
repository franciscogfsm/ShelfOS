import { STATUS, Task } from "../lib";

// Demo floor plan: camera IDs are real; physical positions await store mapping.
export const LOCATIONS: Record<string, { zone: string; bay: string; x: number; y: number }> = Object.fromEntries(
  ["6215", "6371", "6373", "6376", "6383", "6385", "6386", "6443", "6462", "6468", "6491", "6591", "6594", "6781"].map((id, i) => [id, {
    zone: i < 7 ? "A" : "B", bay: String(i % 7 + 1).padStart(2, "0"),
    x: i < 7 ? 78 : 242, y: 56 + (i % 7) * 31,
  }]),
);
export const locationOf = (id: string) => LOCATIONS[id];
export const ENTRY = { x: 160, y: 304 };

/** Urgency always wins; within a priority, visit the nearest demo bay next. */
export function walkingOrder(tasks: Task[], from = ENTRY): Task[] {
  const remaining = [...tasks];
  const ordered: Task[] = [];
  let position = from;
  while (remaining.length) {
    const rank = Math.min(...remaining.map(t => STATUS[t.status].rank));
    let best = -1, distance = Infinity;
    remaining.forEach((t, i) => {
      if (STATUS[t.status].rank !== rank) return;
      const p = locationOf(t.cam.id);
      const d = p ? Math.abs(p.x - position.x) + Math.abs(p.y - position.y) : Infinity;
      if (best < 0 || d < distance) { best = i; distance = d; }
    });
    const [next] = remaining.splice(best, 1);
    ordered.push(next);
    position = locationOf(next.cam.id) ?? position;
  }
  return ordered;
}
