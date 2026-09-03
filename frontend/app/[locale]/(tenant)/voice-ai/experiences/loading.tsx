import { getTranslations } from 'next-intl/server';

export default async function VoiceExperiencesLoading() {
  const t = await getTranslations('crm.voiceExperiences');
  return (
    <div className="space-y-6" aria-busy="true" aria-label={t('common.loading')}>
      <div className="h-44 animate-pulse rounded-2xl bg-slate-900" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-60 animate-pulse rounded-xl bg-muted" />
        <div className="h-60 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}
