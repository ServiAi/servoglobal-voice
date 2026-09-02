'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { configureChatwootIntegration } from '@/lib/api/crm';
import type { ChatwootConfigResponse } from '@/types/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  config?: ChatwootConfigResponse;
  onSaved: (config: ChatwootConfigResponse) => void;
  onError: (message: string) => void;
};

const FIELD_CLASS = 'min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

export function ChatwootConfigForm({ accessToken, config, onSaved, onError }: Props) {
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? 'https://crm.serviglobal-ia.com');
  const [accountId, setAccountId] = useState(config?.account_id ? String(config.account_id) : '');
  const [defaultInboxId, setDefaultInboxId] = useState(config?.default_inbox_id ? String(config.default_inbox_id) : '');
  const [apiToken, setApiToken] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      base_url: baseUrl,
      account_id: Number(accountId),
      default_inbox_id: defaultInboxId ? Number(defaultInboxId) : null,
      status: 'active',
      api_token: apiToken || null,
    };

    const result = await configureChatwootIntegration(accessToken, payload);

    setSaving(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setApiToken('');
    onSaved(result.data);
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-5 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">URL de Chatwoot <FieldHelp label="URL de Chatwoot" required>La instalación de Chatwoot que atiende a este tenant. Usa la de ServiGlobal salvo que traigas tu propia instancia.</FieldHelp></span>
        <input required className={FIELD_CLASS} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://crm.serviglobal-ia.com" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Account ID <FieldHelp label="Account ID" required>El ID de tu Account en Chatwoot (Settings → General, aparece también en la URL /accounts/&#123;id&#125;/).</FieldHelp></span>
        <input required type="number" min={1} className={FIELD_CLASS} value={accountId} onChange={(e) => setAccountId(e.target.value)} placeholder="17" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Inbox por defecto <FieldHelp label="Inbox por defecto" required={false}>ID del inbox que se usará al crear conversaciones nuevas (Settings → Inboxes → tu inbox → ID en la URL).</FieldHelp></span>
        <input type="number" min={1} className={FIELD_CLASS} value={defaultInboxId} onChange={(e) => setDefaultInboxId(e.target.value)} placeholder="35" />
      </label>
      <label className="flex flex-col gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Access token <FieldHelp label="Access token" required={!config?.has_secret}>Perfil → Access Token dentro de Chatwoot. Solo es obligatorio al configurar por primera vez; luego puede dejarse vacío para conservarlo.</FieldHelp></span>
        <input type="password" className={FIELD_CLASS} value={apiToken} onChange={(e) => setApiToken(e.target.value)} placeholder={config?.has_secret ? 'Conservar access token existente' : 'access token'} />
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
