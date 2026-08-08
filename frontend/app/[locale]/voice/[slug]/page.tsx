import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { PublicVoiceExperience } from '@/components/public/voice/PublicVoiceExperience';
import { fetchPublicVoiceExperience } from '@/lib/api/public-voice-experiences';

export const dynamic = 'force-dynamic';

interface PageProps {
  params: Promise<{ locale: string; slug: string }>;
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('publicVoiceExperience.metadata');
  return {
    title: t('title'),
    description: t('description'),
    robots: { index: false, follow: false },
  };
}

export default async function PublicVoiceExperiencePage({ params }: PageProps) {
  const { slug } = await params;
  const [result, t] = await Promise.all([
    fetchPublicVoiceExperience(slug),
    getTranslations('publicVoiceExperience'),
  ]);

  if (!result.ok) notFound();

  return (
    <PublicVoiceExperience
      experience={result.data}
      messages={{
        eyebrow: t('eyebrow'),
        version: t('version'),
        required: t('required'),
        selectPlaceholder: t('selectPlaceholder'),
        privacy: t('privacy'),
        emptyFields: t('emptyFields'),
        noticeTitle: t('noticeTitle'),
        noticeDescription: t('noticeDescription'),
        logoAlt: t('logoAlt'),
      }}
    />
  );
}
