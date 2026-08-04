'use client';

import { useState } from 'react';
import { AlertCircle, CheckCircle2, Mail } from 'lucide-react';
import type { ResendIntegrationConfigResponse } from '@/types/crm';
import { ResendConfigForm } from './ResendConfigForm';
import { ResendTestEmailForm } from './ResendTestEmailForm';

type Props = {
  accessToken: string;
  initialConfig?: ResendIntegrationConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

export function ResendIntegrationCard({ accessToken, initialConfig, mode = 'tenant', tenantId }: Props) {
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const isActive = config?.status === 'active';

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="resend-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-amber-500/10 text-amber-500">
            <Mail className="h-5 w-5" />
          </span>
          <div>
            <h2 id="resend-integration-title" className="text-lg font-semibold text-foreground">Resend</h2>
            <p className="text-sm text-muted-foreground">Email transaccional por tenant</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-2 self-start rounded-md border px-3 py-1.5 text-xs font-semibold md:self-auto ${isActive ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'}`}>
          {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
          {isActive ? 'Activa' : config?.status ?? 'Sin configurar'}
        </span>
      </div>

      <div className="space-y-6 p-5">
        <ResendConfigForm
          accessToken={accessToken}
          config={config}
          mode={mode}
          tenantId={tenantId}
          onSaved={(nextConfig) => {
            setConfig(nextConfig);
            notify('success', 'Configuracion Resend guardada.');
          }}
          onError={(text) => notify('error', text)}
        />
        <div className="border-t border-border pt-5">
          <ResendTestEmailForm
            accessToken={accessToken}
            mode={mode}
            tenantId={tenantId}
            disabled={!isActive || !config?.has_secret}
            onSuccess={(text) => notify('success', text)}
            onError={(text) => notify('error', text)}
          />
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
