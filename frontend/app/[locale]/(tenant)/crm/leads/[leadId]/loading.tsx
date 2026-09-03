export default function LeadWorkspaceLoading() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Cargando lead">
      <div className="h-10 w-32 animate-pulse rounded-md bg-muted" />
      <div className="space-y-5 rounded-xl border border-border bg-card p-6">
        <div className="h-7 w-64 max-w-full animate-pulse rounded bg-muted" />
        <div className="h-4 w-40 animate-pulse rounded bg-muted" />
        <div className="h-20 animate-pulse rounded-lg bg-muted" />
      </div>
      <div className="flex gap-2 overflow-hidden border-b border-border pb-2">
        {[1, 2, 3, 4, 5].map((item) => <div key={item} className="h-10 w-28 shrink-0 animate-pulse rounded bg-muted" />)}
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="h-72 animate-pulse rounded-xl bg-muted lg:col-span-2" />
        <div className="h-72 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}
