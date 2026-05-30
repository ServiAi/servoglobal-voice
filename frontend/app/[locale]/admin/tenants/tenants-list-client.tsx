'use client';

import Link from 'next/link';
import {
  Building2,
  Plus,
  Users,
  Mic,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Clock,
  LogOut,
  ArrowLeft,
} from 'lucide-react';

import { type TenantListItem } from '@/lib/api/tenants';

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        Activo
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
      <Clock className="h-3 w-3" />
      {status}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 py-20 text-center">
      <Building2 className="mb-4 h-10 w-10 text-muted-foreground/60" />
      <h3 className="text-lg font-medium text-foreground">Sin tenants</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        No hay tenants registrados. Crea el primero.
      </p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-center">
      <AlertCircle className="mx-auto mb-2 h-8 w-8 text-destructive" />
      <p className="text-sm text-destructive">{message}</p>
    </div>
  );
}

type TenantsListClientProps = {
  locale: string;
  initialTenants: TenantListItem[];
  initialError?: string | null;
};

export function TenantsListClient({
  locale,
  initialTenants,
  initialError = null,
}: TenantsListClientProps) {
  const tenants = initialTenants;
  const error = initialError;

  if (error) {
    return <ErrorState message={error} />;
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-cyan-600 dark:text-cyan-400">
            Admin
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-foreground sm:text-3xl">
            Tenants
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Gestión de empresas y accesos multitenant
          </p>
        </div>
        <div className="flex items-center gap-3">
          <form action="/api/auth/logout" method="get">
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
            >
              <LogOut className="h-4 w-4" />
              Cerrar sesión
            </button>
          </form>
          <Link
            href={`/${locale}/admin/tenants/new`}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500"
          >
            <Plus className="h-4 w-4" />
            Nuevo tenant
          </Link>
        </div>
      </div>

      {/* Back link */}
      <div className="mb-6">
        <Link
          href={`/${locale}/dashboard`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver al dashboard
        </Link>
      </div>

      {/* List */}
      {tenants.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {tenants.map((t) => (
            <TenantCard key={t.id} tenant={t} locale={locale} />
          ))}
        </div>
      )}
    </div>
  );
}

function TenantCard({
  tenant,
  locale,
}: {
  tenant: TenantListItem;
  locale: string;
}) {
  return (
    <Link
      href={`/${locale}/admin/tenants/${tenant.id}`}
      className="group block rounded-xl border border-border bg-card p-5 transition hover:border-cyan-500/30 hover:bg-muted/50"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:bg-cyan-500/10 group-hover:text-cyan-600 dark:group-hover:text-cyan-400">
            <Building2 className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-medium text-foreground group-hover:text-cyan-600 dark:group-hover:text-cyan-400">
              {tenant.name}
            </h3>
            <p className="text-xs text-muted-foreground font-mono">{tenant.slug}</p>
          </div>
        </div>
        <StatusBadge status={tenant.status} />
      </div>

      <div className="mt-4 flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Users className="h-3.5 w-3.5" />
          {tenant.id}
        </span>
        <span className="flex items-center gap-1">
          <Mic className="h-3.5 w-3.5" />
          {tenant.timezone}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-end text-xs text-muted-foreground group-hover:text-cyan-600 dark:group-hover:text-cyan-400">
        Ver detalle
        <ArrowRight className="ml-1 h-3 w-3 transition-transform group-hover:translate-x-1" />
      </div>
    </Link>
  );
}
