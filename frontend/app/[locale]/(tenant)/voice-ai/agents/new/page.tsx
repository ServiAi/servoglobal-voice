import { getTranslations } from 'next-intl/server';
import { redirect } from 'next/navigation';
import { AgentBuilder } from '@/components/crm/agents/AgentBuilder';
import { fetchToolCatalog } from '@/lib/api/agents';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchVoiceModels, fetchVoiceProviders } from '@/lib/api/voice-registry';
import { fetchProviderVoices } from '@/lib/api/voice-provider-admin';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { canEditAgents } from '@/lib/permissions/agents';

export const dynamic = 'force-dynamic';

export default async function NewAgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const query = await searchParams;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/agents/new`);

  const [profileResult, voiceAgentsResult, providersResult, modelsResult, providerVoicesResult, toolCatalogResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchVoiceAgents(accessToken),
    fetchVoiceProviders(accessToken),
    fetchVoiceModels(accessToken),
    fetchProviderVoices(accessToken, 'ultravox', { pageSize: 50 }),
    fetchToolCatalog(accessToken),
  ]);
  const canEdit = profileResult.ok && canEditAgents(profileResult.profile);
  if (!canEdit) {
    const t = await getTranslations('crm.agentBuilder');
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
        <h1 className="text-xl font-semibold">{t('accessDenied.title')}</h1>
        <p className="mt-2 text-sm">{t('accessDenied.description')}</p>
      </div>
    );
  }

  return (
    <AgentBuilder
      mode="create"
      locale={locale}
      canEdit
      voiceAgents={voiceAgentsResult.ok ? voiceAgentsResult.data : []}
      providers={providersResult.ok ? providersResult.data : []}
      models={modelsResult.ok ? modelsResult.data : []}
      providerVoices={providerVoicesResult.ok ? providerVoicesResult.data.results : []}
      toolCatalog={toolCatalogResult.ok ? toolCatalogResult.data : []}
      initialProviderAgent={query.management_mode === 'provider_managed' && typeof query.provider_agent_id === 'string' ? {
        agentId: query.provider_agent_id,
        name: typeof query.provider_agent_name === 'string' ? query.provider_agent_name : query.provider_agent_id,
        observedPublishedRevisionId: typeof query.observed_published_revision_id === 'string' ? query.observed_published_revision_id : null,
      } : null}
    />
  );
}
