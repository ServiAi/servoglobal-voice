'use client';

import { Archive, CircleDot, Radio, RadioTower } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/badge';
import type { VoiceExperienceStatus } from '@/types/voice-experiences';

const STATUS_STYLES: Record<VoiceExperienceStatus, string> = {
  draft: 'border-slate-400/30 bg-slate-400/10 text-slate-700 dark:text-slate-200',
  published: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
  unpublished: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  archived: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-600 dark:text-zinc-300',
};

const STATUS_ICONS = {
  draft: CircleDot,
  published: RadioTower,
  unpublished: Radio,
  archived: Archive,
} as const;

export function VoiceExperienceStatusBadge({ status }: { status: VoiceExperienceStatus }) {
  const t = useTranslations('crm.voiceExperiences');
  const Icon = STATUS_ICONS[status];
  return (
    <Badge variant="outline" className={`gap-1.5 rounded-full px-2.5 py-1 ${STATUS_STYLES[status]}`}>
      <Icon className="size-3.5" aria-hidden="true" />
      {t(`list.status.${status}`)}
    </Badge>
  );
}
