import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchGoogleCalendarConnections } from '@/lib/api/crm';
import {
  fetchSchedulingConfig,
  fetchSchedulingExceptions,
  fetchSchedulingResources,
  fetchSchedulingSummary,
  fetchSchedulingTeams,
} from '@/lib/api/scheduling';
import { AgendaWorkspace } from '@/components/agenda/AgendaWorkspace';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

const WRITE_ROLES = new Set(['platform_admin', 'tenant_admin']);

export default async function AgendaPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/agenda`);
  }

  const [
    profileResult,
    summaryResult,
    configResult,
    resourcesResult,
    teamsResult,
    exceptionsResult,
    googleConnectionsResult,
  ] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchSchedulingSummary(accessToken),
    fetchSchedulingConfig(accessToken),
    fetchSchedulingResources(accessToken),
    fetchSchedulingTeams(accessToken),
    fetchSchedulingExceptions(accessToken),
    fetchGoogleCalendarConnections(accessToken),
  ]);

  const canEdit = profileResult.ok && WRITE_ROLES.has(profileResult.profile.role);

  const fallbackSummary = {
    active_resources_count: 0,
    teams_count: 0,
    connected_calendars_count: 0,
    upcoming_bookings_count: 0,
    google_connected: false,
    availability_configured: false,
    agents_count: 0,
    alerts: [],
  };

  const fallbackConfig = {
    id: '',
    tenant_id: '',
    timezone: 'America/Bogota',
    default_duration_minutes: 30,
    slot_interval_minutes: 30,
    buffer_before_minutes: 0,
    buffer_after_minutes: 0,
    minimum_notice_minutes: 60,
    maximum_booking_days: 30,
    routing_strategy: 'single',
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const connectedCals: Array<{ id: string; google_calendar_id: string; summary?: string | null }> = [];
  if (googleConnectionsResult.ok) {
    for (const conn of googleConnectionsResult.data) {
      if (conn.status === 'connected' && conn.calendar_id) {
        connectedCals.push({
          id: conn.id,
          google_calendar_id: conn.calendar_id,
          summary: conn.google_account_email,
        });
      }
    }
  }

  return (
    <div className="container mx-auto p-4 md:p-6 max-w-7xl">
      <AgendaWorkspace
        locale={locale}
        canEdit={canEdit}
        initialSummary={summaryResult.ok ? summaryResult.data : fallbackSummary}
        initialConfig={configResult.ok ? configResult.data : fallbackConfig}
        initialResources={resourcesResult.ok ? resourcesResult.data : []}
        initialTeams={teamsResult.ok ? teamsResult.data : []}
        initialExceptions={exceptionsResult.ok ? exceptionsResult.data : []}
        connectedGoogleCalendars={connectedCals}
      />
    </div>
  );
}
