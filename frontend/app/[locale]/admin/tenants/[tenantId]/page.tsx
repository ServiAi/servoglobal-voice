'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Building2,
  Users,
  Mic,
  ArrowRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  Plus,
  Pencil,
  Save,
  Copy,
  ExternalLink,
  Shield,
  Mail,
  User,
  Globe,
} from 'lucide-react';

import {
  fetchTenantDetail,
  updateTenant,
  addTenantMembership,
  addTenantAgent,
  type TenantDetail,
  type TenantMembership,
  type TenantAgent,
  type FetchResult,
} from '@/lib/api/tenants';
import { getAccessToken } from '@/lib/auth/server';

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        Activo
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 px-2.5 py-0.5 text-xs font-medium text-zinc-400">
      <Clock className="h-3 w-3" />
      {status}
    </span>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center">
      <AlertCircle className="mx-auto mb-2 h-8 w-8 text-red-400" />
      <p className="text-sm text-red-300">{message}</p>
    </div>
  );
}

function CopyableField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-sm text-zinc-300">{value}</span>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded p-1 text-zinc-600 transition hover:text-zinc-300"
        title="Copiar"
      >
        {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

export default function TenantDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [tenant, setTenant] = useState<TenantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editTimezone, setEditTimezone] = useState('America/Bogota');
  const [editStatus, setEditStatus] = useState('active');
  const [saving, setSaving] = useState(false);

  // Add membership state
  const [showAddMembership, setShowAddMembership] = useState(false);
  const [membershipEmail, setMembershipEmail] = useState('');
  const [membershipRole, setMembershipRole] = useState('tenant_analyst');
  const [membershipError, setMembershipError] = useState<string | null>(null);

  // Add agent state
  const [showAddAgent, setShowAddAgent] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [agentProvider, setAgentProvider] = useState('ultravox');
  const [agentAgentId, setAgentAgentId] = useState('');
  const [agentChannel, setAgentChannel] = useState('voice');
  const [agentError, setAgentError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = await getAccessToken();
    if (!token) {
      router.push('/api/auth/login?returnTo=/es/admin/tenants');
      return;
    }
    const result = await fetchTenantDetail(token, tenantId);
    if (result.ok) {
      setTenant(result.data);
      setEditName(result.data.name);
      setEditTimezone(result.data.timezone);
      setEditStatus(result.data.status);
    } else {
      setError(result.detail);
    }
    setLoading(false);
  }, [router, tenantId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSaveEdit = async () => {
    const token = await getAccessToken();
    if (!token) return;
    setSaving(true);
    const result = await updateTenant(token, tenantId, {
      name: editName,
      timezone: editTimezone,
      status: editStatus,
    });
    setSaving(false);
    if (result.ok) {
      setTenant(result.data);
      setEditing(false);
    } else {
      setError(result.detail);
    }
  };

  const handleAddMembership = async () => {
    const token = await getAccessToken();
    if (!token) return;
    setMembershipError(null);
    const result = await addTenantMembership(token, tenantId, {
      email: membershipEmail.trim().toLowerCase(),
      role: membershipRole,
    });
    if (result.ok) {
      setTenant((prev) =>
        prev ? { ...prev, memberships: [...prev.memberships, result.data] } : prev
      );
      setShowAddMembership(false);
      setMembershipEmail('');
      load();
    } else {
      setMembershipError(result.detail);
    }
  };

  const handleAddAgent = async () => {
    const token = await getAccessToken();
    if (!token) return;
    setAgentError(null);
    const result = await addTenantAgent(token, tenantId, {
      name: agentName.trim(),
      external_provider: agentProvider.trim(),
      external_agent_id: agentAgentId.trim(),
      channel_type: agentChannel || undefined,
    });
    if (result.ok) {
      setTenant((prev) =>
        prev ? { ...prev, agents: [...prev.agents, result.data] } : prev
      );
      setShowAddAgent(false);
      setAgentName('');
      setAgentAgentId('');
      load();
    } else {
      setAgentError(result.detail);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (error || !tenant) {
    return <ErrorState message={error ?? 'Tenant no encontrado'} />;
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <Link
            href="/es/admin/tenants"
            className="mb-3 inline-block text-sm text-zinc-500 transition hover:text-zinc-300"
          >
            \u2190 Volver a tenants
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-zinc-100 sm:text-3xl">
                {tenant.name}
              </h1>
              <p className="text-sm text-zinc-500 font-mono">{tenant.slug}</p>
            </div>
          </div>
        </div>
        <StatusBadge status={tenant.status} />
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/20 bg-red-500/5 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
            <div>
              <p className="text-sm font-medium text-red-300">Error</p>
              <p className="text-sm text-red-400/80">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Integration Info */}
      <section className="mb-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase text-cyan-400">
          <ExternalLink className="h-4 w-4" />
          Identificador operativo
        </h2>
        <p className="mb-3 text-xs text-zinc-400">
          Usa <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-cyan-300">{tenant.slug}</code> como identificador operativo en metadata de llamadas y webhooks.
        </p>
        <div className="rounded-lg bg-zinc-950 p-3 font-mono text-sm text-zinc-300">
          {`{`}
          {'\n'}  <span className="text-cyan-400">"tenant_slug"</span>: <span className="text-emerald-400">"{tenant.slug}"</span>
          {'\n'}{`}}`}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Tenant Data */}
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200">
              <Building2 className="h-5 w-5 text-cyan-400" />
              Datos del tenant
            </h2>
            {!editing ? (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-lg border border-zinc-700 p-1.5 text-zinc-500 transition hover:border-cyan-500/50 hover:text-cyan-400"
                title="Editar"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={saving}
                className="rounded-lg border border-emerald-500/30 p-1.5 text-emerald-400 transition hover:bg-emerald-500/10"
                title="Guardar"
              >
                <Save className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500">ID</label>
              <CopyableField value={tenant.id} label="Tenant ID" />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500">Slug</label>
              <CopyableField value={tenant.slug} label="Tenant slug" />
            </div>

            {editing ? (
              <>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500">Nombre</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500">Zona horaria</label>
                  <select
                    value={editTimezone}
                    onChange={(e) => setEditTimezone(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    <option value="America/Bogota">America/Bogota</option>
                    <option value="America/Mexico_City">America/Mexico_City</option>
                    <option value="America/Argentina/Buenos_Aires">America/Argentina/Buenos_Aires</option>
                    <option value="America/Lima">America/Lima</option>
                    <option value="America/Santiago">America/Santiago</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="UTC">UTC</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500">Estado</label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    <option value="active">Activo</option>
                    <option value="inactive">Inactivo</option>
                    <option value="suspended">Suspendido</option>
                  </select>
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setEditing(false)}
                    className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition hover:bg-zinc-800"
                  >
                    Cancelar
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Nombre</span>
                  <span className="text-sm text-zinc-200">{tenant.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Zona horaria</span>
                  <span className="flex items-center gap-1 text-sm text-zinc-300">
                    <Globe className="h-3.5 w-3.5 text-zinc-600" />
                    {tenant.timezone}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Ready for calls</span>
                  {tenant.is_ready_for_calls ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      S\u00ed
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 px-2 py-0.5 text-xs font-medium text-zinc-500">
                      <Clock className="h-3 w-3" />
                      No
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </section>

        {/* Quick Stats */}
        <section className="space-y-4">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-400">
              <Users className="h-4 w-4" />
              Membres\u00edas
            </h3>
            <p className="text-2xl font-semibold text-zinc-100">{tenant.memberships.length}</p>
            <p className="text-xs text-zinc-600">usuarios conectados</p>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-400">
              <Mic className="h-4 w-4" />
              Agentes
            </h3>
            <p className="text-2xl font-semibold text-zinc-100">{tenant.agents.length}</p>
            <p className="text-xs text-zinc-600">agentes configurados</p>
          </div>
        </section>
      </div>

      {/* Memberships Section */}
      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200">
            <Users className="h-5 w-5 text-cyan-400" />
            Membres\u00edas
          </h2>
          <button
            type="button"
            onClick={() => setShowAddMembership(!showAddMembership)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-cyan-500/50 hover:text-cyan-400"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar membres\u00eda
          </button>
        </div>

        {showAddMembership && (
          <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950/50 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-zinc-500">Email del usuario *</label>
                <input
                  type="email"
                  value={membershipEmail}
                  onChange={(e) => setMembershipEmail(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="usuario@empresa.com"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Rol</label>
                <select
                  value={membershipRole}
                  onChange={(e) => setMembershipRole(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                >
                  <option value="tenant_admin">Tenant admin</option>
                  <option value="tenant_analyst">Tenant analyst</option>
                  <option value="tenant_agent">Tenant agent</option>
                </select>
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={handleAddMembership}
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-cyan-500"
                >
                  Agregar
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddMembership(false)}
                  className="rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-400 transition hover:bg-zinc-800"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {membershipError && (
              <p className="mt-2 text-xs text-red-400">{membershipError}</p>
            )}
          </div>
        )}

        {tenant.memberships.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-600">Sin membres\u00edas</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                  <th className="pb-2 pr-4 font-medium">Email</th>
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Rol</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.memberships.map((m) => (
                  <tr key={m.id} className="border-b border-zinc-800/50">
                    <td className="py-2.5 pr-4 text-zinc-300">{m.user_email || <span className="text-zinc-600">—</span>}</td>
                    <td className="py-2.5 pr-4 text-zinc-300">{m.user_name || <span className="text-zinc-600">—</span>}</td>
                    <td className="py-2.5 pr-4 text-zinc-400">{m.role}</td>
                    <td className="py-2.5">
                      <StatusBadge status={m.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Agents Section */}
      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200">
            <Mic className="h-5 w-5 text-cyan-400" />
            Agentes
          </h2>
          <button
            type="button"
            onClick={() => setShowAddAgent(!showAddAgent)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-cyan-500/50 hover:text-cyan-400"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar agente
          </button>
        </div>

        {showAddAgent && (
          <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950/50 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Nombre *</label>
                <input
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="Agente Inmobiliario"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Provider *</label>
                <input
                  type="text"
                  value={agentProvider}
                  onChange={(e) => setAgentProvider(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Agent ID *</label>
                <input
                  type="text"
                  value={agentAgentId}
                  onChange={(e) => setAgentAgentId(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="uv-001"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">Canal</label>
                <select
                  value={agentChannel}
                  onChange={(e) => setAgentChannel(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                >
                  <option value="voice">voice</option>
                  <option value="whatsapp">whatsapp</option>
                  <option value="sms">sms</option>
                  <option value="email">email</option>
                </select>
              </div>
              <div className="flex items-end gap-2 sm:col-span-2">
                <button
                  type="button"
                  onClick={handleAddAgent}
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-cyan-500"
                >
                  Agregar
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddAgent(false)}
                  className="rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-400 transition hover:bg-zinc-800"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {agentError && (
              <p className="mt-2 text-xs text-red-400">{agentError}</p>
            )}
          </div>
        )}

        {tenant.agents.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-600">
            Sin agentes. Configura al menos uno para estar listo para llamadas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Provider</th>
                  <th className="pb-2 pr-4 font-medium">Agent ID</th>
                  <th className="pb-2 pr-4 font-medium">Canal</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.agents.map((a) => (
                  <tr key={a.id} className="border-b border-zinc-800/50">
                    <td className="py-2.5 pr-4 text-zinc-300">{a.name}</td>
                    <td className="py-2.5 pr-4 text-zinc-400">{a.external_provider}</td>
                    <td className="py-2.5 pr-4 font-mono text-zinc-300">{a.external_agent_id}</td>
                    <td className="py-2.5 pr-4 text-zinc-400">{a.channel_type || '—'}</td>
                    <td className="py-2.5">
                      <StatusBadge status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
