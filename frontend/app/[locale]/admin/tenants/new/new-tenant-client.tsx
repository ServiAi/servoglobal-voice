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
  type TenantPlanKey,
} from '@/lib/api/admin-tenants-client';
import { getAdminAccessRedirect } from '@/lib/auth/admin-client';
import { TenantPlanFields } from '@/components/tenant-usage/TenantPlanFields';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

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
  const [planKey, setPlanKey] = useState<TenantPlanKey>('web_conversion');
  const [includedMinutes, setIncludedMinutes] = useState('2000');
  const [pricePerMinuteUsd, setPricePerMinuteUsd] = useState('0.16');

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
    const minutes = Number.parseFloat(includedMinutes);
    const price = Number.parseFloat(pricePerMinuteUsd);

    if (planKey === 'enterprise') {
      if (!Number.isFinite(minutes) || minutes < 2000) {
        setError('Enterprise requiere minimo 2000 minutos.');
        setLoading(false);
        return;
      }
      if (!Number.isFinite(price) || price < 0.14 || price > 0.15) {
        setError('Enterprise requiere precio entre 0.14 y 0.15 USD/min.');
        setLoading(false);
        return;
      }
    }

    const payload: TenantCreatePayload = {
      name: name.trim(),
      slug: slug.trim().toLowerCase(),
      timezone,
      status,
      plan: {
        plan_key: planKey,
        included_minutes: minutes,
        price_per_minute_usd: price,
      },
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
        <CheckCircle2 className="mb-4 h-12 w-12 text-emerald-500 dark:text-emerald-400" />
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Tenant creado correctamente</h2>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Redirigiendo al detalle...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <Link
              href={`/${locale}/admin/tenants`}
              className="mb-4 inline-flex items-center gap-1.5 text-sm text-zinc-500 transition hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              <ArrowLeft className="h-4 w-4" />
              Volver a tenants
            </Link>
            <h1 className="text-2xl font-semibold text-zinc-900 sm:text-3xl dark:text-zinc-100">
              Nuevo tenant
            </h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Crea una empresa, su admin inicial y agentes opcionales.
            </p>
          </div>
          <ThemeToggle />
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-300 bg-red-50 p-4 dark:border-red-700 dark:bg-red-950/30">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-500 dark:text-red-400" />
            <div>
              <p className="text-sm font-medium text-red-700 dark:text-red-300">Error</p>
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Empresa */}
        <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium text-zinc-900 dark:text-zinc-100">
            <Building2 className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Empresa
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Nombre *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                placeholder="Ej: Inmobiliaria Central"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Slug *
              </label>
              <input
                type="text"
                required
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm font-mono text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                placeholder="inmobiliaria-central"
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
                Identificador operativo. Se genera automáticamente desde el nombre.
              </p>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Zona horaria
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Estado
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
              >
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
                <option value="suspended">Suspendido</option>
              </select>
            </div>
          </div>
        </section>

        {/* Plan comercial */}
        <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium text-zinc-900 dark:text-zinc-100">
            <Building2 className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Plan comercial
          </h2>
          <TenantPlanFields
            planKey={planKey}
            includedMinutes={includedMinutes}
            pricePerMinuteUsd={pricePerMinuteUsd}
            disabled={loading}
            onPlanKeyChange={setPlanKey}
            onIncludedMinutesChange={setIncludedMinutes}
            onPricePerMinuteUsdChange={setPricePerMinuteUsd}
          />
        </section>

        {/* Admin inicial */}
        <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-medium text-zinc-900 dark:text-zinc-100">
            <User className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Admin inicial
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Nombre *
              </label>
              <input
                type="text"
                required
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                placeholder="Juan Pérez"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Email *
              </label>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                placeholder="juan@inmobiliaria.com"
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
                El vinculo con Auth0 sub se completa en el primer login real.
              </p>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Rol
              </label>
              <select
                value={adminRole}
                onChange={(e) => setAdminRole(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
              >
                <option value="tenant_admin">Tenant admin</option>
                <option value="tenant_analyst">Tenant analyst</option>
                <option value="tenant_agent">Tenant agent</option>
              </select>
            </div>
          </div>
        </section>

        {/* Agentes opcionales */}
        <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-700 dark:bg-zinc-900">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-900 dark:text-zinc-100">
              <Mic className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
              Agentes (opcionales)
            </h2>
            <button
              type="button"
              onClick={addAgent}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-600 transition hover:border-cyan-500 hover:text-cyan-600 dark:border-zinc-600 dark:text-zinc-300 dark:hover:border-cyan-500 dark:hover:text-cyan-400"
            >
              <Plus className="h-3.5 w-3.5" />
              Agregar agente
            </button>
          </div>

          {agents.length === 0 && (
            <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
              Los agentes son opcionales. Puedes agregarlos después desde el detalle del tenant.
            </p>
          )}

          <div className="space-y-6">
            {agents.map((agent, index) => (
              <div
                key={index}
                className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800"
              >
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Agente {index + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAgent(index)}
                    className="text-zinc-500 transition hover:text-red-600 dark:text-zinc-500 dark:hover:text-red-400"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="mb-1.5 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Nombre *
                    </label>
                    <input
                      type="text"
                      required
                      value={agent.name}
                      onChange={(e) => updateAgent(index, 'name', e.target.value)}
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                      placeholder="Agente Inmobiliario"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Provider *
                    </label>
                    <select
                      value={agent.external_provider}
                      onChange={(e) => updateAgent(index, 'external_provider', e.target.value)}
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                    >
                      {PROVIDERS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Agent ID *
                    </label>
                    <input
                      type="text"
                      required
                      value={agent.external_agent_id}
                      onChange={(e) => updateAgent(index, 'external_agent_id', e.target.value)}
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm font-mono text-zinc-900 placeholder:text-zinc-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                      placeholder="uv-001"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Canal
                    </label>
                    <select
                      value={agent.channel_type || 'voice'}
                      onChange={(e) => updateAgent(index, 'channel_type', e.target.value)}
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                    >
                      {CHANNEL_TYPES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      Estado
                    </label>
                    <select
                      value={agent.status || 'active'}
                      onChange={(e) => updateAgent(index, 'status', e.target.value)}
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
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
            className="rounded-lg border border-zinc-300 px-5 py-2.5 text-sm font-medium text-zinc-600 transition hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Cancelar
          </Link>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-700 disabled:opacity-50 dark:bg-cyan-500 dark:hover:bg-cyan-400"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? 'Creando...' : 'Crear tenant'}
          </button>
        </div>
      </form>
    </div>
  );
}