export default function AdminTenantIntegrationsLoading() {
  return (
    <div className="mx-auto max-w-7xl space-y-7" aria-busy="true" aria-label="Cargando integraciones">
      <div className="h-8 w-36 animate-pulse rounded bg-muted" />
      <div className="h-24 animate-pulse rounded-xl bg-muted" />
      <div className="h-48 animate-pulse rounded-xl bg-muted" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="h-64 animate-pulse rounded-xl bg-muted" />)}</div>
    </div>
  );
}
