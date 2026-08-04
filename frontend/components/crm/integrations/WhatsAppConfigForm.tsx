'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { configureAdminTenantWhatsAppIntegration, configureWhatsAppIntegration } from '@/lib/api/crm';
import type { WhatsAppConfigResponse } from '@/types/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  config?: WhatsAppConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: WhatsAppConfigResponse) => void;
  onError: (message: string) => void;
};

const FIELD_CLASS = 'min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

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
    <form onSubmit={handleSubmit} className="grid gap-5 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Phone number ID <FieldHelp label="Phone number ID" required>En Meta Business Manager abre WhatsApp Manager → Configuración de la API y copia Phone number ID.</FieldHelp></span>
        <input required className={FIELD_CLASS} value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Business account ID (WABA ID) <FieldHelp label="Business account ID (WABA ID)" required>En WhatsApp Manager → Configuración → Cuenta, copia el ID de la cuenta de WhatsApp Business. No uses el Business Portfolio ID.</FieldHelp></span>
        <input className={FIELD_CLASS} value={businessAccountId} onChange={(e) => setBusinessAccountId(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Teléfono visible <FieldHelp label="Teléfono visible" required={false}>Es el número asociado al Phone number ID, en formato internacional. Solo se usa como referencia visual.</FieldHelp></span>
        <input className={FIELD_CLASS} value={displayPhoneNumber} onChange={(e) => setDisplayPhoneNumber(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Idioma <FieldHelp label="Idioma" required>Usa el código de idioma de tus plantillas de Meta, por ejemplo es, es_CO o en_US.</FieldHelp></span>
        <input className={FIELD_CLASS} value={defaultLanguage} onChange={(e) => setDefaultLanguage(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Access token <FieldHelp label="Access token" required={!config?.has_secret}>Genera un token permanente para un usuario del sistema en Meta Business Settings con permisos de WhatsApp. Solo es obligatorio la primera vez.</FieldHelp></span>
        <input type="password" className={FIELD_CLASS} value={accessTokenValue} onChange={(e) => setAccessTokenValue(e.target.value)} placeholder={config?.has_secret ? 'Conservar token existente' : 'Meta access token'} />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Webhook verify token <FieldHelp label="Webhook verify token" required={false}>Créalo tú como una cadena secreta y usa exactamente el mismo valor al configurar el webhook en Meta.</FieldHelp></span>
        <input type="password" className={FIELD_CLASS} value={webhookToken} onChange={(e) => setWebhookToken(e.target.value)} placeholder={config?.has_webhook_secret ? 'Conservar token existente' : 'Token de verificación'} />
      </label>
      <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between md:col-span-2">
        <span className="text-xs font-medium text-muted-foreground">Access token configurado: {config?.has_secret ? 'Sí' : 'No'}</span>
        <Button type="submit" disabled={saving} className="gap-2">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar
        </Button>
      </div>
    </form>
  );
}
