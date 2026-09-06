import { CircularLoadingState } from '@/components/ui/circular-loader';

export default function TenantGlobalLoading() {
  return <CircularLoadingState message="Cargando panel…" minHeight="min-h-[65vh]" />;
}
