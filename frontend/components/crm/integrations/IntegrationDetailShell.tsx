import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

type Props = {
  locale: string;
  integrationsLabel: string;
  name: string;
  description: string;
  children: ReactNode;
};

export function IntegrationDetailShell({ locale, integrationsLabel, name, description, children }: Props) {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
        <Link href={`/${locale}/crm/settings/integrations`} className="rounded-sm outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">{integrationsLabel}</Link>
        <ChevronRight className="size-4" aria-hidden="true" />
        <span aria-current="page" className="font-medium text-foreground">{name}</span>
      </nav>
      <header className="border-l-4 border-primary pl-4">
        <h1 className="text-2xl font-bold text-foreground">{name}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
      </header>
      {children}
    </div>
  );
}
