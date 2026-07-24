import { Headphones, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { CrmNavigation } from './CrmNavigation';
import { CrmTenantSummary } from './CrmTenantSummary';
import { CrmUserMenu } from './CrmUserMenu';

type CrmSidebarProps = {
  collapsed: boolean;
  locale: string;
  tenantName: string;
  userName: string;
  onToggle: () => void;
};

export function CrmSidebar({ collapsed, locale, tenantName, userName, onToggle }: CrmSidebarProps) {
  return (
    <aside className={`fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] transition-[width] duration-200 lg:flex ${collapsed ? 'w-20' : 'w-64'}`}>
      <div className={`flex h-16 items-center border-b border-[hsl(var(--sidebar-border))] ${collapsed ? 'justify-center px-2' : 'gap-3 px-5'}`}>
        {!collapsed && (
          <>
            <span className="flex size-9 items-center justify-center rounded-[var(--radius-control)] bg-[hsl(var(--sidebar-accent))] text-[hsl(var(--sidebar-accent-foreground))]">
              <Headphones aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">ServiGlobal</p>
              <p className="text-xs text-[hsl(var(--sidebar-muted))]">CRM</p>
            </div>
          </>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expandir menú lateral' : 'Contraer menú lateral'}
          title={collapsed ? 'Expandir menú lateral' : 'Contraer menú lateral'}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-[hsl(var(--sidebar-muted))] hover:bg-white/5 hover:text-[hsl(var(--sidebar-foreground))]"
        >
          {collapsed ? <PanelLeftOpen aria-hidden="true" className="size-4" /> : <PanelLeftClose aria-hidden="true" className="size-4" />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-6">
        <CrmNavigation collapsed={collapsed} locale={locale} />
      </div>
      {!collapsed && (
        <div className="space-y-3 border-t border-[hsl(var(--sidebar-border))] p-3">
          <CrmTenantSummary tenantName={tenantName} />
          <CrmUserMenu userName={userName} />
        </div>
      )}
    </aside>
  );
}
