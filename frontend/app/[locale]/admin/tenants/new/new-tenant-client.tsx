'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Building2,
  Plus,
  X,
  Loader2,
  AlertCircle,
  CheckCircle2,
  User,
  Mic,
  ArrowLeft,
} from 'lucide-react';

import {
  createTenant,
  type TenantCreatePayload,
  type TenantAgent,
} from '@/lib/api/admin-tenants-client';
import { getAdminAccessRedirect } from '@/lib/auth/admin-client';

const TIMEZONES = [
  'America/Bogota',
  'America/Mexico_City',
  'America/Argentina/Buenos_Aires',
  'America/Lima',
  'America/Santiago',
  'America/New_York',
  'UTC',
];

const PROVIDERS = ['ultravox', 'twilio', 'vonage', 'plivo', 'other'];
const CHANNEL_TYPES = ['voice', 'whatsapp', 'sms', 'email'];

function EmptyAgentRow(): TenantAgent {
  return {
    id: '',
    tenant_id: '',
    name: '',
    external_provider: 'ultravox',
    external_agent_id: '',
    channel_type: 'voice',
    status: 'active',
  };
}

type NewTenantClientProps = {
  locale: string;
};

export function NewTenantClient({ locale }: NewTenantClientProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [timezone, setTimezone] = useState('America/Bogota');
  const [status, setStatus] = useState('active');

  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminRole, setAdminRole] = useState('tenant_admin');

  const [agents, setAgents] = useState<TenantAgent[]>([]);

  const slugFromName = useCallback((n: string) => {
    return n
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }, []);

  const handleNameChange = (v: string) => {
    setName(v);
    if (!slug || slug === slugFromName(name)) {
      setSlug(slugFromName(v));
    }
  };

  const addAgent = () => {
    setAgents((prev) => [...prev, EmptyAgentRow()]);
  };

  const removeAgent = (index: number) => {
    setAgents((prev) => prev.filter((_, i) => i !== index));
  };

  const updateAgent = (index: number, field: keyof TenantAgent, value: string) => {
    setAgents((prev) =>
      prev.map((a, i) => (i === index ? { ...a, [field]: value } : a))
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setLoading(true);

    const payload: TenantCreatePayload = {
      name: name.trim(),
      slug: slug.trim().toLowerCase(),
      timezone,
      status,
      admin: {
        name: adminName.trim(),
        email: adminEmail.trim().toLowerCase(),
        role: adminRole,
      },
      agents: agents
        .filter((a) => a.name.trim() && a.external_agent_id.trim())
        .map((a) => ({
          name: a.name.trim(),
          external_provider: a.external_provider.trim(),
          external_agent_id: a.external_agent_id.trim(),
          channel_type: a.channel_type || undefined,
          status: a.status || 'active',
        })),
    };

    const result = await createTenant(payload);
    setLoading(false);

    if (result.ok) {
      setSuccess(true);
      setTimeout(() => {
        router.push(`/${locale}/admin/tenants/${result.data.id}`);
      }, 1500);
    } else {
      const redirectTo = getAdminAccessRedirect(
        result.status,
        locale,
        `/${locale}/admin/tenants/new`
      );

      if (redirectTo) {
        router.push(redirectTo);
        return;
      }

      setError(result.detail);
    }
  };

  if (success) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center">
        <CheckCircle2 className="mb-4 h-12 w-12 text-emerald-600 dark:text-emerald-400" />
        <h2 className="text-xl font-semibold text-foreground">Tenant creado correctamente</h2>
        <p className="mt-2 text-sm text-muted-foreground">Redirigiendo al detalle...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8">
        <Link
          href={`/${locale}/admin/tenants`}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a tenants
        </Link>
        <h1 className="text-2xl font-semibold text-foreground sm:text-3xl">
          Nuevo tenant
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Crea una empresa, su admin inicial y agentes opcionales.
        </p>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-destructive/20 bg-destructive/10 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div>
              <p className="text-sm font-medium text-destructive">Error</p>
              <p className="text-sm text-destructive/80">{error}</p>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Empresa */}
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium text-foreground">
            <Building2 className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Empresa
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Nombre *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                placeholder="Ej: Inmobiliaria Central"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Slug *
              </label>
              <input
                type="text"
                required
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                placeholder="inmobiliaria-central"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Identificador operativo. Se genera automáticamente desde el nombre.
              </p>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Zona horaria
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Estado
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
                <option value="suspended">Suspendido</option>
              </select>
            </div>
          </div>
        </section>

        {/* Admin inicial */}
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium text-foreground">
            <User className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Admin inicial
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Nombre *
              </label>
              <input
                type="text"
                required
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                placeholder="Juan Pérez"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Email *
              </label>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                placeholder="juan@inmobiliaria.com"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                El vinculo con Auth0 sub se completa en el primer login real.
              </p>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Rol
              </label>
              <select
                value={adminRole}
                onChange={(e) => setAdminRole(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                <option value="tenant_admin">Tenant admin</option>
                <option value="tenant_analyst">Tenant analyst</option>
                <option value="tenant_agent">Tenant agent</option>
              </select>
            </div>
          </div>
        </section>

        {/* Agentes opcionales */}
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-medium text-foreground">
              <Mic className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
              Agentes (opcionales)
            </h2>
            <button
              type="button"
              onClick={addAgent}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted"
            >
              <Plus className="h-3.5 w-3.5" />
              Agregar agente
            </button>
          </div>

          {agents.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Los agentes son opcionales. Puedes agregarlos después desde el detalle del tenant.
            </p>
          )}

          <div className="space-y-6">
            {agents.map((agent, index) => (
              <div
                key={index}
                className="rounded-lg border border-border bg-muted/30 p-4"
              >
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">
                    Agente {index + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAgent(index)}
                    className="text-muted-foreground transition hover:text-destructive"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                      Nombre *
                    </label>
                    <input
                      type="text"
                      required
                      value={agent.name}
                      onChange={(e) => updateAgent(index, 'name', e.target.value)}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      placeholder="Agente Inmobiliario"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                      Provider *
                    </label>
                    <select
                      value={agent.external_provider}
                      onChange={(e) => updateAgent(index, 'external_provider', e.target.value)}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    >
                      {PROVIDERS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                      Agent ID *
                    </label>
                    <input
                      type="text"
                      required
                      value={agent.external_agent_id}
                      onChange={(e) => updateAgent(index, 'external_agent_id', e.target.value)}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                      placeholder="uv-001"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                      Canal
                    </label>
                    <select
                      value={agent.channel_type || 'voice'}
                      onChange={(e) => updateAgent(index, 'channel_type', e.target.value)}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    >
                      {CHANNEL_TYPES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                      Estado
                    </label>
                    <select
                      value={agent.status || 'active'}
                      onChange={(e) => updateAgent(index, 'status', e.target.value)}
                      className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    >
                      <option value="active">Activo</option>
                      <option value="inactive">Inactivo</option>
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Submit */}
        <div className="flex items-center justify-end gap-3">
          <Link
            href={`/${locale}/admin/tenants`}
            className="rounded-lg border border-border bg-background px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? 'Creando...' : 'Crear tenant'}
          </button>
        </div>
      </form>
    </div>
  );
}
