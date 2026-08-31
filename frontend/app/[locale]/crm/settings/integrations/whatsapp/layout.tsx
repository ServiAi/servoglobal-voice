import type { ReactNode } from 'react';
import { WhatsAppIntegrationNavigation } from '@/components/crm/integrations/WhatsAppIntegrationNavigation';
import { fetchWhatsAppConfig } from '@/lib/api/crm';
import { resolveIntegrationStatus } from '@/lib/integrations/catalog';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { children: ReactNode; params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function WhatsAppIntegrationLayout({ children, params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'whatsapp');
  const result = await fetchWhatsAppConfig(accessToken);
  const config = result.ok ? result.data : undefined;
  const status = resolveIntegrationStatus(result.ok, config, Boolean(config?.phone_number_id || config?.has_secret));
  return <div className="mx-auto flex max-w-7xl flex-col gap-6"><WhatsAppIntegrationNavigation locale={locale} status={status} />{children}</div>;
}
