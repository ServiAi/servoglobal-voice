'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Building2,
  Users,
  Mic,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  Plus,
  Pencil,
  Save,
  Copy,
  ExternalLink,
  Globe,
  Trash2,
  X,
  ArrowLeft,
} from 'lucide-react';

import {
  type TenantDetail,
} from '@/lib/api/tenants';
import {
  addTenantAgent,
  addTenantMembership,
  deleteTenant,
  fetchTenantDetail,
  updateTenant,
} from '@/lib/api/admin-tenants-client';
import { getAdminAccessRedirect } from '@/lib/auth/admin-client';

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

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-center">
      <AlertCircle className="mx-auto mb-2 h-8 w-8 text-destructive" />
      <p className="text-sm text-destructive">{message}</p>
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
      <span className="font-mono text-sm text-foreground">{value}</span>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded p-1 text-muted-foreground transition hover:text-foreground"
        title={`Copiar ${label}`}
      >
        {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

function generateTenantDeleteCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const values = new Uint32Array(8);

  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(values);
  } else {
    for (let i = 0; i < values.length; i += 1) {
      values[i] = Math.floor(Math.random() * alphabet.length);
    }
  }

  const characters = Array.from(values, (value) => alphabet[value % alphabet.length]);
  return `${characters.slice(0, 4).join('')}-${characters.slice(4).join('')}`;
}

type TenantDetailClientProps = {
  locale: string;
  tenantId: string;
  initialTenant: TenantDetail | null;
  initialError?: string | null;
};

