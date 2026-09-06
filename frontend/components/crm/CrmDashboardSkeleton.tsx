import { CircularLoader } from '@/components/ui/circular-loader';

const PULSE = 'animate-pulse rounded-xl bg-muted/60 motion-reduce:animate-none';

export function CrmDashboardSkeleton({ message = 'Cargando información…' }: { message?: string }) {
  return (
    <div className="relative space-y-6" aria-busy="true" aria-label={message}>
      {/* Centered Glowing Circular Loader */}
      <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-background/80 p-6 shadow-2xl backdrop-blur-md dark:border-white/5 dark:bg-zinc-950/80">
          <CircularLoader size="xl" glow={true} label={message} />
          <p className="mt-4 text-sm font-medium text-foreground/90">{message}</p>
        </div>
      </div>

      <div className="space-y-2 opacity-50">
        <div className={`${PULSE} h-8 w-56`} />
        <div className={`${PULSE} h-4 w-80 max-w-full`} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 opacity-50">
        {[1, 2, 3, 4].map((item) => <div key={item} className={`${PULSE} h-32`} />)}
      </div>
      <div className="grid gap-6 lg:grid-cols-2 opacity-50">
        <div className={`${PULSE} h-80`} />
        <div className={`${PULSE} h-80`} />
      </div>
    </div>
  );
}
