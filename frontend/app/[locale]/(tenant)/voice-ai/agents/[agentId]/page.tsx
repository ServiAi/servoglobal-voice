import { getTranslations } from 'next-intl/server';
import { notFound, redirect } from 'next/navigation';
import { AgentBuilder } from '@/components/crm/agents/AgentBuilder';
import { fetchAgent, fetchAgentDraft, fetchAgentVersions } from '@/lib/api/agents';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchVoiceModels, fetchVoiceProviders } from '@/lib/api/voice-registry';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { canEditAgents, canReadAgents } from '@/lib/permissions/agents';

export const dynamic = 'force-dynamic';

export default async function AgentEditorPage({
  params,
}: {
  params: Promise<{ locale: string; agentId: string }>;
}) {
  const { locale, agentId } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/agents/${agentId}`);

  const [profileResult, agentResult, voiceAgentsResult, providersResult, modelsResult] =
    await Promise.all([
      fetchMeProfile(accessToken),
      fetchAgent(accessToken, agentId),
      fetchVoiceAgents(accessToken),
      fetchVoiceProviders(accessToken),
      fetchVoiceModels(accessToken),
    ]);
  if (!agentResult.ok && agentResult.status === 404) notFound();

  const canRead = profileResult.ok && canReadAgents(profileResult.profile);
  if (!canRead || !agentResult.ok) {
    const t = await getTranslations('crm.agentBuilder');
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
        <h1 className="text-xl font-semibold">{t('errors.loadTitle')}</h1>
        <p className="mt-2 text-sm">{t('errors.generic')}</p>
      </div>
    );
  }

  const agent = agentResult.data;
  const [draftResult, versionsResult] = await Promise.all([
    fetchAgentDraft(accessToken, agent.id),
    fetchAgentVersions(accessToken, agent.id),
  ]);

  return (
    <AgentBuilder
      mode="edit"
      locale={locale}
      canEdit={canEditAgents(profileResult.profile)}
      voiceAgents={voiceAgentsResult.ok ? voiceAgentsResult.data : []}
      providers={providersResult.ok ? providersResult.data : []}
      models={modelsResult.ok ? modelsResult.data : []}
      initialAgent={agent}
      initialDraft={draftResult.ok ? draftResult.data : null}
      initialVersions={versionsResult.ok ? versionsResult.data : []}
    />
  );
}
