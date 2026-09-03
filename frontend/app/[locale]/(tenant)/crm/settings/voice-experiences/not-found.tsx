'use client';

import { useLocale, useTranslations } from 'next-intl';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function VoiceExperienceNotFound() {
  const t = useTranslations('crm.voiceExperiences');
  const locale = useLocale();
  return (
    <div className="rounded-xl border border-slate-200 bg-card p-8 text-center shadow-sm">
      <h1 className="text-2xl font-bold">{t('notFound.title')}</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{t('notFound.description')}</p>
      <Button asChild className="mt-6">
        <Link href={`/${locale}/crm/settings/voice-experiences`}>{t('notFound.back')}</Link>
      </Button>
    </div>
  );
}
