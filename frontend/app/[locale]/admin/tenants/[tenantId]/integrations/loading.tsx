import { CircularLoadingState } from '@/components/ui/circular-loader';

export default function AdminTenantIntegrationsLoading() {
  return (
    <CircularLoadingState
      message="Cargando integraciones del tenant…"
      description="Obteniendo estado y configuración de servicios conectados"
      minHeight="min-h-[50vh]"
    />
  );
}