export function TenantDetailClient({
  locale,
  tenantId,
  initialTenant,
  initialError = null,
}: TenantDetailClientProps) {
  const router = useRouter();

  const [tenant, setTenant] = useState<TenantDetail | null>(initialTenant);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(initialTenant?.name ?? '');
  const [editTimezone, setEditTimezone] = useState(initialTenant?.timezone ?? 'America/Bogota');
  const [editStatus, setEditStatus] = useState(initialTenant?.status ?? 'active');
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

  // Delete state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteCode, setDeleteCode] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const deleteReady = deleteConfirmation.trim() === deleteCode;

  const redirectOnAccessFailure = useCallback(
    (status: number) => {
      const redirectTo = getAdminAccessRedirect(
        status,
        locale,
        `/${locale}/admin/tenants/${tenantId}`
      );

      if (redirectTo) {
        router.push(redirectTo);
        return true;
      }

      return false;
    },
    [locale, router, tenantId]
  );

  const load = useCallback(async () => {
    setLoading(true);
    const result = await fetchTenantDetail(tenantId);
    if (result.ok) {
      setTenant(result.data);
      setEditName(result.data.name);
      setEditTimezone(result.data.timezone);
      setEditStatus(result.data.status);
      setError(null);
    } else if (!redirectOnAccessFailure(result.status)) {
      setError(result.detail);
    }
    setLoading(false);
  }, [redirectOnAccessFailure, tenantId]);

  const handleSaveEdit = async () => {
    setSaving(true);
    const result = await updateTenant(tenantId, {
      name: editName,
      timezone: editTimezone,
      status: editStatus,
    });
    setSaving(false);
    if (result.ok) {
      setTenant(result.data);
      setEditing(false);
    } else if (!redirectOnAccessFailure(result.status)) {
      setError(result.detail);
    }
  };

  const handleAddMembership = async () => {
    setMembershipError(null);
    const result = await addTenantMembership(tenantId, {
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
    } else if (!redirectOnAccessFailure(result.status)) {
      setMembershipError(result.detail);
    }
  };

  const handleAddAgent = async () => {
    setAgentError(null);
    const result = await addTenantAgent(tenantId, {
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
    } else if (!redirectOnAccessFailure(result.status)) {
      setAgentError(result.detail);
    }
  };

  const handleOpenDeleteModal = () => {
    setDeleteCode(generateTenantDeleteCode());
    setDeleteConfirmation('');
    setDeleteError(null);
    setDeleteModalOpen(true);
  };

  const handleCloseDeleteModal = () => {
    if (deleting) {
      return;
    }
    setDeleteModalOpen(false);
    setDeleteConfirmation('');
    setDeleteError(null);
  };

  const handleDeleteTenant = async () => {
    if (!deleteReady || deleting) {
      return;
    }

    setDeleting(true);
    setDeleteError(null);
    const result = await deleteTenant(tenantId);
    setDeleting(false);

    if (result.ok) {
      setDeleteModalOpen(false);
      router.push(`/${locale}/admin/tenants`);
      router.refresh();
    } else if (!redirectOnAccessFailure(result.status)) {
      setDeleteError(result.detail);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
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
            href={`/${locale}/admin/tenants`}
            className="mb-3 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a tenants
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-foreground sm:text-3xl">
                {tenant.name}
              </h1>
              <p className="text-sm text-muted-foreground font-mono">{tenant.slug}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={tenant.status} />
          <button
            type="button"
            onClick={handleOpenDeleteModal}
            className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 px-3 py-1.5 text-xs font-medium text-destructive transition hover:bg-destructive/10"
            title="Borrar tenant"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Borrar
          </button>
        </div>
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

      {/* Integration Info */}
      <section className="mb-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase text-cyan-600 dark:text-cyan-400">
          <ExternalLink className="h-4 w-4" />
          Identificador operativo
        </h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Usa <code className="rounded bg-muted px-1.5 py-0.5 text-cyan-600 dark:text-cyan-400">{tenant.slug}</code> como identificador operativo en metadata de llamadas y webhooks.
        </p>
        <pre className="rounded-lg bg-background border border-border p-3 font-mono text-sm text-foreground overflow-auto">
          {JSON.stringify({ tenant_slug: tenant.slug }, null, 2)}
        </pre>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Tenant Data */}
        <section className="rounded-xl border border-border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-medium text-foreground">
              <Building2 className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
              Datos del tenant
            </h2>
            {!editing ? (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-lg border border-border bg-background p-1.5 text-muted-foreground transition hover:border-cyan-500/50 hover:text-cyan-600 dark:hover:text-cyan-400"
                title="Editar"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={saving}
                className="rounded-lg border border-emerald-500/30 p-1.5 text-emerald-600 dark:text-emerald-400 transition hover:bg-emerald-500/10"
                title="Guardar"
              >
                <Save className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">ID</label>
              <CopyableField value={tenant.id} label="Tenant ID" />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Slug</label>
              <CopyableField value={tenant.slug} label="Tenant slug" />
            </div>

            {editing ? (
              <>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Nombre</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Zona horaria</label>
                  <select
                    value={editTimezone}
                    onChange={(e) => setEditTimezone(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
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
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Estado</label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
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
                    className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition hover:bg-muted"
                  >
                    Cancelar
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Nombre</span>
                  <span className="text-sm text-foreground">{tenant.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Zona horaria</span>
                  <span className="flex items-center gap-1 text-sm text-foreground">
                    <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                    {tenant.timezone}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Ready for calls</span>
                  {tenant.is_ready_for_calls ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      Sí
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
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
          <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Users className="h-4 w-4" />
              Membresías
            </h3>
            <p className="text-2xl font-semibold text-foreground">{tenant.memberships.length}</p>
            <p className="text-xs text-muted-foreground">usuarios conectados</p>
          </div>

          <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Mic className="h-4 w-4" />
              Agentes
            </h3>
            <p className="text-2xl font-semibold text-foreground">{tenant.agents.length}</p>
            <p className="text-xs text-muted-foreground">agentes configurados</p>
          </div>
        </section>
      </div>

      {/* Memberships Section */}
      <section className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-foreground">
            <Users className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Membresías
          </h2>
          <button
            type="button"
            onClick={() => setShowAddMembership(!showAddMembership)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar membresía
          </button>
        </div>

        {showAddMembership && (
          <div className="mb-4 rounded-lg border border-border bg-muted/30 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-muted-foreground">Email del usuario *</label>
                <input
                  type="email"
                  value={membershipEmail}
                  onChange={(e) => setMembershipEmail(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="usuario@empresa.com"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Rol</label>
                <select
                  value={membershipRole}
                  onChange={(e) => setMembershipRole(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
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
                  className="rounded-lg border border-border bg-background px-4 py-2 text-xs text-muted-foreground transition hover:bg-muted"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {membershipError && (
              <p className="mt-2 text-xs text-destructive">{membershipError}</p>
            )}
          </div>
        )}

        {tenant.memberships.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Sin membresías</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Email</th>
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Rol</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.memberships.map((m) => (
                  <tr key={m.id} className="border-b border-border">
                    <td className="py-2.5 pr-4 text-foreground">{m.user_email || <span className="text-muted-foreground/65">—</span>}</td>
                    <td className="py-2.5 pr-4 text-foreground">{m.user_name || <span className="text-muted-foreground/65">—</span>}</td>
                    <td className="py-2.5 pr-4 text-muted-foreground">{m.role}</td>
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
      <section className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-foreground">
            <Mic className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
            Agentes
          </h2>
          <button
            type="button"
            onClick={() => setShowAddAgent(!showAddAgent)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar agente
          </button>
        </div>

        {showAddAgent && (
          <div className="mb-4 rounded-lg border border-border bg-muted/30 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Nombre *</label>
                <input
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="Agente Inmobiliario"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Provider *</label>
                <input
                  type="text"
                  value={agentProvider}
                  onChange={(e) => setAgentProvider(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Agent ID *</label>
                <input
                  type="text"
                  value={agentAgentId}
                  onChange={(e) => setAgentAgentId(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  placeholder="uv-001"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Canal</label>
                <select
                  value={agentChannel}
                  onChange={(e) => setAgentChannel(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
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
                  className="rounded-lg border border-border bg-background px-4 py-2 text-xs text-muted-foreground transition hover:bg-muted"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {agentError && (
              <p className="mt-2 text-xs text-destructive">{agentError}</p>
            )}
          </div>
        )}

        {tenant.agents.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Sin agentes. Configura al menos uno para estar listo para llamadas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Provider</th>
                  <th className="pb-2 pr-4 font-medium">Agent ID</th>
                  <th className="pb-2 pr-4 font-medium">Canal</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.agents.map((a) => (
                  <tr key={a.id} className="border-b border-border">
                    <td className="py-2.5 pr-4 text-foreground">{a.name}</td>
                    <td className="py-2.5 pr-4 text-muted-foreground">{a.external_provider}</td>
                    <td className="py-2.5 pr-4 font-mono text-foreground">{a.external_agent_id}</td>
                    <td className="py-2.5 pr-4 text-muted-foreground">{a.channel_type || '—'}</td>
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

      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-tenant-title"
            className="w-full max-w-md rounded-xl border border-destructive/30 bg-card p-6 shadow-2xl"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2
                  id="delete-tenant-title"
                  className="flex items-center gap-2 text-lg font-semibold text-destructive"
                >
                  <Trash2 className="h-5 w-5" />
                  Borrar tenant
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Esta accion elimina el tenant, sus membresias, agentes, llamadas,
                  eventos, metricas y registros de auditoria asociados.
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseDeleteModal}
                disabled={deleting}
                className="rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                title="Cerrar"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-destructive">
                Codigo de confirmacion
              </p>
              <p className="mt-2 select-all rounded-md bg-background border border-border px-3 py-2 font-mono text-lg font-semibold tracking-[0.2em] text-destructive text-center">
                {deleteCode}
              </p>
            </div>

            <label className="mt-4 block text-xs font-medium text-muted-foreground">
              Escribe el codigo para confirmar
            </label>
            <input
              type="text"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value.toUpperCase())}
              className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 font-mono text-sm uppercase tracking-wider text-foreground placeholder:text-muted-foreground focus:border-destructive focus:outline-none focus:ring-1 focus:ring-destructive"
              placeholder={deleteCode}
              disabled={deleting}
            />

            {deleteError && (
              <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {deleteError}
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={handleCloseDeleteModal}
                disabled={deleting}
                className="rounded-lg border border-border bg-background px-4 py-2 text-sm text-foreground transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleDeleteTenant}
                disabled={!deleteReady || deleting}
                className="inline-flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground transition hover:bg-destructive/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Borrar definitivamente
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
