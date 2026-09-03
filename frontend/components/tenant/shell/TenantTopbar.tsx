'use client';

import { usePathname } from 'next/navigation';
import { Building2 } from 'lucide-react';
import { ThemeToggle } from '@/components/shared/ThemeToggle';
import { TenantMobileDrawer } from './TenantMobileDrawer';
import { TenantUserMenu } from './TenantUserMenu';
import { useTranslations } from 'next-intl';

type TenantTopbarProps = { collapsed: boolean; locale: string; tenantName: string; userName: string };

function getTitleKey(pathname: string) {
  if (pathname.includes('/crm/analytics')) return 'performance';
  if (pathname.endsWith('/dashboard')) return 'homeSummary';
  if (pathname.endsWith('/crm')) return 'crmSummary';
  if (pathname.includes('/crm/settings/integrations')) return 'integrations';
  if (pathname.includes('/crm/settings/notifications')) return 'notifications';
  if (pathname.includes('/crm/leads/')) return 'leadDetail';
  if (pathname.endsWith('/crm/leads')) return 'leads';
  if (pathname.includes('/crm/tasks')) return 'tasks';
  if (pathname.includes('/voice-ai/experiences')) return 'voiceExperiences';
  if (pathname.includes('/voice-ai/calls')) return 'voiceCalls';
  if (pathname.includes('/voice-ai/analytics')) return 'voiceAnalytics';
  if (pathname.includes('/voice-ai/telephony')) return 'voiceTelephony';
  return 'pipeline';
}

export function TenantTopbar({ collapsed, locale, tenantName, userName }: TenantTopbarProps) {
  const pathname = usePathname();
  const t = useTranslations('crm.navigation');

  return (
    <header className={`sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-background/92 px-4 backdrop-blur-md transition-[margin] duration-200 sm:px-6 ${collapsed ? 'lg:ml-20' : 'lg:ml-64'}`}>
      <TenantMobileDrawer locale={locale} tenantName={tenantName} userName={userName} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold sm:text-base">{t(getTitleKey(pathname))}</p>
        <p className="hidden truncate text-xs text-muted-foreground sm:block">ServiGlobal IA</p>
      </div>
      <div className="hidden min-w-0 items-center gap-2 rounded-[var(--radius-control)] border border-border bg-[hsl(var(--surface-subtle))] px-3 py-2 md:flex">
        <Building2 aria-hidden="true" className="size-4 shrink-0 text-[hsl(var(--brand))]" />
        <span className="max-w-40 truncate text-xs font-medium">{tenantName}</span>
      </div>
      <ThemeToggle />
      <div className="hidden lg:block">
        <TenantUserMenu userName={userName} compact />
      </div>
    </header>
  );
}
