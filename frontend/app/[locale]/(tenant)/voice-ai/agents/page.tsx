import { redirect } from 'next/navigation';
import { AgentsList } from '@/components/crm/agents/AgentsList';
import { fetchAgents } from '@/lib/api/agents';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { canEditAgents, canReadAgents, resolveAgentGateState } from '@/lib/permissions/agents';

export const dynamic = 'force-dynamic';

export default async function AgentsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/agents`);

  const [profileResult, agentsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchAgents(accessToken),
  ]);

  const gateState = resolveAgentGateState({
    canRead: profileResult.ok && canReadAgents(profileResult.profile),
    agentsStatus: agentsResult.ok ? null : agentsResult.status,
  });

  return (
    <AgentsList
      locale={locale}
      canEdit={profileResult.ok && canEditAgents(profileResult.profile)}
      initialAgents={agentsResult.ok ? agentsResult.data : []}
      gateState={gateState}
    />
  );
}
