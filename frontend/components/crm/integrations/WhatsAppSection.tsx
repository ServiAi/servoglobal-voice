'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { WhatsAppConfigResponse, WhatsAppTemplateResponse } from '@/types/crm';
import { WhatsAppConfigForm } from './WhatsAppConfigForm';
import { WhatsAppTestForm } from './WhatsAppTestForm';
import { WhatsAppTemplateManager } from './whatsapp-templates/WhatsAppTemplateManager';

type Props = {
  accessToken: string;
  section: 'account' | 'templates' | 'test';
  initialConfig?: WhatsAppConfigResponse;
  templates?: WhatsAppTemplateResponse[];
};

export function WhatsAppSection({ accessToken, section, initialConfig, templates = [] }: Props) {
  const router = useRouter();
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };
  const disabled = config?.status !== 'active' || !config.has_secret;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-xs sm:p-6">
      {section === 'account' ? (
        <WhatsAppConfigForm
          accessToken={accessToken}
          config={config}
          onSaved={(nextConfig) => {
            setConfig(nextConfig);
            notify('success', 'Configuración WhatsApp guardada.');
            router.refresh();
          }}
          onError={(text) => notify('error', text)}
        />
      ) : null}
      {section === 'templates' ? (
        <WhatsAppTemplateManager
          accessToken={accessToken}
          templates={templates}
          voiceCallingEnabled={!!config?.voice_calling_enabled}
          disabled={disabled}
          onSuccess={(text) => notify('success', text)}
          onError={(text) => notify('error', text)}
        />
      ) : null}
      {section === 'test' ? (
        <WhatsAppTestForm
          accessToken={accessToken}
          templates={templates}
          disabled={disabled}
          onSuccess={(text) => notify('success', text)}
          onError={(text) => notify('error', text)}
        />
      ) : null}
      {message ? (
        <div role={message.type === 'error' ? 'alert' : 'status'} className={`mt-5 rounded-md border p-3 text-sm ${message.type === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-destructive/20 bg-destructive/10 text-destructive'}`}>
          {message.text}
        </div>
      ) : null}
    </div>
  );
}
