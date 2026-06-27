'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { configureResendIntegration, configureAdminTenantResendIntegration } from '@/lib/api/crm';
import type { ResendIntegrationConfigResponse } from '@/types/crm';

type Props = {
  accessToken: string;
  config?: ResendIntegrationConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: ResendIntegrationConfigResponse) => void;
  onError: (message: string) => void;
};

export function ResendConfigForm({ accessToken, config, mode = 'tenant', tenantId, onSaved, onError }: Props) {
  const [senderName, setSenderName] = useState(config?.sender_name ?? 'ServiGlobal IA');
  const [senderEmail, setSenderEmail] = useState(config?.sender_email ?? '');
  const [replyTo, setReplyTo] = useState(config?.reply_to ?? '');
  const [defaultDomain, setDefaultDomain] = useState(config?.default_domain ?? '');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      sender_name: senderName,
      sender_email: senderEmail,
      reply_to: replyTo || null,
      default_domain: defaultDomain || null,
      resend_api_key: apiKey || null,
    };

    const result = mode === 'admin' && tenantId
      ? await configureAdminTenantResendIntegration(accessToken, tenantId, payload)
      : await configureResendIntegration(accessToken, payload);

    setSaving(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setApiKey('');
    onSaved(result.data);
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Nombre remitente</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={senderName} onChange={(e) => setSenderName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Email remitente</span>
        <input required type="email" className="rounded-md border border-border bg-background px-3 py-2" value={senderEmail} onChange={(e) => setSenderEmail(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Reply-To</span>
        <input type="email" className="rounded-md border border-border bg-background px-3 py-2" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Dominio</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={defaultDomain} onChange={(e) => setDefaultDomain(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="font-medium text-muted-foreground">Resend API key</span>
        <input type="password" className="rounded-md border border-border bg-background px-3 py-2" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={config?.has_secret ? 'Conservar API key existente' : 're_...'} />
      </label>
      <div className="flex items-center justify-between gap-3 md:col-span-2">
        <span className="text-xs text-muted-foreground">API key configurada: {config?.has_secret ? 'Si' : 'No'}</span>
        <Button type="submit" disabled={saving} className="gap-2">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar
        </Button>
      </div>
    </form>
  );
}
