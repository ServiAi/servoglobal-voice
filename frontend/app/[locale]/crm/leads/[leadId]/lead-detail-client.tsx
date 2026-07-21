'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import type { LeadDetailResponse, LeadUpdateRequest } from '@/types/crm';
import { createCrmLeadNote, createCrmTask, deleteCrmTask, updateCrmLead, updateCrmTask } from '@/lib/api/crm';
import { CrmLeadWorkspace } from '@/components/crm/lead-workspace/CrmLeadWorkspace';

type LeadDetailClientProps = {
  lead: LeadDetailResponse;
  accessToken: string;
  locale: string;
  userRole?: string;
};

export function LeadDetailClient({ lead, accessToken, locale, userRole }: LeadDetailClientProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const refresh = (message: string) => {
    setSuccess(message);
    startTransition(() => router.refresh());
  };

  const handleSave = async (payload: LeadUpdateRequest) => {
    setError(null);
    setSuccess(null);
    const result = await updateCrmLead(accessToken, lead.id, payload);
    if (!result.ok) {
      setError(`Error al guardar: ${result.detail}`);
      throw new Error(result.detail);
    }
    refresh('Lead actualizado con éxito.');
  };

  const handleAddNote = async (note: string) => {
    setError(null);
    const result = await createCrmLeadNote(accessToken, lead.id, { note });
    if (!result.ok) {
      setError(`Error al agregar nota: ${result.detail}`);
      throw new Error(result.detail);
    }
    refresh('Nota interna agregada con éxito.');
  };

  const handleCreateTask = async (task: { title: string; description?: string; due_at?: string; priority: string }) => {
    setError(null);
    const result = await createCrmTask(accessToken, { ...task, lead_id: lead.id, contact_id: lead.contact.id });
    if (!result.ok) {
      setError(`Error al crear tarea: ${result.detail}`);
      throw new Error(result.detail);
    }
    refresh('Tarea creada con éxito.');
  };

  const handleToggleTask = async (taskId: string, status: string) => {
    setError(null);
    const result = await updateCrmTask(accessToken, taskId, { status });
    if (!result.ok) {
      setError(`Error al actualizar tarea: ${result.detail}`);
      throw new Error(result.detail);
    }
    refresh('Estado de tarea actualizado.');
  };

  const handleDeleteTask = async (taskId: string) => {
    setError(null);
    const result = await deleteCrmTask(accessToken, taskId);
    if (!result.ok) {
      setError(`Error al eliminar tarea: ${result.detail}`);
      throw new Error(result.detail);
    }
    refresh('Tarea eliminada con éxito.');
  };

  return (
    <>
      {(error || success || isPending) ? (
        <div className="fixed bottom-4 left-4 right-4 z-50 rounded-lg border border-border bg-card p-4 shadow-lg sm:left-auto sm:max-w-sm" role="status" aria-live="polite">
          {isPending ? <p className="text-sm text-muted-foreground">Sincronizando cambios…</p> : null}
          {error ? <p className="flex items-start gap-2 text-sm text-destructive"><ShieldAlert className="mt-0.5 size-4 shrink-0" />{error}</p> : null}
          {success && !isPending ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{success}</p> : null}
        </div>
      ) : null}
      <CrmLeadWorkspace lead={lead} accessToken={accessToken} locale={locale} userRole={userRole} onSave={handleSave} onAddNote={handleAddNote} onCreateTask={handleCreateTask} onToggleTask={handleToggleTask} onDeleteTask={handleDeleteTask} />
    </>
  );
}
