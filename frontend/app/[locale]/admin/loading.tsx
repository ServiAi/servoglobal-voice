import { CircularLoadingState } from '@/components/ui/circular-loader';

export default function AdminGlobalLoading() {
  return <CircularLoadingState message="Cargando panel de administración…" minHeight="min-h-[65vh]" />;
}
