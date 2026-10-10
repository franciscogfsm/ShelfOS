import { Store, Task, confidence, tasksAt, timeline } from "../lib";

/** A fresh, readable image must show full stock AND the correct product. */
export function cameraConfirmed(previous: Store, next: Store): Task[] {
  const current = new Map(tasksAt(next, timeline(next).latest).map(t => [t.area.id, t]));
  return tasksAt(previous, timeline(previous).latest).filter(t => {
    const updated = current.get(t.area.id);
    return t.status !== "ok" && updated?.status === "ok" && updated.frame.ts > t.frame.ts
      && updated.frame.file !== t.frame.file && updated.pred.source !== "memory"
      && (updated.pred.obstruction ?? 0) <= .25 && confidence(updated.pred) >= .65
      && updated.pred.pOk >= .65;
  });
}
