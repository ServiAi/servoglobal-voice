import { cn } from '@/lib/utils';
import { getStatusLabel } from '../config/crm-display';

const styles: Record<string, string> = {
  open: 'border-[hsl(var(--info)/0.25)] bg-[hsl(var(--info)/0.1)] text-[hsl(var(--info))]',
  won: 'border-[hsl(var(--success)/0.25)] bg-[hsl(var(--success)/0.1)] text-[hsl(var(--success))]',
  lost: 'border-destructive/25 bg-destructive/10 text-destructive',
  unqualified: 'border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.12)] text-[hsl(var(--warning))]',
  paused: 'border-border bg-muted text-muted-foreground',
};

export function CrmStatusBadge({ status }: { status: string }) {
  return <span className={cn('inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold', styles[status] ?? 'border-border bg-muted text-muted-foreground')}>{getStatusLabel(status)}</span>;
}
