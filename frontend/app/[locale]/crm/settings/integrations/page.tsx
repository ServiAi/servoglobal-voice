import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import {
  fetchBookingConfig,
  fetchGoogleCalendarConnections,
  fetchIntegrationAvailability,
  fetchTenantIntegrations,
  fetchVoiceConfig,
  fetchVoiceAgents,
  fetchWhatsAppConfig,
  fetchWhatsAppTemplates,
} from '@/lib/api/crm';
import { CalComIntegrationCard } from '@/components/crm/integrations/CalComIntegrationCard';
import { GoogleCalendarIntegrationCard } from '@/components/crm/integrations/GoogleCalendarIntegrationCard';
import { ResendIntegrationCard } from '@/components/crm/integrations/ResendIntegrationCard';
import { VoiceIntegrationCard } from '@/components/crm/integrations/VoiceIntegrationCard';
import { WhatsAppIntegrationCard } from '@/components/crm/integrations/WhatsAppIntegrationCard';
import { CrmIntegrationStatusBadge } from '@/components/crm/integrations/CrmIntegrationStatusBadge';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

export default async function CrmIntegrationsPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/settings/integrations`);
  }
  const [
    availabilityResult,
    integrationsResult,
    bookingConfigResult,
    googleConnectionsResult,
    voiceConfigResult,
    voiceAgentsResult,
    whatsappConfigResult,
    whatsappTemplatesResult,
  ] = await Promise.all([
    fetchIntegrationAvailability(accessToken),
    fetchTenantIntegrations(accessToken),
    fetchBookingConfig(accessToken),
    fetchGoogleCalendarConnections(accessToken),
    fetchVoiceConfig(accessToken),
    fetchVoiceAgents(accessToken),
    fetchWhatsAppConfig(accessToken),
    fetchWhatsAppTemplates(accessToken),
  ]);

  const resendConfig = integrationsResult.ok
    ? integrationsResult.data.find((item) => item.provider === 'resend')
    : undefined;
  const enabledProviders = new Set(
    availabilityResult.ok
      ? availabilityResult.data.filter((item) => item.enabled).map((item) => item.provider)
      : ['resend', 'voice', 'whatsapp', 'calcom', 'google_calendar']
  );
  const summaries = [
    { name: 'Email transaccional', status: !integrationsResult.ok ? 'error' : resendConfig?.status === 'active' ? 'active' : resendConfig ? 'configured' : 'not_configured' },
    { name: 'Voz', status: !voiceConfigResult.ok ? 'error' : voiceConfigResult.data?.status === 'active' ? 'active' : voiceConfigResult.data ? 'configured' : 'not_configured' },
    { name: 'WhatsApp', status: !whatsappConfigResult.ok ? 'error' : whatsappConfigResult.data?.status === 'active' ? 'active' : whatsappConfigResult.data ? 'configured' : 'not_configured' },
    { name: 'Reservas', status: !bookingConfigResult.ok ? 'error' : bookingConfigResult.data?.status === 'active' ? 'active' : bookingConfigResult.data ? 'configured' : 'not_configured' },
    { name: 'Google Calendar', status: !googleConnectionsResult.ok ? 'error' : googleConnectionsResult.data.length ? 'active' : 'not_configured' },
  ].filter((_, index) => enabledProviders.has(['resend', 'voice', 'whatsapp', 'calcom', 'google_calendar'][index])) as Array<{
    name: string;
    status: 'active' | 'configured' | 'not_configured' | 'error';
  }>;
  const loadErrors = [
    !availabilityResult.ok,
    enabledProviders.has('resend') && !integrationsResult.ok,
    enabledProviders.has('calcom') && !bookingConfigResult.ok,
    enabledProviders.has('google_calendar') && !googleConnectionsResult.ok,
    enabledProviders.has('voice') && (!voiceConfigResult.ok || !voiceAgentsResult.ok),
    enabledProviders.has('whatsapp') && (!whatsappConfigResult.ok || !whatsappTemplatesResult.ok),
  ].filter(Boolean).length;
  const activeIntegrations = summaries.filter((item) => item.status === 'active').length;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8">
      <div className="flex flex-col gap-4 border-l-4 border-primary pl-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Integraciones CRM</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">Conecta y supervisa los canales comerciales de tu organización.</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span aria-hidden="true" className="size-2 rounded-full bg-emerald-500" />
          <span><strong className="font-semibold text-foreground">{activeIntegrations}</strong> de {summaries.length} activas</span>
        </div>
      </div>
      <section aria-label="Estado de integraciones" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {summaries.map((item, index) => (
          <div
            key={item.name}
            className={`flex min-h-28 flex-col justify-between gap-4 rounded-lg border p-4 shadow-xs ${
              item.status === 'active' ? 'border-emerald-500/25 bg-emerald-500/5' : 'border-border bg-card'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold text-foreground">{item.name}</p>
              <span className="text-xs font-semibold tabular-nums text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
            </div>
            <CrmIntegrationStatusBadge status={item.status} />
          </div>
        ))}
      </section>
      {loadErrors > 0 && (
        <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          No fue posible cargar {loadErrors === 1 ? 'una integración' : `${loadErrors} integraciones`}. Puedes revisar las tarjetas disponibles o recargar la página.
        </div>
      )}
      <section className="flex flex-col gap-4" aria-labelledby="communication-integrations">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <h2 id="communication-integrations" className="text-lg font-semibold text-foreground">Comunicación</h2>
        <span className="text-xs font-medium text-muted-foreground">Email, voz y mensajería</span>
      </div>
      {enabledProviders.has('resend') && <ResendIntegrationCard accessToken={accessToken} initialConfig={resendConfig} />}
      {enabledProviders.has('voice') && (
        <div id="voice-integration" className="scroll-mt-6">
          <VoiceIntegrationCard
            accessToken={accessToken}
            initialConfig={voiceConfigResult.ok ? voiceConfigResult.data : undefined}
            initialAgents={voiceAgentsResult.ok ? voiceAgentsResult.data : []}
          />
        </div>
      )}
      {enabledProviders.has('whatsapp') && (
        <WhatsAppIntegrationCard
          accessToken={accessToken}
          initialConfig={whatsappConfigResult.ok ? whatsappConfigResult.data : undefined}
          templates={whatsappTemplatesResult.ok ? whatsappTemplatesResult.data : []}
        />
      )}
      </section>
      <section className="flex flex-col gap-4" aria-labelledby="scheduling-integrations">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <h2 id="scheduling-integrations" className="text-lg font-semibold text-foreground">Agenda y reservas</h2>
        <span className="text-xs font-medium text-muted-foreground">Reservas y calendarios conectados</span>
      </div>
      {enabledProviders.has('calcom') && <CalComIntegrationCard accessToken={accessToken} initialConfig={bookingConfigResult.ok ? bookingConfigResult.data : undefined} />}
      {enabledProviders.has('google_calendar') && (
        <GoogleCalendarIntegrationCard
          accessToken={accessToken}
          connections={googleConnectionsResult.ok ? googleConnectionsResult.data : []}
        />
      )}
      </section>
    </div>
  );
}
