'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { testResendIntegration, testAdminTenantResendIntegration } from '@/lib/api/crm';

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
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 md:flex-row">
      <input
        required
        type="email"
        className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm"
        value={toEmail}
        onChange={(e) => setToEmail(e.target.value)}
        placeholder="destino@empresa.com"
      />
      <Button type="submit" disabled={disabled || sending} variant="outline" className="gap-2">
        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        Probar
      </Button>
    </form>
  );
}
