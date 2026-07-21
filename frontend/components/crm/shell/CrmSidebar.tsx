import { Headphones } from 'lucide-react';
import { CrmNavigation } from './CrmNavigation';
import { CrmTenantSummary } from './CrmTenantSummary';
import { CrmUserMenu } from './CrmUserMenu';

type CrmSidebarProps = { locale: string; tenantName: string; userName: string };

export function CrmSidebar({ locale, tenantName, userName }: CrmSidebarProps) {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] lg:flex">
      <div className="flex h-16 items-center gap-3 border-b border-[hsl(var(--sidebar-border))] px-5">
        <span className="flex size-9 items-center justify-center rounded-[var(--radius-control)] bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))]">
          <Headphones aria-hidden="true" className="size-5" />
        </span>
        <div>
          <p className="text-sm font-semibold">ServiGlobal</p>
          <p className="text-xs text-[hsl(var(--sidebar-muted))]">CRM</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-6">
        <CrmNavigation locale={locale} />
      </div>
      <div className="space-y-3 border-t border-[hsl(var(--sidebar-border))] p-3">
        <CrmTenantSummary tenantName={tenantName} />
        <CrmUserMenu userName={userName} />
      </div>
    </aside>
  );
}
