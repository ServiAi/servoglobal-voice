'use client';

import { useState } from 'react';
import { AlertCircle, CheckCircle2, Copy, Eye, EyeOff, Loader2, MessageCircle, Send, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { provisionChatwootIntegration, testChatwootIntegration } from '@/lib/api/crm';
import type { ChatwootConfigResponse } from '@/types/crm';
import { ChatwootConfigForm } from './ChatwootConfigForm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  initialConfig?: ChatwootConfigResponse;
};

export function ChatwootIntegrationCard({ accessToken, initialConfig }: Props) {
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showWebhookUrl, setShowWebhookUrl] = useState(false);
  const [testing, setTesting] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const isActive = config?.status === 'active';

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
  const fullWebhookUrl = config?.webhook_url ? `${apiBaseUrl}${config.webhook_url}` : null;

  const handleTest = async () => {
    setTesting(true);
    const result = await testChatwootIntegration(accessToken);
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
    const result = await provisionChatwootIntegration(accessToken, {});
    setProvisioning(false);
    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    setConfig(result.data);
    notify('success', 'Cuenta de Chatwoot creada y configurada automáticamente.');
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

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="chatwoot-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-500">
            <MessageCircle className="h-5 w-5" />
          </span>
          <div>
            <h2 id="chatwoot-integration-title" className="text-lg font-semibold text-foreground">Chatwoot</h2>
            <p className="text-sm text-muted-foreground">Conversaciones y handoff a humanos por tenant</p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start md:self-auto">
          {config?.mode === 'managed' && (
            <span className="inline-flex items-center rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary">
              Managed
            </span>
          )}
          <span className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-semibold ${isActive ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'}`}>
            {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            {isActive ? 'Activa' : config?.status ?? 'Sin configurar'}
          </span>
        </div>
      </div>

      <div className="space-y-6 p-5">
        {!isActive && (
          <div className="flex flex-col gap-3 rounded-lg border border-primary/20 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="flex items-center gap-1 text-sm font-medium text-foreground">
                Crear la cuenta automáticamente
                <FieldHelp label="Crear la cuenta automáticamente" required={false}>
                  Crea una Account, un Agent Bot y un inbox nuevos en Chatwoot para este tenant sin salir de esta pantalla. Requiere que la plataforma tenga habilitado el aprovisionamiento automático (modo &quot;managed&quot;); si no está disponible, usa el formulario manual de abajo.
                </FieldHelp>
              </p>
              <p className="text-xs text-muted-foreground">Alternativa a llenar el formulario manual con datos de una Account existente.</p>
            </div>
            <Button type="button" onClick={handleProvision} disabled={provisioning} className="gap-2 sm:shrink-0">
              {provisioning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Crear automáticamente
            </Button>
          </div>
        )}

        <ChatwootConfigForm
          accessToken={accessToken}
          config={config}
          onSaved={(nextConfig) => {
            setConfig(nextConfig);
            notify('success', 'Configuración de Chatwoot guardada.');
          }}
          onError={(text) => notify('error', text)}
        />

        {fullWebhookUrl && (
          <div className="border-t border-border pt-5">
            <span className="flex items-center gap-1 text-sm font-medium text-muted-foreground">
              URL de webhook
              <FieldHelp label="URL de webhook" required align="right">
                Configúrala en Chatwoot → Settings → Integrations → Webhooks para esta Account. Es única por tenant; no la compartas.
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

        <div className="border-t border-border pt-5">
          <Button type="button" variant="outline" disabled={!isActive || !config?.has_secret || testing} onClick={handleTest} className="gap-2">
            {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Probar conexión
          </Button>
        </div>
      </div>

      {message && (
        <div role="status" className={`mx-5 mb-5 rounded-md border p-3 text-sm ${message.type === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-destructive/20 bg-destructive/10 text-destructive'}`}>
          {message.text}
        </div>
      )}
    </section>
  );
}
