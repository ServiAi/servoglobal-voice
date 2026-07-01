'use client';

import { useState } from 'react';
import { AlertCircle, CalendarCheck, CheckCircle2 } from 'lucide-react';
import type { BookingConfigResponse } from '@/types/crm';
import { CalComConfigForm } from './CalComConfigForm';
import { CalComTestForm } from './CalComTestForm';

type Props = {
  accessToken: string;
  initialConfig?: BookingConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

export function CalComIntegrationCard({ accessToken, initialConfig, mode = 'tenant', tenantId }: Props) {
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const isActive = config?.status === 'active';

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-xs">
      <div className="mb-5 flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-fuchsia-500/10 text-fuchsia-500">
            <CalendarCheck className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Cal.com</h2>
            <p className="text-sm text-muted-foreground">Booking engine multitenant</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-2 rounded-md border px-3 py-1 text-xs font-semibold ${isActive ? 'border-emerald-500/30 text-emerald-500' : 'border-amber-500/30 text-amber-500'}`}>
          {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
          {isActive ? `${config?.calendar_mode} active` : config?.status ?? 'no configurado'}
        </span>
      </div>
      <div className="space-y-6">
        <CalComConfigForm
          accessToken={accessToken}
          config={config}
          mode={mode}
          tenantId={tenantId}
          onSaved={(nextConfig) => {
            setConfig(nextConfig);
            notify('success', 'Configuracion Cal.com guardada.');
          }}
          onError={(text) => notify('error', text)}
        />
        <div className="border-t border-border pt-4">
          <CalComTestForm
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
        <div className={`mt-4 rounded-md border p-3 text-sm ${message.type === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500' : 'border-red-500/20 bg-red-500/10 text-red-500'}`}>
          {message.text}
        </div>
      )}
    </section>
  );
}
