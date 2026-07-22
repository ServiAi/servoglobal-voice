import type { ReactNode } from 'react';
import { CrmSidebar } from './CrmSidebar';
import { CrmTopbar } from './CrmTopbar';

type CrmShellProps = {
  children: ReactNode;
  locale: string;
  tenantName: string;
  userName: string;
};

export function CrmShell({ children, locale, tenantName, userName }: CrmShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <CrmSidebar locale={locale} tenantName={tenantName} userName={userName} />
      <CrmTopbar locale={locale} tenantName={tenantName} userName={userName} />
      <main className="min-w-0 px-4 py-6 sm:px-6 lg:ml-64 lg:px-8 lg:py-8">
        {children}
      </main>
    </div>
  );
}
