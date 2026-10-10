const Sk = ({ w, h, r, className = "" }: { w?: number | string; h?: number | string; r?: number; className?: string }) => (
  <span className={`sk ${className}`} style={{ width: w, height: h, borderRadius: r }} />
);
const list = (n: number) => Array.from({ length: n }, (_, i) => i);

/** The app before its data arrives: every block sits where the real one will be. */
export default function Loading() {
  return (
    <div className="app-shell h-full grid grid-rows-[auto_auto_1fr] overflow-hidden" role="status" aria-label="Loading shelf state" aria-busy="true">
      <header className="app-header flex flex-wrap items-center gap-x-6 gap-y-3 px-4 lg:px-6 py-3 lg:py-0 lg:h-[76px]">
        <div className="flex min-w-0 items-center gap-3 lg:flex-1">
          <Sk w={20} h={20} r={10} />
          <div className="grid gap-2"><Sk w={190} h={12} /><Sk w={120} h={9} /></div>
        </div>
        <nav className="main-nav glass order-last lg:order-none flex w-full lg:w-auto" aria-hidden="true">
          {[92, 118, 104, 128].map((w) => <span key={w} className="nav-item flex-1 lg:flex-none"><Sk w={w - 36} h={10} /></span>)}
        </nav>
        <div className="flex lg:flex-1 items-center justify-end gap-2.5">
          <Sk h={40} r={999} className="w-10 md:w-[150px]" />
          <Sk w={236} h={42} r={999} className="max-md:hidden" />
        </div>
      </header>

      <div className="timeline-bar flex items-center gap-3 lg:gap-4 px-4 lg:px-6 py-3">
        <Sk w={36} h={36} r={999} />
        <div className="grid gap-2 w-[76px] lg:w-[92px] shrink-0"><Sk w="100%" h={22} /><Sk w={48} h={8} /></div>
        <Sk h={52} r={10} className="flex-1" />
        <Sk w={112} h={34} r={999} className="max-sm:hidden" />
      </div>

      <div className="grid min-h-0 lg:grid-cols-[minmax(0,1fr)_384px]">
        <main className="workspace min-h-0 min-w-0 overflow-hidden p-4 lg:p-7">
          {/* wide screens open on the store wall */}
          <div className="max-lg:hidden flex flex-col gap-5">
            <section className="overview-heading">
              <div className="grid gap-3"><Sk w={70} h={8} /><Sk w={340} h={44} r={12} /><Sk w={180} h={12} /></div>
              <Sk w={172} h={36} r={999} />
            </section>
            <div className="metrics-grid grid grid-cols-2 xl:grid-cols-4 gap-3">
              {list(4).map((i) => (
                <div key={i} className="metric-card glass-card">
                  <div className="flex items-start justify-between gap-3">
                    <div><Sk w={96} h={9} /><Sk w={112} h={44} r={12} className="mt-3.5 mb-2.5" /><Sk w={150} h={10} /></div>
                    <Sk w={46} h={46} r={999} />
                  </div>
                  <div className="metric-spark"><Sk w="100%" h="100%" r={0} className="sk-fade" /></div>
                </div>
              ))}
            </div>
            <div className="section-heading"><div className="grid gap-2"><Sk w={120} h={8} /><Sk w={150} h={22} /></div><Sk w={170} h={10} /></div>
            <div className="camera-grid grid sm:grid-cols-2 2xl:grid-cols-3 gap-4">
              {list(6).map((i) => (
                <div key={i}>
                  <div className="camera-caption"><Sk w={112} h={13} /><Sk w={64} h={10} /></div>
                  <Sk w="100%" h="auto" r={18} className="aspect-video" />
                  <div className="camera-footer"><Sk w={150} h={10} /><Sk w={72} h={10} /></div>
                </div>
              ))}
            </div>
          </div>
          {/* a phone opens on the tasks */}
          <div className="lg:hidden tasks-page flex flex-col gap-5">
            <section className="overview-heading">
              <div className="grid gap-3"><Sk w={96} h={8} /><Sk w={200} h={36} r={12} /><Sk w={230} h={12} /></div>
              <div className="shift-progress glass-card grid gap-3"><div className="flex justify-between"><Sk w={96} h={10} /><Sk w={44} h={10} /></div><Sk w="100%" h={4} /></div>
            </section>
            <div className="filter-row">{[70, 128, 132, 124].map((w) => <Sk key={w} w={w} h={38} r={999} />)}</div>
            <Sk w={130} h={10} />
            <div className="task-grid">
              {list(6).map((i) => (
                <div key={i} className="task-card glass-card">
                  <Sk w={68} h={68} r={16} />
                  <div className="grid gap-2 flex-1"><Sk w="70%" h={14} /><Sk w="55%" h={10} /><Sk w="40%" h={9} /></div>
                  <Sk w={46} h={46} r={999} />
                </div>
              ))}
            </div>
          </div>
        </main>

        <aside className="task-panel glass-card hidden lg:flex min-h-0 flex-col">
          <div className="px-5 pb-4 grid gap-3"><Sk w={150} h={8} /><Sk w={210} h={24} /><div className="flex gap-5 pt-1"><Sk w={40} h={11} /><Sk w={110} h={11} /></div></div>
          <div className="queue-head flex justify-between px-5"><Sk w={110} h={10} /><Sk w={56} h={10} /></div>
          {list(8).map((i) => (
            <div key={i} className="task-row flex items-center gap-3">
              <Sk w={48} h={48} r={12} />
              <div className="grid gap-1.5 flex-1"><Sk w="62%" h={13} /><Sk w="78%" h={9} /><Sk w="50%" h={8} /></div>
              <Sk w={32} h={32} r={999} />
            </div>
          ))}
        </aside>
      </div>
      <span className="sr-only">Preparing your shelf overview…</span>
    </div>
  );
}
