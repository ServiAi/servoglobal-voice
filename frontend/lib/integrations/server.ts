import 'server-only';

import { redirect } from 'next/navigation';
import { fetchIntegrationAvailability } from '@/lib/api/crm';
import { getAccessToken } from '@/lib/auth/server';
import type { IntegrationProvider } from '@/types/crm';

export async function getIntegrationAccess(locale: string, provider: IntegrationProvider) {
  const returnTo = `/${locale}/integrations/${provider === 'google_calendar' ? 'google-calendar' : provider}`;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=${returnTo}`);

  const availability = await fetchIntegrationAvailability(accessToken);
  if (availability.ok && availability.data.some((item) => item.provider === provider && !item.enabled)) {
    redirect(`/${locale}/integrations`);
  }
  return accessToken;
}
