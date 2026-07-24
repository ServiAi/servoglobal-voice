'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  CheckSquare2,
  Gauge,
  Settings,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

const GROUPS = [
  {
    label: 'operation',
    links: [
      { label: 'home', path: '/crm', icon: Gauge, exact: true },
      { label: 'leads', path: '/crm/leads', icon: Users },
      { label: 'tasks', path: '/crm/tasks', icon: CheckSquare2 },
    ],
  },
  {
    label: 'analysis',
    links: [
      { label: 'performance', path: '/crm/dashboard', icon: BarChart3 },
    ],
  },
  {
    label: 'configuration',
    links: [
      { label: 'integrations', path: '/crm/settings/integrations', icon: Settings },
    ],
  },
] as const;

type CrmNavigationProps = {
  locale: string;
  onNavigate?: () => void;
};

export function CrmNavigation({ locale, onNavigate }: CrmNavigationProps) {
  const pathname = usePathname();
  const t = useTranslations('crm.navigation');

  return (
    <nav aria-label={t('ariaLabel')} className="space-y-6">
      {GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-[0.12em] text-[hsl(var(--sidebar-muted))]">
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
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex min-h-10 items-center gap-3 rounded-[var(--radius-control)] border-l-2 px-3 text-sm font-medium transition-colors',
                      active
                        ? 'border-[hsl(var(--sidebar-accent))] bg-[hsl(var(--sidebar-accent)/0.16)] text-[hsl(var(--sidebar-foreground))]'
                        : 'border-transparent text-[hsl(var(--sidebar-muted))] hover:bg-white/5 hover:text-[hsl(var(--sidebar-foreground))]'
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                    <span>{t(item.label)}</span>
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
