import { getTranslations } from 'next-intl/server';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { VoiceExperienceBuilder } from '@/components/crm/voice-experiences/VoiceExperienceBuilder';
import { Button } from '@/components/ui/button';
import { getAccessToken } from '@/lib/auth/server';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import { canEditVoiceExperiences } from '@/lib/permissions/voice-experiences';

export const dynamic = 'force-dynamic';

export default async function NewVoiceExperiencePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/experiences/new`);

  const [profileResult, agentsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchVoiceAgents(accessToken),
  ]);
  const canEdit = profileResult.ok && canEditVoiceExperiences(profileResult.profile);
  if (!canEdit || !agentsResult.ok || agentsResult.data.length === 0) {
    const t = await getTranslations('crm.voiceExperiences');
    const noAgents = agentsResult.ok && agentsResult.data.length === 0;
    const integrationDisabled = !agentsResult.ok && agentsResult.status === 404;
    const state = noAgents ? 'noAgents' : integrationDisabled ? 'integrationDisabled' : 'accessDenied';
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
        <h1 className="text-xl font-semibold">{t(`${state}.title`)}</h1>
        <p className="mt-2 text-sm">{t(`${state}.description`)}</p>
        {noAgents || integrationDisabled ? (
          <Button asChild className="mt-5">
            <Link href={`/${locale}/crm/settings/integrations`}>{t(`${state}.cta`)}</Link>
          </Button>
        ) : null}
      </div>
    );
  }

  return <VoiceExperienceBuilder mode="create" locale={locale} canEdit agents={agentsResult.data} />;
}
