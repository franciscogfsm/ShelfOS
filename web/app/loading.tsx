export default function Loading() {
  return (
    <div className="loading-shell app-shell h-full" role="status" aria-label="Loading shelf state" aria-busy="true">
      <div className="loading-header"><div className="loading-brand">Shelf<span>OS</span></div><div className="skeleton loading-nav" /></div>
      <div className="loading-timeline skeleton" />
      <div className="loading-body">
        <div className="loading-main">
          <div className="skeleton loading-eyebrow" /><div className="skeleton loading-title" /><div className="skeleton loading-subtitle" />
          <div className="loading-metrics">{[0, 1, 2, 3].map((n) => <div key={n} className="skeleton loading-metric" />)}</div>
          <div className="loading-cameras">{[0, 1, 2, 3].map((n) => <div key={n} className="skeleton loading-camera" />)}</div>
        </div>
        <div className="loading-queue"><div className="skeleton loading-title" />{[0, 1, 2, 3, 4].map((n) => <div key={n} className="skeleton loading-task" />)}</div>
      </div>
      <span className="sr-only">Preparing your shelf overview…</span>
    </div>
  );
}
