'use client';

import { useState } from 'react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { updateAdminTenantIntegrationAvailability } from '@/lib/api/crm';
import type { IntegrationAvailabilityResponse, IntegrationProvider } from '@/types/crm';

const LABELS: Record<IntegrationProvider, string> = {
  resend: 'Email transaccional (Resend)',
  voice: 'Voz',
  whatsapp: 'WhatsApp',
  calcom: 'Reservas (Cal.com)',
  google_calendar: 'Google Calendar',
  chatwoot: 'Chatwoot',
};

type Props = {
  accessToken: string;
  tenantId: string;
  initialItems: IntegrationAvailabilityResponse[];
};

export function IntegrationAvailabilityPanel({ accessToken, tenantId, initialItems }: Props) {
  const router = useRouter();
  const t = useTranslations('crm.integrationsCatalog.admin.availability');
  const [items, setItems] = useState(initialItems);
  const [updating, setUpdating] = useState<IntegrationProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = async (provider: IntegrationProvider, enabled: boolean) => {
    setUpdating(provider);
    setError(null);
    const result = await updateAdminTenantIntegrationAvailability(accessToken, tenantId, provider, enabled);
    setUpdating(null);
    if (!result.ok) {
      setError(result.detail);
      return;
    }
    setItems((current) => current.map((item) => (item.provider === provider ? result.data : item)));
    router.refresh();
  };

  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-xs" aria-labelledby="integration-access-title">
      <div className="mb-4">
        <h2 id="integration-access-title" className="text-lg font-semibold text-foreground">{t('title')}</h2>
        <p className="text-sm text-muted-foreground">{t('description')}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((item) => {
          const isUpdating = updating === item.provider;
          return (
            <label key={item.provider} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-border p-3">
              <span>
                <span className="block text-sm font-medium text-foreground">{LABELS[item.provider]}</span>
                <span className="block text-xs text-muted-foreground">{t(item.enabled ? 'enabled' : 'disabled')}</span>
              </span>
              {isUpdating ? (
                <CircularLoader size="xs" glow={false} />
              ) : (
                <input
                  type="checkbox"
                  role="switch"
                  checked={item.enabled}
                  onChange={(event) => update(item.provider, event.target.checked)}
                  disabled={updating !== null}
                  className="h-5 w-9 cursor-pointer accent-primary"
                  aria-label={`${t(item.enabled ? 'disable' : 'enable')} ${LABELS[item.provider]}`}
                />
              )}
            </label>
          );
        })}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
    </section>
  );
}
