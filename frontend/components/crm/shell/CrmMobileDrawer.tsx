'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { Headphones, Menu, X } from 'lucide-react';
import { useState } from 'react';
import { CrmNavigation } from './CrmNavigation';
import { CrmTenantSummary } from './CrmTenantSummary';
import { CrmUserMenu } from './CrmUserMenu';

type CrmMobileDrawerProps = { locale: string; tenantName: string; userName: string };

export function CrmMobileDrawer({ locale, tenantName, userName }: CrmMobileDrawerProps) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          aria-label="Abrir navegación"
          className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] border border-border bg-card lg:hidden"
        >
          <Menu aria-hidden="true" className="size-5" />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[hsl(var(--overlay)/0.62)] backdrop-blur-[2px]" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-[min(20rem,calc(100vw-2rem))] flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] shadow-xl">
          <Dialog.Title className="sr-only">Navegación del CRM</Dialog.Title>
          <div className="flex h-16 items-center justify-between border-b border-[hsl(var(--sidebar-border))] px-4">
            <div className="flex items-center gap-3 font-semibold">
              <Headphones aria-hidden="true" className="size-5 text-[hsl(var(--sidebar-accent))]" />
              ServiGlobal CRM
            </div>
            <Dialog.Close asChild>
              <button type="button" aria-label="Cerrar navegación" className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] hover:bg-white/5">
                <X aria-hidden="true" className="size-5" />
              </button>
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-6">
            <CrmNavigation locale={locale} onNavigate={() => setOpen(false)} />
          </div>
          <div className="space-y-3 border-t border-[hsl(var(--sidebar-border))] p-3">
            <CrmTenantSummary tenantName={tenantName} />
            <CrmUserMenu userName={userName} />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
