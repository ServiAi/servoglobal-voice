import { CircularLoadingState } from '@/components/ui/circular-loader';

export default function LeadWorkspaceLoading() {
  return (
    <CircularLoadingState
      message="Cargando información del lead…"
      description="Recuperando historial, notas, tareas y datos de contacto"
      minHeight="min-h-[50vh]"
    />
  );
}
