'use client';

import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { CrmSidebar } from './CrmSidebar';
import { CrmTopbar } from './CrmTopbar';

type CrmShellProps = {
  children: ReactNode;
  locale: string;
  tenantName: string;
  userName: string;
};

export function CrmShell({ children, locale, tenantName, userName }: CrmShellProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    setSidebarCollapsed(localStorage.getItem('serviai:crm-sidebar-collapsed') === 'true');
  }, []);

  const toggleSidebar = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      localStorage.setItem('serviai:crm-sidebar-collapsed', String(next));
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <CrmSidebar
        collapsed={sidebarCollapsed}
        locale={locale}
        tenantName={tenantName}
        userName={userName}
        onToggle={toggleSidebar}
      />
      <CrmTopbar collapsed={sidebarCollapsed} locale={locale} tenantName={tenantName} userName={userName} />
      <main className={`min-w-0 px-4 py-6 transition-[margin] duration-200 sm:px-6 lg:px-8 lg:py-8 ${sidebarCollapsed ? 'lg:ml-20' : 'lg:ml-64'}`}>
        {children}
      </main>
    </div>
  );
}
