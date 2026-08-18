'use client';

import { CalendarClock, CheckCircle2, Eye, Layers3, RotateCcw, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { VoiceExperienceVersionResponse } from '@/types/voice-experiences';
import { ActionDialog } from '../ActionDialog';

type Props = {
  versions: VoiceExperienceVersionResponse[];
  publishedVersionId: string | null;
  locale: string;
  canEdit: boolean;
  busy: boolean;
  selectedVersionId: string | null;
  onSelect: (version: VoiceExperienceVersionResponse) => void;
  onRestore: (version: VoiceExperienceVersionResponse) => void;
  onDelete: (version: VoiceExperienceVersionResponse) => void;
};

export function VersionHistoryPanel({
  versions,
  publishedVersionId,
  locale,
  canEdit,
  busy,
  selectedVersionId,
  onSelect,
  onRestore,
  onDelete,
}: Props) {
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
            {versions.map((version) => {
              const selected = selectedVersionId === version.id;
              return (
                <li
                  key={version.id}
                  className={`p-3 transition-colors ${selected ? 'bg-cyan-500/[0.07]' : ''}`}
                >
                  <button
                    type="button"
                    data-testid={`voice-version-${version.version}`}
                    className="grid w-full gap-3 rounded-lg p-2 text-left outline-none transition hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-primary/40 sm:grid-cols-[auto_1fr_auto] sm:items-center"
                    aria-pressed={selected}
                    disabled={busy}
                    onClick={() => onSelect(version)}
                  >
                    <span className="flex size-9 items-center justify-center rounded-md bg-primary/10 font-mono text-sm font-bold text-primary">
                      v{version.version}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">
                        {version.content.title}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <CalendarClock className="size-3.5" aria-hidden="true" />
                        {new Intl.DateTimeFormat(locale, {
                          dateStyle: 'medium',
                          timeStyle: 'short',
                        }).format(new Date(version.published_at))}
                        <span aria-hidden="true">·</span>
                        {version.default_locale}
                      </span>
                    </span>
                    <span className="flex items-center justify-end gap-2">
                      {publishedVersionId === version.id ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-700 dark:text-cyan-300">
                          <CheckCircle2 className="size-3.5" aria-hidden="true" />
                          {t('versions.current')}
                        </span>
                      ) : null}
                      {selected ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-primary">
                          <Eye className="size-3.5" aria-hidden="true" />
                          {t('versions.selected')}
                        </span>
                      ) : null}
                    </span>
                  </button>

                  {canEdit ? (
                    <div className="mt-2 flex flex-wrap items-center justify-end gap-2 px-2">
                      {version.delete_block_reason ? (
                        <span className="mr-auto text-xs text-muted-foreground">
                          {t(`versions.deleteReasons.${version.delete_block_reason}`)}
                        </span>
                      ) : null}
                      <ActionDialog
                        trigger={
                          <Button type="button" size="sm" variant="outline" disabled={busy}>
                            <RotateCcw className="mr-1.5 size-4" aria-hidden="true" />
                            {t('versions.restore')}
                          </Button>
                        }
                        title={t('versions.confirmRestore.title', { version: version.version })}
                        description={t('versions.confirmRestore.description')}
                        confirmLabel={t('versions.restore')}
                        cancelLabel={t('common.cancel')}
                        busy={busy}
                        onConfirm={() => onRestore(version)}
                      />
                      {version.can_delete ? (
                        <ActionDialog
                          trigger={
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              disabled={busy}
                              aria-label={t('versions.delete', { version: version.version })}
                            >
                              <Trash2 className="size-4" aria-hidden="true" />
                            </Button>
                          }
                          title={t('versions.confirmDelete.title', { version: version.version })}
                          description={t('versions.confirmDelete.description')}
                          confirmLabel={t('versions.confirmDelete.confirmLabel')}
                          cancelLabel={t('common.cancel')}
                          destructive
                          busy={busy}
                          onConfirm={() => onDelete(version)}
                        />
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
