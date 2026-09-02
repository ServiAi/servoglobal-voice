import type { ReactNode } from 'react';
import { WhatsAppIntegrationNavigation } from '@/components/crm/integrations/WhatsAppIntegrationNavigation';
import { fetchAdminTenantWhatsAppConfig } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';
import { resolveIntegrationStatus } from '@/lib/integrations/catalog';

type Props = { children: ReactNode; params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantWhatsAppLayout({ children, params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath } = await getAdminIntegrationAccess(locale, tenantId, 'whatsapp');
  const result = await fetchAdminTenantWhatsAppConfig(accessToken, tenantId);
  const config = result.ok ? result.data : undefined;
  const status = resolveIntegrationStatus(result.ok, config, Boolean(config?.phone_number_id || config?.has_secret));
  return <div className="mx-auto flex max-w-7xl flex-col gap-6"><WhatsAppIntegrationNavigation locale={locale} status={status} basePath={`${integrationsPath}/whatsapp`} includeFlows={false} />{children}</div>;
}
