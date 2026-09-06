import { CircularLoadingState } from '@/components/ui/circular-loader';
import { getTranslations } from 'next-intl/server';

export default async function VoiceExperiencesLoading() {
  const t = await getTranslations('crm.voiceExperiences');
  return (
    <CircularLoadingState
      message={t('common.loading')}
      minHeight="min-h-[50vh]"
    />
  );
}
