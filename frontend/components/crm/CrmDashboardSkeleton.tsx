import { CircularLoader } from '@/components/ui/circular-loader';

export function CrmDashboardSkeleton({ message = 'Cargando información…' }: { message?: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={message}
      className="flex min-h-[60vh] w-full items-center justify-center"
    >
      <CircularLoader size="2xl" glow={true} />
      <span className="sr-only">{message}</span>
    </div>
  );
}
