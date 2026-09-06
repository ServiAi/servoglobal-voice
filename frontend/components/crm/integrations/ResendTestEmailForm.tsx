'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Send } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { Button } from '@/components/ui/button';
import { testResendIntegration, testAdminTenantResendIntegration } from '@/lib/api/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  disabled?: boolean;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
};

export function ResendTestEmailForm({ accessToken, disabled, mode = 'tenant', tenantId, onSuccess, onError }: Props) {
  const [toEmail, setToEmail] = useState('');
  const [sending, setSending] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSending(true);

    const result = mode === 'admin' && tenantId
      ? await testAdminTenantResendIntegration(accessToken, tenantId, { to_email: toEmail })
      : await testResendIntegration(accessToken, { to_email: toEmail });

    setSending(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    onSuccess('Correo de prueba enviado correctamente.');
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 md:flex-row md:items-end">
      <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 text-muted-foreground">Correo de prueba <FieldHelp label="Correo de prueba" required>Escribe una dirección a la que tengas acceso para comprobar la entrega.</FieldHelp></span>
        <input
          required
          type="email"
          className="min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
          value={toEmail}
          onChange={(e) => setToEmail(e.target.value)}
          placeholder="destino@empresa.com"
        />
      </label>
      <Button type="submit" disabled={disabled || sending} variant="outline" className="gap-2">
        {sending ? <CircularLoader size="xs" glow={false} /> : <Send className="h-4 w-4" />}
        Probar
      </Button>
    </form>
  );
}
