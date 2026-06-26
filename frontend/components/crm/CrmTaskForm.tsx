'use client';

import React, { useState } from 'react';
import { Plus, CheckSquare } from 'lucide-react';
import { canCreateTask } from '@/lib/permissions/crm';

type CrmTaskFormProps = {
  onSubmit: (task: {
    title: string;
    description?: string;
    due_at?: string;
    priority: string;
  }) => Promise<void>;
  userRole?: string;
};

export function CrmTaskForm({ onSubmit, userRole }: CrmTaskFormProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [priority, setPriority] = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canCreate = canCreateTask(userRole);

  if (!canCreate) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const cleanedTitle = title.trim();

    if (!cleanedTitle) {
      setError('El título de la tarea es requerido.');
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        title: cleanedTitle,
        description: description.trim() || undefined,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
        priority,
      });
      // Reset form
      setTitle('');
      setDescription('');
      setDueAt('');
      setPriority('medium');
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Error al crear la tarea.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider pb-2 border-b border-border/60">
        <CheckSquare className="h-4 w-4 text-violet-500" />
        <span>Crear Nueva Tarea</span>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {/* Title */}
        <div className="flex flex-col gap-1">
          <label htmlFor="task-title" className="text-2xs font-bold text-muted-foreground uppercase">
            Título
          </label>
          <input
            type="text"
            id="task-title"
            placeholder="Ej: Enviar propuesta técnica"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              if (error) setError(null);
            }}
            disabled={submitting}
            className="w-full rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
          />
        </div>

        {/* Description */}
        <div className="flex flex-col gap-1">
          <label htmlFor="task-desc" className="text-2xs font-bold text-muted-foreground uppercase">
            Descripción (Opcional)
          </label>
          <textarea
            id="task-desc"
            rows={2}
            placeholder="Detalles adicionales sobre la tarea..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={submitting}
            className="w-full rounded-md border border-border bg-zinc-950/40 p-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
          />
        </div>

        {/* Due Date & Priority */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="task-due" className="text-2xs font-bold text-muted-foreground uppercase">
              Fecha de Vencimiento
            </label>
            <input
              type="datetime-local"
              id="task-due"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              disabled={submitting}
              className="w-full rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="task-priority" className="text-2xs font-bold text-muted-foreground uppercase">
              Prioridad
            </label>
            <select
              id="task-priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              disabled={submitting}
              className="w-full rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            >
              <option value="low">Baja</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
            </select>
          </div>
        </div>

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        <div className="flex justify-end pt-1">
          <button
            type="submit"
            disabled={submitting || !title.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-4 py-2 text-xs font-bold text-white hover:bg-violet-500 disabled:pointer-events-none disabled:opacity-50 transition shadow-sm"
          >
            {submitting ? (
              <>
                <div className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Creando...
              </>
            ) : (
              <>
                <Plus className="h-4 w-4" />
                Crear Tarea
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
