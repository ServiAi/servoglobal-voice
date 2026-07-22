const PULSE = 'animate-pulse rounded-xl bg-muted motion-reduce:animate-none';

export function CrmDashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando información CRM">
      <div className="space-y-2">
        <div className={`${PULSE} h-8 w-56`} />
        <div className={`${PULSE} h-4 w-80 max-w-full`} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((item) => <div key={item} className={`${PULSE} h-32`} />)}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className={`${PULSE} h-80`} />
        <div className={`${PULSE} h-80`} />
      </div>
    </div>
  );
}
