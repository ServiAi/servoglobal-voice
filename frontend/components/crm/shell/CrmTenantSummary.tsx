import { Building2 } from 'lucide-react';

type CrmTenantSummaryProps = { tenantName: string };

export function CrmTenantSummary({ tenantName }: CrmTenantSummaryProps) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-[var(--radius-control)] border border-[hsl(var(--sidebar-border))] bg-white/5 p-3">
      <Building2 aria-hidden="true" className="size-4 shrink-0 text-[hsl(var(--sidebar-accent))]" />
      <div className="min-w-0">
        <p className="text-xs text-[hsl(var(--sidebar-muted))]">Tenant activo</p>
        <p className="truncate text-sm font-semibold text-[hsl(var(--sidebar-foreground))]">{tenantName}</p>
      </div>
    </div>
  );
}
