'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { configureAdminTenantWhatsAppIntegration, configureWhatsAppIntegration } from '@/lib/api/crm';
import type { WhatsAppConfigResponse } from '@/types/crm';

type Props = {
  accessToken: string;
  config?: WhatsAppConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: WhatsAppConfigResponse) => void;
  onError: (message: string) => void;
};

export function WhatsAppConfigForm({ accessToken, config, mode = 'tenant', tenantId, onSaved, onError }: Props) {
  const [phoneNumberId, setPhoneNumberId] = useState(config?.phone_number_id ?? '');
  const [businessAccountId, setBusinessAccountId] = useState(config?.business_account_id ?? '');
  const [displayPhoneNumber, setDisplayPhoneNumber] = useState(config?.display_phone_number ?? '');
  const [defaultLanguage, setDefaultLanguage] = useState(config?.default_language ?? 'es');
  const [accessTokenValue, setAccessTokenValue] = useState('');
  const [webhookToken, setWebhookToken] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    const payload = {
      phone_number_id: phoneNumberId,
      business_account_id: businessAccountId || null,
      display_phone_number: displayPhoneNumber || null,
      default_language: defaultLanguage || 'es',
      status: 'active',
      access_token: accessTokenValue || null,
      webhook_verify_token: webhookToken || null,
    };
    const result = mode === 'admin' && tenantId
      ? await configureAdminTenantWhatsAppIntegration(accessToken, tenantId, payload)
      : await configureWhatsAppIntegration(accessToken, payload);
    setSaving(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setAccessTokenValue('');
    setWebhookToken('');
    onSaved(result.data);
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Phone number ID</span>
        <input required className="rounded-md border border-border bg-background px-3 py-2" value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Business account ID</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={businessAccountId} onChange={(e) => setBusinessAccountId(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Telefono visible</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={displayPhoneNumber} onChange={(e) => setDisplayPhoneNumber(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Idioma</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={defaultLanguage} onChange={(e) => setDefaultLanguage(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="font-medium text-muted-foreground">Access token</span>
        <input type="password" className="rounded-md border border-border bg-background px-3 py-2" value={accessTokenValue} onChange={(e) => setAccessTokenValue(e.target.value)} placeholder={config?.has_secret ? 'Conservar token existente' : 'Meta access token'} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="font-medium text-muted-foreground">Webhook verify token</span>
        <input type="password" className="rounded-md border border-border bg-background px-3 py-2" value={webhookToken} onChange={(e) => setWebhookToken(e.target.value)} placeholder={config?.has_webhook_secret ? 'Conservar token existente' : 'Token de verificacion'} />
      </label>
      <div className="flex items-center justify-between gap-3 md:col-span-2">
        <span className="text-xs text-muted-foreground">Access token configurado: {config?.has_secret ? 'Si' : 'No'}</span>
        <Button type="submit" disabled={saving} className="gap-2">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar
        </Button>
      </div>
    </form>
  );
}
