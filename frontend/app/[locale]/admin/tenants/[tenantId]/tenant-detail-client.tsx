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
  type TenantPlanPayload,
} from '@/lib/api/tenants';
import {
  addTenantAgent,
  addTenantMembership,
  deleteTenant,
  fetchTenantDetail,
  updateTenant,
  updateTenantPlan,
} from '@/lib/api/admin-tenants-client';
import { getAdminAccessRedirect } from '@/lib/auth/admin-client';
import { PlanUpdateForm } from '@/components/tenant-usage/PlanUpdateForm';
import { TenantSavingsComparison } from '@/components/tenant-usage/TenantSavingsComparison';
import { TenantUsageAlerts } from '@/components/tenant-usage/TenantUsageAlerts';
import { TenantUsageCard } from '@/components/tenant-usage/TenantUsageCard';

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400 dark:bg-emerald-400/10 dark:text-emerald-300">
        <CheckCircle2 className="h-3 w-3" />
        Activo
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 px-2.5 py-0.5 text-xs font-medium text-zinc-400 dark:bg-zinc-400/10 dark:text-zinc-300">
      <Clock className="h-3 w-3" />
      {status}
    </span>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center dark:border-red-400/20 dark:bg-red-400/5">
      <AlertCircle className="mx-auto mb-2 h-8 w-8 text-red-400 dark:text-red-300" />
      <p className="text-sm text-red-300 dark:text-red-200">{message}</p>
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
      <span className="font-mono text-sm text-zinc-300 dark:text-zinc-200">{value}</span>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded p-1 text-zinc-600 transition hover:text-zinc-300 dark:text-zinc-500 dark:hover:text-zinc-200"
        title={`Copiar ${label}`}
      >
        {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 dark:text-emerald-300" /> : <Copy className="h-3.5 w-3.5" />}
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
  const [planSaving, setPlanSaving] = useState(false);

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

  const handlePlanUpdate = async (payload: TenantPlanPayload) => {
    setPlanSaving(true);
    setError(null);
    const result = await updateTenantPlan(tenantId, payload);
    setPlanSaving(false);

    if (result.ok) {
      await load();
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
        <Loader2 className="h-8 w-8 animate-spin text-zinc-500 dark:text-zinc-400" />
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
            className="mb-3 inline-flex items-center gap-1.5 text-sm text-zinc-500 transition hover:text-zinc-300 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a tenants
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400 dark:bg-zinc-700 dark:text-zinc-300">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-zinc-100 sm:text-3xl dark:text-zinc-100">
                {tenant.name}
              </h1>
              <p className="text-sm text-zinc-500 font-mono dark:text-zinc-400">{tenant.slug}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={tenant.status} />
          <button
            type="button"
            onClick={handleOpenDeleteModal}
            className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/10 dark:border-red-400/30 dark:text-red-200 dark:hover:bg-red-400/10"
            title="Borrar tenant"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Borrar
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/20 bg-red-500/5 p-4 dark:border-red-400/20 dark:bg-red-400/5">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400 dark:text-red-300" />
            <div>
              <p className="text-sm font-medium text-red-300 dark:text-red-200">Error</p>
              <p className="text-sm text-red-400/80 dark:text-red-300/80">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Integration Info */}
      <section className="mb-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5 dark:border-cyan-400/20 dark:bg-cyan-400/5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase text-cyan-400 dark:text-cyan-300">
          <ExternalLink className="h-4 w-4" />
          Identificador operativo
        </h2>
        <p className="mb-3 text-xs text-zinc-400 dark:text-zinc-300">
          Usa <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-cyan-300 dark:bg-zinc-700 dark:text-cyan-200">{tenant.slug}</code> como identificador operativo en metadata de llamadas y webhooks.
        </p>
        <pre className="rounded-lg bg-zinc-950 p-3 font-mono text-sm text-zinc-300 dark:bg-zinc-900 dark:text-zinc-200">
          {JSON.stringify({ tenant_slug: tenant.slug }, null, 2)}
        </pre>
      </section>

      {tenant.usage && (
        <div className="mb-6 grid gap-6 lg:grid-cols-2">
          <TenantUsageCard usage={tenant.usage} />
          <PlanUpdateForm
            usage={tenant.usage}
            saving={planSaving}
            onSubmit={handlePlanUpdate}
          />
        </div>
      )}

      {tenant.usage && (
        <div className="mb-6 grid gap-6 lg:grid-cols-2">
          <TenantUsageAlerts alerts={tenant.usage.alerts} />
          {tenant.savings_comparison && (
            <TenantSavingsComparison comparison={tenant.savings_comparison} />
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Tenant Data */}
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 dark:border-zinc-700 dark:bg-zinc-800/50">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200 dark:text-zinc-100">
              <Building2 className="h-5 w-5 text-cyan-400 dark:text-cyan-300" />
              Datos del tenant
            </h2>
            {!editing ? (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-lg border border-zinc-700 p-1.5 text-zinc-500 transition hover:border-cyan-500/50 hover:text-cyan-400 dark:border-zinc-600 dark:text-zinc-400 dark:hover:border-cyan-400/50 dark:hover:text-cyan-300"
                title="Editar"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={saving}
                className="rounded-lg border border-emerald-500/30 p-1.5 text-emerald-400 transition hover:bg-emerald-500/10 dark:border-emerald-400/30 dark:text-emerald-300 dark:hover:bg-emerald-400/10"
                title="Guardar"
              >
                <Save className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">ID</label>
              <CopyableField value={tenant.id} label="Tenant ID" />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Slug</label>
              <CopyableField value={tenant.slug} label="Tenant slug" />
            </div>

            {editing ? (
              <>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Nombre</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Zona horaria</label>
                  <select
                    value={editTimezone}
                    onChange={(e) => setEditTimezone(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
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
                  <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Estado</label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
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
                    className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition hover:bg-zinc-800 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  >
                    Cancelar
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">Nombre</span>
                  <span className="text-sm text-zinc-200 dark:text-zinc-100">{tenant.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">Zona horaria</span>
                  <span className="flex items-center gap-1 text-sm text-zinc-300 dark:text-zinc-200">
                    <Globe className="h-3.5 w-3.5 text-zinc-600 dark:text-zinc-500" />
                    {tenant.timezone}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">Ready for calls</span>
                  {tenant.is_ready_for_calls ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400 dark:bg-emerald-400/10 dark:text-emerald-300">
                      <CheckCircle2 className="h-3 w-3" />
                      Sí
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-400/10 dark:text-zinc-400">
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
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 dark:border-zinc-700 dark:bg-zinc-800/50">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-400 dark:text-zinc-300">
              <Users className="h-4 w-4" />
              Membresías
            </h3>
            <p className="text-2xl font-semibold text-zinc-100 dark:text-zinc-100">{tenant.memberships.length}</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-500">usuarios conectados</p>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 dark:border-zinc-700 dark:bg-zinc-800/50">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-400 dark:text-zinc-300">
              <Mic className="h-4 w-4" />
              Agentes
            </h3>
            <p className="text-2xl font-semibold text-zinc-100 dark:text-zinc-100">{tenant.agents.length}</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-500">agentes configurados</p>
          </div>
        </section>
      </div>

      {/* Memberships Section */}
      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 dark:border-zinc-700 dark:bg-zinc-800/50">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200 dark:text-zinc-100">
            <Users className="h-5 w-5 text-cyan-400 dark:text-cyan-300" />
            Membresías
          </h2>
          <button
            type="button"
            onClick={() => setShowAddMembership(!showAddMembership)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-cyan-500/50 hover:text-cyan-400 dark:border-zinc-600 dark:text-zinc-200 dark:hover:border-cyan-400/50 dark:hover:text-cyan-300"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar membresía
          </button>
        </div>

        {showAddMembership && (
          <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950/50 p-4 dark:border-zinc-600 dark:bg-zinc-900/50">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Email del usuario *</label>
                <input
                  type="email"
                  value={membershipEmail}
                  onChange={(e) => setMembershipEmail(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                  placeholder="usuario@empresa.com"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Rol</label>
                <select
                  value={membershipRole}
                  onChange={(e) => setMembershipRole(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
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
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-cyan-500 dark:bg-cyan-500 dark:hover:bg-cyan-400"
                >
                  Agregar
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddMembership(false)}
                  className="rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-400 transition hover:bg-zinc-800 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-700"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {membershipError && (
              <p className="mt-2 text-xs text-red-400 dark:text-red-300">{membershipError}</p>
            )}
          </div>
        )}

        {tenant.memberships.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-600 dark:text-zinc-500">Sin membresías</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                  <th className="pb-2 pr-4 font-medium">Email</th>
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Rol</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.memberships.map((m) => (
                  <tr key={m.id} className="border-b border-zinc-800/50 dark:border-zinc-700/50">
                    <td className="py-2.5 pr-4 text-zinc-300 dark:text-zinc-200">{m.user_email || <span className="text-zinc-600 dark:text-zinc-500">—</span>}</td>
                    <td className="py-2.5 pr-4 text-zinc-300 dark:text-zinc-200">{m.user_name || <span className="text-zinc-600 dark:text-zinc-500">—</span>}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 dark:text-zinc-300">{m.role}</td>
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
      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 dark:border-zinc-700 dark:bg-zinc-800/50">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-200 dark:text-zinc-100">
            <Mic className="h-5 w-5 text-cyan-400 dark:text-cyan-300" />
            Agentes
          </h2>
          <button
            type="button"
            onClick={() => setShowAddAgent(!showAddAgent)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:border-cyan-500/50 hover:text-cyan-400 dark:border-zinc-600 dark:text-zinc-200 dark:hover:border-cyan-400/50 dark:hover:text-cyan-300"
          >
            <Plus className="h-3.5 w-3.5" />
            Agregar agente
          </button>
        </div>

        {showAddAgent && (
          <div className="mb-4 rounded-lg border border-zinc-700 bg-zinc-950/50 p-4 dark:border-zinc-600 dark:bg-zinc-900/50">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Nombre *</label>
                <input
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                  placeholder="Agente Inmobiliario"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Provider *</label>
                <input
                  type="text"
                  value={agentProvider}
                  onChange={(e) => setAgentProvider(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Agent ID *</label>
                <input
                  type="text"
                  value={agentAgentId}
                  onChange={(e) => setAgentAgentId(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-mono text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
                  placeholder="uv-001"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500 dark:text-zinc-400">Canal</label>
                <select
                  value={agentChannel}
                  onChange={(e) => setAgentChannel(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
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
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-cyan-500 dark:bg-cyan-500 dark:hover:bg-cyan-400"
                >
                  Agregar
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddAgent(false)}
                  className="rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-400 transition hover:bg-zinc-800 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-700"
                >
                  Cancelar
                </button>
              </div>
            </div>
            {agentError && (
              <p className="mt-2 text-xs text-red-400 dark:text-red-300">{agentError}</p>
            )}
          </div>
        )}

        {tenant.agents.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-600 dark:text-zinc-500">
            Sin agentes. Configura al menos uno para estar listo para llamadas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                  <th className="pb-2 pr-4 font-medium">Nombre</th>
                  <th className="pb-2 pr-4 font-medium">Provider</th>
                  <th className="pb-2 pr-4 font-medium">Agent ID</th>
                  <th className="pb-2 pr-4 font-medium">Canal</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {tenant.agents.map((a) => (
                  <tr key={a.id} className="border-b border-zinc-800/50 dark:border-zinc-700/50">
                    <td className="py-2.5 pr-4 text-zinc-300 dark:text-zinc-200">{a.name}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 dark:text-zinc-300">{a.external_provider}</td>
                    <td className="py-2.5 pr-4 font-mono text-zinc-300 dark:text-zinc-200">{a.external_agent_id}</td>
                    <td className="py-2.5 pr-4 text-zinc-400 dark:text-zinc-300">{a.channel_type || '—'}</td>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 dark:bg-black/50">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-tenant-title"
            className="w-full max-w-md rounded-xl border border-red-500/30 bg-zinc-950 p-6 shadow-2xl dark:border-red-400/30 dark:bg-zinc-900"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2
                  id="delete-tenant-title"
                  className="flex items-center gap-2 text-lg font-semibold text-red-200 dark:text-red-100"
                >
                  <Trash2 className="h-5 w-5" />
                  Borrar tenant
                </h2>
                <p className="mt-2 text-sm text-zinc-400 dark:text-zinc-300">
                  Esta accion elimina el tenant, sus membresias, agentes, llamadas,
                  eventos, metricas y registros de auditoria asociados.
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseDeleteModal}
                disabled={deleting}
                className="rounded-lg p-1 text-zinc-500 transition hover:bg-zinc-900 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                title="Cerrar"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 dark:border-red-400/20 dark:bg-red-400/5">
              <p className="text-xs font-medium uppercase tracking-wide text-red-300 dark:text-red-200">
                Codigo de confirmacion
              </p>
              <p className="mt-2 select-all rounded-md bg-zinc-950 px-3 py-2 font-mono text-lg font-semibold tracking-[0.2em] text-red-100 dark:bg-zinc-800 dark:text-red-50">
                {deleteCode}
              </p>
            </div>

            <label className="mt-4 block text-xs font-medium text-zinc-400 dark:text-zinc-300">
              Escribe el codigo para confirmar
            </label>
            <input
              type="text"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value.toUpperCase())}
              className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm uppercase tracking-wider text-zinc-100 placeholder:text-zinc-600 focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-400 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-red-300 dark:focus:ring-red-300"
              placeholder={deleteCode}
              disabled={deleting}
            />

            {deleteError && (
              <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-sm text-red-300 dark:border-red-400/20 dark:bg-red-400/5 dark:text-red-200">
                {deleteError}
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={handleCloseDeleteModal}
                disabled={deleting}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleDeleteTenant}
                disabled={!deleteReady || deleting}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-red-950 disabled:text-red-300/50 dark:bg-red-500 dark:hover:bg-red-400"
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
