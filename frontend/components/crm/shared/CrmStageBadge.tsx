import { cn } from '@/lib/utils';
import { getStageLabel } from '../config/crm-display';

const styles: Record<string, string> = {
  new: 'border-[hsl(var(--info)/0.25)] bg-[hsl(var(--info)/0.1)] text-[hsl(var(--info))]',
  contacted: 'border-[hsl(var(--brand)/0.25)] bg-[hsl(var(--brand)/0.1)] text-[hsl(var(--brand))]',
  connected: 'border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
  qualified: 'border-[hsl(var(--brand)/0.25)] bg-[hsl(var(--brand)/0.1)] text-[hsl(var(--brand))]',
  scheduled: 'border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.12)] text-[hsl(var(--warning))]',
  won: 'border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
  lost: 'border-destructive/25 bg-destructive/10 text-destructive',
};

export function CrmStageBadge({ stageKey, stageName }: { stageKey: string; stageName?: string }) {
  return <span className={cn('inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold', styles[stageKey] ?? 'border-border bg-muted text-muted-foreground')}>{getStageLabel(stageKey, stageName)}</span>;
}
