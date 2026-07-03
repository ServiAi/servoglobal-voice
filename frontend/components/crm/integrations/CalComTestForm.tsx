'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { testAdminTenantCalComIntegration, testCalComIntegration } from '@/lib/api/crm';

type Props = {
  accessToken: string;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  disabled?: boolean;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
};

export function CalComTestForm({ accessToken, mode = 'tenant', tenantId, disabled, onSuccess, onError }: Props) {
  const [loading, setLoading] = useState(false);

  const test = async () => {
    setLoading(true);
    const result =
      mode === 'admin' && tenantId
        ? await testAdminTenantCalComIntegration(accessToken, tenantId)
        : await testCalComIntegration(accessToken);
    setLoading(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    if (result.data.status !== 'active') {
      onError(result.data.error_message ?? 'No se pudo verificar Cal.com.');
      return;
    }
    onSuccess('Conexion Cal.com verificada.');
  };

  return (
    <Button type="button" variant="outline" disabled={disabled || loading} onClick={test}>
      {loading ? 'Probando...' : 'Probar Cal.com'}
    </Button>
  );
}
