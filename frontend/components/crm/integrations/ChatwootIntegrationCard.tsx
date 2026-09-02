'use client';

import { useState } from 'react';
import { AlertCircle, Copy, Eye, EyeOff, Loader2, MessageCircle, Send, Settings2, Sparkles, Unplug } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  disconnectAdminTenantChatwoot,
  disconnectChatwootIntegration,
  provisionAdminTenantChatwoot,
  provisionChatwootIntegration,
  testAdminTenantChatwoot,
  testChatwootIntegration,
} from '@/lib/api/crm';
import type { ChatwootConfigResponse } from '@/types/crm';
import { ChatwootConfigForm } from './ChatwootConfigForm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  initialConfig?: ChatwootConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

type ProvisionMethod = 'managed' | 'external';

const METHOD_CARD_CLASS = 'flex flex-1 cursor-pointer flex-col gap-1 rounded-lg border p-4 text-sm transition has-[:checked]:border-primary has-[:checked]:bg-primary/5';

export function ChatwootIntegrationCard({ accessToken, initialConfig, mode = 'tenant', tenantId }: Props) {
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showWebhookUrl, setShowWebhookUrl] = useState(false);
  const [testing, setTesting] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [method, setMethod] = useState<ProvisionMethod>(config?.mode === 'external' ? 'external' : 'managed');

  const isActive = config?.status === 'active';
  const isError = config?.status === 'error';
  const hasExistingConfig = Boolean(config?.account_id);
  const isManagedReconnect = method === 'managed' && config?.mode === 'managed' && hasExistingConfig;

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
  const fullWebhookUrl = config?.webhook_url ? `${apiBaseUrl}${config.webhook_url}` : null;
  const displayUrl = config?.base_url?.replace(/^https?:\/\//, '') ?? null;

  const handleTest = async () => {
    setTesting(true);
    const result = mode === 'admin' && tenantId
      ? await testAdminTenantChatwoot(accessToken, tenantId)
      : await testChatwootIntegration(accessToken);
    setTesting(false);
    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    if (result.data.status !== 'success') {
      notify('error', result.data.error_message ?? 'La prueba de conexión con Chatwoot falló.');
      return;
    }
    notify('success', 'Conexión con Chatwoot verificada correctamente.');
  };

  const handleProvision = async () => {
    setProvisioning(true);
    const result = mode === 'admin' && tenantId
      ? await provisionAdminTenantChatwoot(accessToken, tenantId, {})
      : await provisionChatwootIntegration(accessToken, {});
    setProvisioning(false);
    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    setConfig(result.data);
    notify('success', isManagedReconnect ? 'Chatwoot reconectado.' : 'Cuenta de Chatwoot creada y configurada automáticamente.');
  };

  const handleDisconnect = async () => {
    if (!window.confirm('¿Desconectar Chatwoot? La configuración se conserva y podrás reconectar cuando quieras.')) return;
    setDisconnecting(true);
    const result = mode === 'admin' && tenantId
      ? await disconnectAdminTenantChatwoot(accessToken, tenantId)
      : await disconnectChatwootIntegration(accessToken);
    setDisconnecting(false);
    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    setConfig(result.data);
    setManageOpen(false);
    notify('success', 'Chatwoot desconectado.');
  };

  const copyWebhookUrl = async () => {
    if (!fullWebhookUrl) return;
    try {
      await navigator.clipboard.writeText(fullWebhookUrl);
      notify('success', 'URL de webhook copiada.');
    } catch {
      notify('error', 'No se pudo copiar la URL.');
    }
  };

  const statusDotClass = isActive ? 'bg-emerald-500' : isError ? 'bg-destructive' : 'bg-muted-foreground/50';
  const statusLabel = isActive ? 'Connected' : isError ? 'Error' : hasExistingConfig ? 'Disconnected' : 'Not connected';
  const statusTextClass = isActive
    ? 'text-emerald-700 dark:text-emerald-300'
    : isError
      ? 'text-destructive'
      : 'text-muted-foreground';

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="chatwoot-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500">
            <MessageCircle className="h-5 w-5" />
          </span>
          <div>
            <h2 id="chatwoot-integration-title" className="text-lg font-semibold text-foreground">Chatwoot</h2>
            <p className="text-sm text-muted-foreground">Customer Support / Human Handoff</p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start md:self-auto">
          {config?.mode === 'managed' && (
            <span className="inline-flex items-center rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary">
              ServiGlobal Managed
            </span>
          )}
          <span className={`inline-flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-semibold ${statusTextClass}`}>
            <span className={`h-2 w-2 rounded-full ${statusDotClass}`} aria-hidden />
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="space-y-6 p-5">
        {isActive ? (
          <>
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Account</dt>
                <dd className="text-sm font-medium text-foreground">{config?.account_name || `#${config?.account_id}`}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">URL</dt>
                <dd className="text-sm font-medium text-foreground">{displayUrl}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Default Inbox</dt>
                <dd className="text-sm font-medium text-foreground">
                  {config?.default_inbox_name || (config?.default_inbox_id ? `#${config.default_inbox_id}` : 'No configurado')}
                </dd>
              </div>
            </dl>

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => setManageOpen((v) => !v)} className="gap-2">
                <Settings2 className="h-4 w-4" />
                {manageOpen ? 'Ocultar conexión' : 'Manage connection'}
              </Button>
              <Button type="button" variant="outline" disabled={!config?.has_secret || testing} onClick={handleTest} className="gap-2">
                {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Test connection
              </Button>
              <Button type="button" variant="outline" disabled={disconnecting} onClick={handleDisconnect} className="gap-2 text-destructive hover:text-destructive">
                {disconnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
                Disconnect
              </Button>
            </div>

            {manageOpen && (
              <div className="space-y-6 border-t border-border pt-5">
                <ChatwootConfigForm
                  accessToken={accessToken}
                  config={config}
                  mode={mode}
                  tenantId={tenantId}
                  onSaved={(nextConfig) => {
                    setConfig(nextConfig);
                    notify('success', 'Configuración de Chatwoot guardada.');
                  }}
                  onError={(text) => notify('error', text)}
                />

                {fullWebhookUrl && (
                  <div>
                    <span className="flex items-center gap-1 text-sm font-medium text-muted-foreground">
                      URL de webhook
                      <FieldHelp label="URL de webhook" required align="right">
                        Configúrala en Chatwoot → Settings → Integrations → Webhooks para esta Account. Es única por tenant; no la compartas. En modo managed ya quedó registrada automáticamente.
                      </FieldHelp>
                    </span>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        readOnly
                        type={showWebhookUrl ? 'text' : 'password'}
                        value={fullWebhookUrl}
                        className="min-h-10 flex-1 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-foreground outline-none"
                      />
                      <Button type="button" variant="outline" size="icon" onClick={() => setShowWebhookUrl((v) => !v)} aria-label={showWebhookUrl ? 'Ocultar URL' : 'Mostrar URL'}>
                        {showWebhookUrl ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </Button>
                      <Button type="button" variant="outline" size="icon" onClick={copyWebhookUrl} aria-label="Copiar URL">
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <>
            {isError && config?.last_error_message && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                {config.last_error_message}
              </div>
            )}

            <div role="radiogroup" aria-label="Método de conexión" className="flex flex-col gap-3 sm:flex-row">
              <label className={METHOD_CARD_CLASS}>
                <span className="flex items-center gap-2 font-medium text-foreground">
                  <input type="radio" name="chatwoot-method" checked={method === 'managed'} onChange={() => setMethod('managed')} />
                  ServiGlobal Managed
                </span>
                <span className="text-xs text-muted-foreground">Creamos la Account de Chatwoot por ti, sin salir de esta pantalla.</span>
              </label>
              <label className={METHOD_CARD_CLASS}>
                <span className="flex items-center gap-2 font-medium text-foreground">
                  <input type="radio" name="chatwoot-method" checked={method === 'external'} onChange={() => setMethod('external')} />
                  Connect existing Chatwoot
                </span>
                <span className="text-xs text-muted-foreground">Usa una Account de Chatwoot que ya tienes, con tus propias credenciales.</span>
              </label>
            </div>

            {method === 'managed' ? (
              <div className="flex flex-col gap-3 rounded-lg border border-primary/20 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="flex items-center gap-1 text-sm font-medium text-foreground">
                    {isManagedReconnect ? 'Reconectar la cuenta managed existente' : 'Crear la cuenta automáticamente'}
                    <FieldHelp label="ServiGlobal Managed" required={false}>
                      Crea una Account, un usuario administrator dedicado y un inbox nuevos en Chatwoot para este tenant. Requiere que la plataforma tenga habilitado el aprovisionamiento automático; si no está disponible, usa &quot;Connect existing Chatwoot&quot;.
                    </FieldHelp>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {isManagedReconnect ? 'Reutiliza la Account ya creada, sin duplicarla en Chatwoot.' : 'No necesitas entrar a Chatwoot ni copiar nada.'}
                  </p>
                </div>
                <Button type="button" onClick={handleProvision} disabled={provisioning} className="gap-2 sm:shrink-0">
                  {provisioning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {isManagedReconnect ? 'Reconectar' : 'Crear automáticamente'}
                </Button>
              </div>
            ) : (
              <ChatwootConfigForm
                accessToken={accessToken}
                config={config}
                mode={mode}
                tenantId={tenantId}
                onSaved={(nextConfig) => {
                  setConfig(nextConfig);
                  notify('success', 'Configuración de Chatwoot guardada.');
                }}
                onError={(text) => notify('error', text)}
              />
            )}
          </>
        )}
      </div>

      {message && (
        <div role="status" className={`mx-5 mb-5 rounded-md border p-3 text-sm ${message.type === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-destructive/20 bg-destructive/10 text-destructive'}`}>
          {message.text}
        </div>
      )}
    </section>
  );
}
