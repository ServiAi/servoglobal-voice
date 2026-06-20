'use client';

import React, { useState, useTransition, useCallback } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import type { TaskResponse } from '@/types/crm';
import { CrmTaskList } from '@/components/crm/CrmTaskList';
import { CrmTaskForm } from '@/components/crm/CrmTaskForm';
import { createCrmTask, updateCrmTask, deleteCrmTask } from '@/lib/api/crm';
import { ShieldAlert, Filter, CheckSquare } from 'lucide-react';

type TasksClientProps = {
  tasks: TaskResponse[];
  accessToken: string;
  locale: string;
};

export function TasksClient({
  tasks,
  accessToken,
  locale,
}: TasksClientProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filter states
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [priority, setPriority] = useState(searchParams.get('priority') || '');

  const triggerRefresh = (msg: string) => {
    setSuccessMsg(msg);
    startTransition(() => {
      router.refresh();
    });
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const createQueryString = useCallback(
    (params: Record<string, string>) => {
      const newSearchParams = new URLSearchParams(searchParams.toString());
      Object.entries(params).forEach(([name, value]) => {
        if (value) {
          newSearchParams.set(name, value);
        } else {
          newSearchParams.delete(name);
        }
      });
      return newSearchParams.toString();
    },
    [searchParams]
  );

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(`${pathname}?${createQueryString({ status, priority })}`);
  };

  const handleResetFilters = () => {
    setStatus('');
    setPriority('');
    router.push(pathname);
  };

  const handleCreateTask = async (taskPayload: {
    title: string;
    description?: string;
    due_at?: string;
    priority: string;
  }) => {
    setError(null);
    const res = await createCrmTask(accessToken, taskPayload);
    if (res.ok) {
      triggerRefresh('Tarea creada con éxito.');
    } else {
      setError(`Error al crear tarea: ${res.detail}`);
      throw new Error(res.detail);
    }
  };

  const handleToggleTaskStatus = async (taskId: string, nextStatus: string) => {
    setError(null);
    const res = await updateCrmTask(accessToken, taskId, { status: nextStatus });
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
      triggerRefresh('Tarea eliminada con éxito.');
    } else {
      setError(`Error al eliminar tarea: ${res.detail}`);
    }
  };

  const pendingCount = tasks.filter((t) => t.status === 'pending').length;
  const completedCount = tasks.filter((t) => t.status === 'done').length;

  return (
    <div className="flex flex-col gap-6">
      {/* Toast Alert Feedback */}
      {(error || successMsg || isPending) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span>Sincronizando tareas...</span>
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

      {/* Header section */}
      <section className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Gestión de Tareas
        </h2>
        <p className="text-sm text-muted-foreground">
          Organiza, completa y programa actividades de seguimiento de leads.
        </p>
      </section>

      {/* Grid: Filters & Creation vs Tasks List */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Side: Filters & Creation (1 col) */}
        <div className="lg:col-span-1 flex flex-col gap-6">
          {/* Filters Form */}
          <div className="rounded-xl border border-border bg-card/65 p-5 shadow-xs flex flex-col gap-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider pb-2 border-b border-border/60">
              <Filter className="h-4 w-4 text-violet-500" />
              <span>Filtrar Tareas</span>
            </div>

            <form onSubmit={handleApplyFilters} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="filter-status" className="text-2xs font-bold text-muted-foreground uppercase">
                  Estado
                </label>
                <select
                  id="filter-status"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="w-full rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                >
                  <option value="">Todos</option>
                  <option value="pending">Pendiente</option>
                  <option value="done">Completado</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="filter-priority" className="text-2xs font-bold text-muted-foreground uppercase">
                  Prioridad
                </label>
                <select
                  id="filter-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  className="w-full rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                >
                  <option value="">Todas</option>
                  <option value="high">Alta</option>
                  <option value="medium">Media</option>
                  <option value="low">Baja</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-muted"
                >
                  Limpiar
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-violet-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-violet-500"
                >
                  Filtrar
                </button>
              </div>
            </form>
          </div>

          {/* Creation Form */}
          <CrmTaskForm onSubmit={handleCreateTask} />
        </div>

        {/* Right Side: Tasks List (2 cols) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
            <div className="border-b border-border/60 pb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckSquare className="h-5 w-5 text-violet-500" />
                <h3 className="text-base font-bold text-foreground">Lista de Tareas</h3>
              </div>
              <div className="flex gap-3 text-2xs text-muted-foreground font-semibold uppercase">
                <span className="text-amber-500">{pendingCount} Pendientes</span>
                <span className="text-zinc-500/40">•</span>
                <span className="text-emerald-500">{completedCount} Completadas</span>
              </div>
            </div>

            <CrmTaskList
              tasks={tasks}
              onToggleStatus={handleToggleTaskStatus}
              onDelete={handleDeleteTask}
              showLeadInfo={true}
              locale={locale}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
