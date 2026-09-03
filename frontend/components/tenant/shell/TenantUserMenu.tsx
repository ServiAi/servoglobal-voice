import { LogOut, UserRound } from 'lucide-react';

type TenantUserMenuProps = { userName: string; compact?: boolean };

export function TenantUserMenu({ userName, compact = false }: TenantUserMenuProps) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[hsl(var(--brand)/0.12)] text-[hsl(var(--brand))]">
        <UserRound aria-hidden="true" className="size-4" />
      </div>
      {!compact ? <span className="min-w-0 flex-1 truncate text-sm font-medium">{userName}</span> : null}
      <form action="/api/auth/logout" method="get">
        <button
          type="submit"
          aria-label="Cerrar sesión"
          title="Cerrar sesión"
          className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <LogOut aria-hidden="true" className="size-4" />
        </button>
      </form>
    </div>
  );
}
