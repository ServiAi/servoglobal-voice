'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Globe, LayoutDashboard, Users, CheckSquare, LogOut, Phone } from 'lucide-react';
import { ThemeToggle } from '../shared/ThemeToggle';

type CrmHeaderProps = {
  locale: string;
  tenantName: string;
  userName: string;
};

export function CrmHeader({ locale, tenantName, userName }: CrmHeaderProps) {
  const pathname = usePathname();

  const NAV_LINKS = [
    {
      name: 'Panel CRM / Pipeline',
      href: `/${locale}/crm`,
      icon: LayoutDashboard,
      active: pathname === `/${locale}/crm`,
    },
    {
      name: 'Listado de Leads',
      href: `/${locale}/crm/leads`,
      icon: Users,
      active: pathname.startsWith(`/${locale}/crm/leads`),
    },
    {
      name: 'Tareas',
      href: `/${locale}/crm/tasks`,
      icon: CheckSquare,
      active: pathname === `/${locale}/crm/tasks`,
    },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-card/85 backdrop-blur-md transition-colors duration-300">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-6">
        {/* Left Side: Logo */}
        <div className="flex items-center gap-6">
          <Link href={`/${locale}/crm`} className="flex items-center gap-2 group">
            <div className="relative size-9 rounded-lg bg-gradient-to-tr from-violet-600 to-indigo-500 flex items-center justify-center overflow-hidden shadow-md shadow-violet-500/20 transform group-hover:scale-105 transition-all">
              <Globe className="absolute size-5 text-white/30 animate-spin-slow" strokeWidth={1.5} />
              <Phone className="absolute size-4 text-white z-10" strokeWidth={2.5} />
            </div>
            <span className="text-lg font-bold tracking-tight text-foreground transition-colors flex items-center gap-1">
              ServiGlobal <span className="text-violet-500 font-extrabold">CRM</span>
            </span>
          </Link>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const Icon = link.icon;
              return (
                <Link
                  key={link.name}
                  href={link.href}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200',
                    link.active
                      ? 'bg-violet-500/10 text-violet-500 dark:text-violet-400'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {link.name}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right Side: Profile info, theme toggle, return to calls, logout */}
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex flex-col items-end border-r border-border pr-4 text-right">
            <span className="text-xs font-semibold text-foreground max-w-[150px] truncate">
              {tenantName}
            </span>
            <span className="text-[10px] text-muted-foreground max-w-[150px] truncate">
              {userName}
            </span>
          </div>

          {/* Return to Call Analytics Dashboard */}
          <Link
            href={`/${locale}/dashboard`}
            className="inline-flex h-9 items-center justify-center rounded-md border border-border bg-card px-3 text-xs font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
          >
            Métricas de Voz
          </Link>

          <ThemeToggle />

          <form action="/api/auth/logout" method="get">
            <button
              type="submit"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
              title="Cerrar sesión"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
