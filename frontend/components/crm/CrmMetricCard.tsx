import type { LucideIcon } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

type Props = {
  title: string;
  value: string | number;
  icon?: LucideIcon;
  subtext?: string;
  className?: string;
  tone?: 'default' | 'positive' | 'warning' | 'critical';
};

const TONES = {
  default: 'bg-primary/10 text-primary',
  positive: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  critical: 'bg-destructive/10 text-destructive',
} as const;

export function CrmMetricCard({ title, value, icon: Icon, subtext, className, tone = 'default' }: Props) {
  return <Card className={cn('border-border bg-card p-4 shadow-xs sm:p-5', className)}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p><p className="mt-3 break-words text-2xl font-semibold tracking-tight text-foreground">{value}</p></div>{Icon ? <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', TONES[tone])}><Icon aria-hidden="true" className="size-4" /></span> : null}</div>{subtext ? <p className="mt-2 text-xs leading-5 text-muted-foreground">{subtext}</p> : null}</Card>;
}
