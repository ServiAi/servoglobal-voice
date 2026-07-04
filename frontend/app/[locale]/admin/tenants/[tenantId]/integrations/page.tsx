import { locales, type Locale } from '@/i18n';
import {
  fetchAdminTenantBookingConfig,
  fetchAdminTenantGoogleCalendarConnections,
  fetchAdminTenantIntegrations,
  fetchAdminTenantVoiceConfig,
  fetchAdminTenantVoiceAgents,
} from '@/lib/api/crm';
import {
  redirectAdminAccessFailure,
  requireInternalAdminAccess,
} from '@/lib/auth/server';
import { ResendIntegrationCard } from '@/components/crm/integrations/ResendIntegrationCard';
import { CalComIntegrationCard } from '@/components/crm/integrations/CalComIntegrationCard';
import { GoogleCalendarIntegrationCard } from '@/components/crm/integrations/GoogleCalendarIntegrationCard';
import { VoiceIntegrationCard } from '@/components/crm/integrations/VoiceIntegrationCard';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

type Props = {
  params: Promise<{ locale: string; tenantId: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function AdminTenantIntegrationsPage({ params }: Props) {
  const { locale: rawLocale, tenantId } = await params;
  const locale = normalizeLocale(rawLocale);
  const returnTo = `/${locale}/admin/tenants/${tenantId}/integrations`;
  
  // Guard access to internal platform admin
  const { accessToken } = await requireInternalAdminAccess(locale, returnTo);

  // Fetch the configurations using our admin API client method
  const integrationsResult = await fetchAdminTenantIntegrations(accessToken, tenantId);
  const bookingConfigResult = await fetchAdminTenantBookingConfig(accessToken, tenantId);
  const googleConnectionsResult = await fetchAdminTenantGoogleCalendarConnections(accessToken, tenantId);
  const voiceConfigResult = await fetchAdminTenantVoiceConfig(accessToken, tenantId);
  const voiceAgentsResult = await fetchAdminTenantVoiceAgents(accessToken, tenantId);

  if (!integrationsResult.ok) {
    redirectAdminAccessFailure(integrationsResult.status, locale, returnTo);
  }

  const resendConfig = integrationsResult.ok
    ? integrationsResult.data.find((item) => item.provider === 'resend')
    : undefined;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      {/* Back button */}
      <div>
        <Link
          href={`/${locale}/admin/tenants/${tenantId}`}
          className="inline-flex items-center gap-1.5 text-sm text-zinc-500 transition hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver al detalle del tenant
        </Link>
      </div>

      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Integraciones del tenant</h1>
        <p className="text-sm text-muted-foreground">Configura proveedores externos para este tenant</p>
      </div>

      <ResendIntegrationCard
        accessToken={accessToken}
        initialConfig={resendConfig}
        mode="admin"
        tenantId={tenantId}
      />
      <VoiceIntegrationCard
        accessToken={accessToken}
        initialConfig={voiceConfigResult.ok ? voiceConfigResult.data : undefined}
        initialAgents={voiceAgentsResult.ok ? voiceAgentsResult.data : []}
        mode="admin"
        tenantId={tenantId}
      />
      <CalComIntegrationCard
        accessToken={accessToken}
        initialConfig={bookingConfigResult.ok ? bookingConfigResult.data : undefined}
        mode="admin"
        tenantId={tenantId}
      />
      <GoogleCalendarIntegrationCard connections={googleConnectionsResult.ok ? googleConnectionsResult.data : []} />
    </div>
  );
}
