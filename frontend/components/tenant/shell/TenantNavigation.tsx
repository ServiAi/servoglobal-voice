'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  AudioLines,
  BarChart3,
  BellRing,
  Calendar,
  CheckSquare2,
  Gauge,
  LayoutDashboard,
  PhoneCall,
  RadioTower,
  Settings,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

const GROUPS = [
  {
    label: 'homeGroup',
    links: [
      { label: 'homeSummary', path: '/dashboard', icon: LayoutDashboard, exact: true },
    ],
  },
  {
    label: 'crmGroup',
    links: [
      { label: 'crmSummary', path: '/crm', icon: Gauge, exact: true },
      { label: 'leads', path: '/crm/leads', icon: Users },
      { label: 'agenda', path: '/agenda', icon: Calendar },
      { label: 'tasks', path: '/crm/tasks', icon: CheckSquare2 },
      { label: 'performance', path: '/crm/analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'voiceGroup',
    links: [
      { label: 'voiceExperiences', path: '/voice-ai/experiences', icon: AudioLines },
      { label: 'voiceCalls', path: '/voice-ai/calls', icon: PhoneCall },
      { label: 'voiceAnalytics', path: '/voice-ai/analytics', icon: BarChart3 },
      { label: 'voiceTelephony', path: '/voice-ai/telephony', icon: RadioTower },
    ],
  },
  {
    label: 'automationGroup',
    links: [
      { label: 'notifications', path: '/automations/notifications', icon: BellRing },
    ],
  },
  {
    label: 'integrationsGroup',
    links: [
      { label: 'integrations', path: '/integrations', icon: Settings },
    ],
  },
] as const;

type TenantNavigationProps = {
  collapsed?: boolean;
  locale: string;
  onNavigate?: () => void;
};

export function TenantNavigation({ collapsed = false, locale, onNavigate }: TenantNavigationProps) {
  const pathname = usePathname();
  const t = useTranslations('crm.navigation');

  return (
    <nav aria-label={t('ariaLabel')} className="space-y-6">
      {GROUPS.map((group) => (
        <div key={group.label}>
          <p className={collapsed ? 'sr-only' : 'mb-2 px-3 text-xs font-semibold uppercase tracking-[0.12em] text-[hsl(var(--sidebar-muted))]'}>
            {t(group.label)}
          </p>
          <ul className="space-y-1">
            {group.links.map((item) => {
              const href = `/${locale}${item.path}`;
              const active = 'exact' in item && item.exact
                ? pathname === href
                : pathname === href || pathname.startsWith(`${href}/`);
              const Icon = item.icon;

              return (
                <li key={item.path}>
                  <Link
                    href={href}
                    onClick={onNavigate}
                    title={collapsed ? t(item.label) : undefined}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex min-h-10 items-center gap-3 rounded-[var(--radius-control)] border-l-2 px-3 text-sm font-medium transition-colors',
                      collapsed && 'justify-center px-0',
                      active
                        ? 'border-[hsl(var(--sidebar-accent))] bg-[hsl(var(--sidebar-accent)/0.16)] text-[hsl(var(--sidebar-foreground))]'
                        : 'border-transparent text-[hsl(var(--sidebar-muted))] hover:bg-white/5 hover:text-[hsl(var(--sidebar-foreground))]'
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                    <span className={collapsed ? 'sr-only' : undefined}>{t(item.label)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
