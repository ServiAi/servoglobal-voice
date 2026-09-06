import { getTranslations } from 'next-intl/server';
import { redirect } from 'next/navigation';
import { AgentBuilder } from '@/components/crm/agents/AgentBuilder';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchVoiceModels, fetchVoiceProviders } from '@/lib/api/voice-registry';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { canEditAgents } from '@/lib/permissions/agents';

export const dynamic = 'force-dynamic';

export default async function NewAgentPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/agents/new`);

  const [profileResult, voiceAgentsResult, providersResult, modelsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchVoiceAgents(accessToken),
    fetchVoiceProviders(accessToken),
    fetchVoiceModels(accessToken),
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
    />
  );
}
