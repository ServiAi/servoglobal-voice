'use client';

import { Archive, CircleDot, RadioTower } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/badge';
import type { AgentStatus } from '@/types/agents';

const STATUS_STYLES: Record<AgentStatus, string> = {
  draft: 'border-slate-400/30 bg-slate-400/10 text-slate-700 dark:text-slate-200',
  active: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
  archived: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-600 dark:text-zinc-300',
};

const STATUS_ICONS = {
  draft: CircleDot,
  active: RadioTower,
  archived: Archive,
} as const;

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  const t = useTranslations('crm.agentBuilder');
  const Icon = STATUS_ICONS[status];
  return (
    <Badge variant="outline" className={`gap-1.5 rounded-full px-2.5 py-1 ${STATUS_STYLES[status]}`}>
      <Icon className="size-3.5" aria-hidden="true" />
      {t(`status.${status}`)}
    </Badge>
  );
}
