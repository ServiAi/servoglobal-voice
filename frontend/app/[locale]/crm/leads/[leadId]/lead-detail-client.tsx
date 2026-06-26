'use client';

import React, { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import type { LeadDetailResponse, LeadUpdateRequest } from '@/types/crm';
import { CrmLeadDetailPanel } from '@/components/crm/CrmLeadDetailPanel';
import { CrmActivityTimeline } from '@/components/crm/CrmActivityTimeline';
import { CrmTaskList } from '@/components/crm/CrmTaskList';
import { CrmTaskForm } from '@/components/crm/CrmTaskForm';
import { CrmNoteForm } from '@/components/crm/CrmNoteForm';
import { CrmLeadQuickActions } from '@/components/crm/CrmLeadQuickActions';
import { updateCrmLead, createCrmLeadNote, createCrmTask, updateCrmTask, deleteCrmTask } from '@/lib/api/crm';
import { ShieldAlert, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

type LeadDetailClientProps = {
  lead: LeadDetailResponse;
  accessToken: string;
  locale: string;
  userRole?: string;
};

export function LeadDetailClient({
  lead,
  accessToken,
  locale,
  userRole,
}: LeadDetailClientProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const triggerRefresh = (msg: string) => {
    setSuccessMsg(msg);
    startTransition(() => {
      router.refresh();
    });
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const handleSaveLead = async (payload: LeadUpdateRequest) => {
    setError(null);
    const res = await updateCrmLead(accessToken, lead.id, payload);
    if (res.ok) {
      triggerRefresh('Lead actualizado con exito.');
      return;
    }

    setError(`Error al guardar: ${res.detail}`);
    throw new Error(res.detail);
  };

  const handleAddNote = async (noteText: string) => {
    setError(null);
    const res = await createCrmLeadNote(accessToken, lead.id, { note: noteText });
    if (res.ok) {
      triggerRefresh('Nota interna agregada con exito.');
      return;
    }

    setError(`Error al agregar nota: ${res.detail}`);
    throw new Error(res.detail);
  };

  const handleCreateTask = async (taskPayload: {
    title: string;
    description?: string;
    due_at?: string;
    priority: string;
  }) => {
    setError(null);
    const res = await createCrmTask(accessToken, {
      ...taskPayload,
      lead_id: lead.id,
      contact_id: lead.contact.id,
    });
    if (res.ok) {
      triggerRefresh('Tarea creada con exito.');
      return;
    }

    setError(`Error al crear tarea: ${res.detail}`);
    throw new Error(res.detail);
  };

  const handleToggleTaskStatus = async (taskId: string, status: string) => {
    setError(null);
    const res = await updateCrmTask(accessToken, taskId, { status });
    if (res.ok) {
      triggerRefresh('Estado de tarea actualizado.');
    } else {
      setError(`Error al actualizar tarea: ${res.detail}`);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    setError(null);
    const res = await deleteCrmTask(accessToken, taskId);
    if (res.ok) {
      triggerRefresh('Tarea eliminada con exito.');
    } else {
      setError(`Error al eliminar tarea: ${res.detail}`);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {(error || successMsg || isPending) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span>Sincronizando cambios...</span>
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <ShieldAlert className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}
          {successMsg && !isPending && (
            <div className="flex items-center gap-2 text-sm text-emerald-500">
              <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
              <span>{successMsg}</span>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-4">
        <Link
          href={`/${locale}/crm/leads`}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground transition shadow-2xs"
          title="Volver"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Detalle del Lead
          </h2>
          <p className="text-sm text-muted-foreground">
            {lead.contact.name} - {lead.stage.name}
          </p>
        </div>
      </div>

      <CrmLeadDetailPanel lead={lead} onSave={handleSaveLead} userRole={userRole} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 mt-4">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <CrmActivityTimeline activities={lead.activities} />
        </div>

        <div className="lg:col-span-1 flex flex-col gap-6">
          <CrmLeadQuickActions
            leadId={lead.id}
            accessToken={accessToken}
            currentStageKey={lead.stage.key}
            userRole={userRole}
          />

          <CrmNoteForm onSubmit={handleAddNote} userRole={userRole} />

          <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
            <div className="border-b border-border/60 pb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold text-foreground">Tareas del Lead</h3>
              <span className="text-2xs text-muted-foreground">
                Total: {lead.tasks.length}
              </span>
            </div>
            <CrmTaskList
              tasks={lead.tasks}
              onToggleStatus={handleToggleTaskStatus}
              onDelete={handleDeleteTask}
              showLeadInfo={false}
              locale={locale}
              userRole={userRole}
            />
          </div>

          <CrmTaskForm onSubmit={handleCreateTask} userRole={userRole} />
        </div>
      </div>
    </div>
  );
}
