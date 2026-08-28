import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { PublicVoiceExperience } from '@/components/public/voice/PublicVoiceExperience';
import { fetchPublicVoiceExperience } from '@/lib/api/public-voice-experiences';
import { buildPublicVoiceMessages } from '@/lib/voice-experiences/public-voice-messages';

export const dynamic = 'force-dynamic';

interface PageProps {
  params: Promise<{ locale: string; slug: string }>;
}

export async function generateMetadata(): Promise<Metadata> {
  return { robots: { index: false, follow: false } };
}

export default async function VoiceExperienceEmbedPage({ params }: PageProps) {
  const { locale, slug } = await params;
  const [result, messages] = await Promise.all([
    fetchPublicVoiceExperience(slug),
    buildPublicVoiceMessages(),
  ]);

  if (!result.ok) notFound();

  return (
    <PublicVoiceExperience experience={result.data} locale={locale} messages={messages} embed />
  );
}
