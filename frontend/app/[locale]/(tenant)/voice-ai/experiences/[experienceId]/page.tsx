import { getTranslations } from 'next-intl/server';
import { notFound, redirect } from 'next/navigation';
import { VoiceExperienceBuilder } from '@/components/crm/voice-experiences/VoiceExperienceBuilder';
import { getAccessToken } from '@/lib/auth/server';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import {
  fetchVoiceContextSchema,
  fetchVoiceContextSchemas,
  fetchVoiceExperience,
  fetchVoiceExperienceVersions,
} from '@/lib/api/voice-experiences';
import {
  canEditVoiceExperiences,
  canReadVoiceExperiences,
} from '@/lib/permissions/voice-experiences';

export const dynamic = 'force-dynamic';

export default async function VoiceExperienceEditorPage({
  params,
}: {
  params: Promise<{ locale: string; experienceId: string }>;
}) {
  const { locale, experienceId } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/experiences/${experienceId}`);

  const [profileResult, experienceResult, agentsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchVoiceExperience(accessToken, experienceId),
    fetchVoiceAgents(accessToken),
  ]);
  if (!experienceResult.ok && experienceResult.status === 404) notFound();

  const canRead = profileResult.ok && canReadVoiceExperiences(profileResult.profile);
  if (!canRead || !experienceResult.ok || !agentsResult.ok) {
    const t = await getTranslations('crm.voiceExperiences');
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
        <h1 className="text-xl font-semibold">{t('errors.loadTitle')}</h1>
        <p className="mt-2 text-sm">{t('errors.generic')}</p>
      </div>
    );
  }

  const experience = experienceResult.data;
  const [versionsResult, schemasResult, schemaResult] = await Promise.all([
    fetchVoiceExperienceVersions(accessToken, experience.id),
    fetchVoiceContextSchemas(accessToken, experience.agent_config_id),
    fetchVoiceContextSchema(accessToken, experience.context_schema_id),
  ]);

  return (
    <VoiceExperienceBuilder
      mode="edit"
      locale={locale}
      canEdit={canEditVoiceExperiences(profileResult.profile)}
      agents={agentsResult.data}
      initialExperience={experience}
      initialVersions={versionsResult.ok ? versionsResult.data : []}
      versionsUnknown={!versionsResult.ok}
      initialSchemas={schemasResult.ok ? schemasResult.data : []}
      initialSchema={schemaResult.ok ? schemaResult.data : null}
    />
  );
}
