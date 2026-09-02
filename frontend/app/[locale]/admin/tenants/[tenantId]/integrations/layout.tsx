import type { ReactNode } from 'react';

export default function AdminTenantIntegrationsLayout({ children }: { children: ReactNode }) {
  return <div className="px-4 py-8 sm:px-6">{children}</div>;
}
