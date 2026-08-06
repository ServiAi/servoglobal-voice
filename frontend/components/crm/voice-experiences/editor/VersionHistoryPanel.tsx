'use client';

import { CalendarClock, CheckCircle2, Layers3 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { VoiceExperienceVersionResponse } from '@/types/voice-experiences';

type Props = {
  versions: VoiceExperienceVersionResponse[];
  publishedVersionId: string | null;
  locale: string;
};

export function VersionHistoryPanel({ versions, publishedVersionId, locale }: Props) {
  const t = useTranslations('crm.voiceExperiences');
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border bg-muted/20">
        <CardTitle className="flex items-center gap-2 text-base">
          <Layers3 className="size-4 text-primary" aria-hidden="true" />
          {t('versions.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {versions.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">{t('versions.empty')}</p>
        ) : (
          <ol className="divide-y divide-border">
            {versions.map((version) => (
              <li key={version.id} className="grid gap-2 p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                <span className="flex size-9 items-center justify-center rounded-md bg-primary/10 font-mono text-sm font-bold text-primary">
                  v{version.version}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-foreground">{version.content.title}</p>
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CalendarClock className="size-3.5" aria-hidden="true" />
                    {new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
                      new Date(version.published_at)
                    )}
                    <span aria-hidden="true">·</span>
                    {version.default_locale}
                  </p>
                </div>
                {publishedVersionId === version.id ? (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-700 dark:text-cyan-300">
                    <CheckCircle2 className="size-3.5" aria-hidden="true" />
                    {t('versions.current')}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
