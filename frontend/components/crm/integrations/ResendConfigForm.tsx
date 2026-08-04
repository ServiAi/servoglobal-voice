'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { configureResendIntegration, configureAdminTenantResendIntegration } from '@/lib/api/crm';
import type { ResendIntegrationConfigResponse } from '@/types/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  config?: ResendIntegrationConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: ResendIntegrationConfigResponse) => void;
  onError: (message: string) => void;
};

const FIELD_CLASS = 'min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

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
    <form onSubmit={handleSubmit} className="grid gap-5 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Nombre remitente <FieldHelp label="Nombre remitente" required={false}>Es el nombre comercial que verán los destinatarios junto al correo.</FieldHelp></span>
        <input className={FIELD_CLASS} value={senderName} onChange={(e) => setSenderName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Email remitente <FieldHelp label="Email remitente" required>Créalo y verifícalo dentro de Domains en Resend; debe pertenecer a un dominio verificado.</FieldHelp></span>
        <input required type="email" className={FIELD_CLASS} value={senderEmail} onChange={(e) => setSenderEmail(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Reply-To <FieldHelp label="Reply-To" required={false}>Indica el correo que recibirá las respuestas. Si se omite, se usa el email remitente.</FieldHelp></span>
        <input type="email" className={FIELD_CLASS} value={replyTo} onChange={(e) => setReplyTo(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Dominio <FieldHelp label="Dominio" required={false}>Cópialo desde Resend → Domains después de completar la verificación DNS.</FieldHelp></span>
        <input className={FIELD_CLASS} value={defaultDomain} onChange={(e) => setDefaultDomain(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Resend API key <FieldHelp label="Resend API key" required={!config?.has_secret}>Créala en Resend → API Keys. Solo es obligatoria al configurar por primera vez; luego puede dejarse vacía para conservarla.</FieldHelp></span>
        <input type="password" className={FIELD_CLASS} value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={config?.has_secret ? 'Conservar API key existente' : 're_...'} />
      </label>
      <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between md:col-span-2">
        <span className="text-xs font-medium text-muted-foreground">API key configurada: {config?.has_secret ? 'Sí' : 'No'}</span>
        <Button type="submit" disabled={saving} className="gap-2">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar
        </Button>
      </div>
    </form>
  );
}
