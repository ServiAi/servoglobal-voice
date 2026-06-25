'use client';

import React, { useState } from 'react';
import type { TaskResponse } from '@/types/crm';
import { Card } from '../ui/card';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Trash2, Calendar, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

type CrmTaskListProps = {
  tasks: TaskResponse[];
  onToggleStatus: (taskId: string, newStatus: string) => Promise<void>;
  onDelete?: (taskId: string) => Promise<void>;
  showLeadInfo?: boolean;
  locale?: string;
};

export function CrmTaskList({
  tasks,
  onToggleStatus,
  onDelete,
  showLeadInfo = false,
  locale = 'es',
}: CrmTaskListProps) {
  const [loadingTasks, setLoadingTasks] = useState<Record<string, boolean>>({});
  const [deleteTaskId, setDeleteTaskId] = useState<string | null>(null);

  const handleStatusToggle = async (taskId: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'done' ? 'pending' : 'done';
    setLoadingTasks((prev) => ({ ...prev, [taskId]: true }));
    try {
      await onToggleStatus(taskId, nextStatus);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingTasks((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleDelete = async (taskId: string) => {
    if (!onDelete) return;
    setLoadingTasks((prev) => ({ ...prev, [taskId]: true }));
    try {
      await onDelete(taskId);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingTasks((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleConfirmDelete = async () => {
    const taskId = deleteTaskId;
    if (!taskId) return;

    setDeleteTaskId(null);
    await handleDelete(taskId);
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case 'high':
        return <span className="inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-2xs font-semibold text-red-500 border border-red-500/20">Alta</span>;
      case 'medium':
        return <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-2xs font-semibold text-amber-500 border border-amber-500/20">Media</span>;
      case 'low':
        return <span className="inline-flex items-center rounded-full bg-zinc-500/10 px-2 py-0.5 text-2xs font-semibold text-zinc-400 border border-zinc-500/20">Baja</span>;
      default:
        return <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-2xs font-semibold text-muted-foreground border border-border">{priority}</span>;
    }
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return null;

    const isOverdue = date.getTime() < Date.now();

    return {
      label: date.toLocaleDateString('es-ES', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }),
      isOverdue,
    };
  };

  return (
    <div className="flex flex-col gap-3">
      {tasks.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-6 border border-dashed border-border/60 rounded-xl">
          No hay tareas programadas.
        </p>
      ) : (
        tasks.map((task) => {
          const isDone = task.status === 'done';
          const dueInfo = formatDate(task.due_at);
          const isLoading = loadingTasks[task.id];

          return (
            <Card
              key={task.id}
              className={cn(
                'p-4 bg-card border border-border/80 hover:border-violet-500/30 transition shadow-2xs flex items-start justify-between gap-4',
                isDone && 'opacity-65 bg-muted/5',
                isLoading && 'pointer-events-none opacity-50'
              )}
            >
              <div className="flex items-start gap-3 flex-1">
                {/* Status Checkbox */}
                <button
                  type="button"
                  onClick={() => handleStatusToggle(task.id, task.status)}
                  disabled={isLoading}
                  className="mt-1 flex items-center justify-center h-5 w-5 rounded border border-border bg-zinc-950/20 text-violet-500 hover:border-violet-500 transition shrink-0 cursor-pointer disabled:pointer-events-none"
                >
                  {isDone && <CheckCircle2 className="h-4 w-4 fill-violet-500 text-white" />}
                </button>

                <div className="flex flex-col gap-1.5 flex-1">
                  {/* Title */}
                  <span className={cn(
                    'text-sm font-semibold text-foreground leading-tight',
                    isDone && 'line-through text-muted-foreground'
                  )}>
                    {task.title}
                  </span>

                  {/* Description */}
                  {task.description && (
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                      {task.description}
                    </p>
                  )}

                  {/* Badges row: Priority, Due Date, Lead Info */}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {getPriorityBadge(task.priority)}

                    {dueInfo && (
                      <span className={cn(
                        'inline-flex items-center gap-1 rounded bg-muted/40 px-2 py-0.5 text-2xs font-mono border',
                        dueInfo.isOverdue && !isDone
                          ? 'text-red-500 bg-red-500/5 border-red-500/10'
                          : 'text-muted-foreground border-border/50'
                      )}>
                        <Calendar className="h-3 w-3 shrink-0" />
                        <span>{dueInfo.label}</span>
                        {dueInfo.isOverdue && !isDone && (
                          <span className="font-bold text-[9px] uppercase tracking-wide ml-0.5 animate-pulse text-red-500">
                            (Vencida)
                          </span>
                        )}
                      </span>
                    )}

                    {showLeadInfo && task.lead_id && (
                      <span className="text-2xs text-muted-foreground">
                        Lead:{' '}
                        <a
                          href={`/${locale}/crm/leads/${task.lead_id}`}
                          className="font-semibold text-violet-500 hover:underline"
                        >
                          Ver detalle
                        </a>
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Delete button */}
              {onDelete && (
                <button
                  type="button"
                  onClick={() => setDeleteTaskId(task.id)}
                  disabled={isLoading}
                  className="text-muted-foreground hover:text-destructive transition p-1.5 rounded-md hover:bg-muted/50"
                  title="Eliminar tarea"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </Card>
          );
        })
      )}

      <Dialog open={deleteTaskId !== null} onOpenChange={(open) => !open && setDeleteTaskId(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-red-500/10 text-red-500">
              <Trash2 className="h-6 w-6" />
            </div>
            <DialogTitle className="text-center">Eliminar tarea</DialogTitle>
            <DialogDescription className="text-center">
              Esta acción eliminará la tarea seleccionada de forma permanente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:justify-center">
            <Button type="button" variant="outline" onClick={() => setDeleteTaskId(null)}>
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={handleConfirmDelete}>
              Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
