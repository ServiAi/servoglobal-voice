import 'server-only';

import { requireInternalAdminAccess } from '@/lib/auth/server';

export async function getAdminIntegrationAccess(locale: string, tenantId: string, suffix = '') {
  const integrationsPath = `/admin/tenants/${tenantId}/integrations`;
  const returnTo = `/${locale}${integrationsPath}${suffix ? `/${suffix}` : ''}`;
  const { accessToken } = await requireInternalAdminAccess(locale, returnTo);
  return { accessToken, integrationsPath, returnTo };
}
