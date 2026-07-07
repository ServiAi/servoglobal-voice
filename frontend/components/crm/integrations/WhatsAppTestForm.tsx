'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { testAdminTenantWhatsAppIntegration, testWhatsAppIntegration } from '@/lib/api/crm';
import type { WhatsAppTemplateResponse } from '@/types/crm';

type Props = {
  accessToken: string;
  templates: WhatsAppTemplateResponse[];
  disabled?: boolean;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
};

export function WhatsAppTestForm({ accessToken, templates, disabled, mode = 'tenant', tenantId, onSuccess, onError }: Props) {
  const [toPhone, setToPhone] = useState('');
  const [templateKey, setTemplateKey] = useState(templates[0]?.template_key ?? 'lead_follow_up');
  const [sending, setSending] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSending(true);
    const payload = { to_phone: toPhone || null, template_key: templateKey };
    const result = mode === 'admin' && tenantId
      ? await testAdminTenantWhatsAppIntegration(accessToken, tenantId, payload)
      : await testWhatsAppIntegration(accessToken, payload);
    setSending(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    onSuccess('Conexion WhatsApp validada correctamente.');
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
      <input
        className="rounded-md border border-border bg-background px-3 py-2 text-sm"
        value={toPhone}
        onChange={(e) => setToPhone(e.target.value)}
        placeholder="+573001112233"
      />
      <select
        className="rounded-md border border-border bg-background px-3 py-2 text-sm"
        value={templateKey}
        onChange={(e) => setTemplateKey(e.target.value)}
      >
        {templates.map((template) => (
          <option key={template.id} value={template.template_key}>{template.name}</option>
        ))}
      </select>
      <Button type="submit" disabled={disabled || sending} variant="outline" className="gap-2">
        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        Probar
      </Button>
    </form>
  );
}
