import { AudioLines, Plus } from 'lucide-react';
import { getTranslations } from 'next-intl/server';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { VoiceExperiencesList } from '@/components/crm/voice-experiences/VoiceExperiencesList';
import { Button } from '@/components/ui/button';
import { getAccessToken } from '@/lib/auth/server';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import {
  fetchVoiceExperiences,
  fetchVoiceExperienceVersions,
} from '@/lib/api/voice-experiences';
import {
  canEditVoiceExperiences,
  canReadVoiceExperiences,
  resolveVoiceExperienceGateState,
} from '@/lib/permissions/voice-experiences';

export const dynamic = 'force-dynamic';

export default async function VoiceExperiencesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/experiences`);

  const t = await getTranslations('crm.voiceExperiences');
  const [profileResult, experiencesResult, agentsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchVoiceExperiences(accessToken),
    fetchVoiceAgents(accessToken),
  ]);

  const gateState = resolveVoiceExperienceGateState({
    canRead: profileResult.ok && canReadVoiceExperiences(profileResult.profile),
    experiencesStatus: experiencesResult.ok ? null : experiencesResult.status,
    agentsStatus: agentsResult.ok ? null : agentsResult.status,
    agentCount: agentsResult.ok ? agentsResult.data.length : 0,
  });

  const experiences = experiencesResult.ok ? experiencesResult.data : [];
  const agents = agentsResult.ok ? agentsResult.data : [];
  const versionEntries = gateState === 'ok'
    ? await Promise.all(
        experiences.map(async (experience) => {
          const result = await fetchVoiceExperienceVersions(accessToken, experience.id);
          // null = could not determine. Never turn a read error into "0", which
          // would wrongly present an experience as safe to delete (fail-closed).
          return [experience.id, result.ok ? result.data.length : null] as const;
        })
      )
    : [];

  return (
    <div className="space-y-8 pb-12">
      <header className="relative overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 px-6 py-7 text-white shadow-sm sm:px-8">
        <div className="absolute inset-y-0 right-0 w-2/5 bg-[radial-gradient(circle_at_center,rgba(34,211,238,0.18),transparent_68%)]" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <p className="mb-3 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
              <AudioLines className="size-4" aria-hidden="true" />
              {t('page.eyebrow')}
            </p>
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t('page.title')}</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">{t('page.description')}</p>
          </div>
          {gateState === 'ok' && profileResult.ok && canEditVoiceExperiences(profileResult.profile) ? (
            <Button asChild className="bg-cyan-400 text-slate-950 hover:bg-cyan-300">
              <Link href={`/${locale}/voice-ai/experiences/new`}>
                <Plus className="mr-2 size-4" aria-hidden="true" />
                {t('newExperience')}
              </Link>
            </Button>
          ) : null}
        </div>
      </header>

      <VoiceExperiencesList
        locale={locale}
        canEdit={profileResult.ok && canEditVoiceExperiences(profileResult.profile)}
        initialExperiences={experiences}
        agents={agents}
        versionCounts={Object.fromEntries(versionEntries)}
        gateState={gateState}
      />
    </div>
  );
}
