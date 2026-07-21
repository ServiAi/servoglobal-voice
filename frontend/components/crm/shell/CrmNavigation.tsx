'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  CheckSquare2,
  KanbanSquare,
  MessageSquareMore,
  Settings,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const GROUPS = [
  {
    label: 'Operación',
    links: [
      { label: 'Pipeline', path: '/crm', icon: KanbanSquare, exact: true },
      { label: 'Leads', path: '/crm/leads', icon: Users },
      { label: 'Tareas', path: '/crm/tasks', icon: CheckSquare2 },
    ],
  },
  {
    label: 'Análisis',
    links: [
      { label: 'Rendimiento', path: '/crm/dashboard', icon: BarChart3 },
      { label: 'Métricas de voz', path: '/dashboard', icon: MessageSquareMore },
    ],
  },
  {
    label: 'Configuración',
    links: [
      { label: 'Integraciones', path: '/crm/settings/integrations', icon: Settings },
    ],
  },
] as const;

type CrmNavigationProps = {
  locale: string;
  onNavigate?: () => void;
};

export function CrmNavigation({ locale, onNavigate }: CrmNavigationProps) {
  const pathname = usePathname();

  return (
    <nav aria-label="Navegación principal del CRM" className="space-y-6">
      {GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-[0.12em] text-[hsl(var(--sidebar-muted))]">
            {group.label}
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
                    <span>{item.label}</span>
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
