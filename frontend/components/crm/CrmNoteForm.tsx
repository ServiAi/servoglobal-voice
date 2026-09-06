'use client';

import React, { useState } from 'react';
import { Send, FileText } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { canCreateNote } from '@/lib/permissions/crm';

type CrmNoteFormProps = {
  onSubmit: (note: string) => Promise<void>;
  userRole?: string;
};

export function CrmNoteForm({ onSubmit, userRole }: CrmNoteFormProps) {
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canCreate = canCreateNote(userRole);

  if (!canCreate) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const cleanedNote = note.trim();

    if (!cleanedNote) {
      setError('La nota no puede estar vacía.');
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(cleanedNote);
      setNote('');
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Error al guardar la nota.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider pb-2 border-b border-border/60">
        <FileText className="h-4 w-4 text-violet-500" />
        <span>Agregar Nota Interna</span>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          rows={3}
          placeholder="Escribe comentarios sobre este lead (ej: cliente solicita propuesta detallada, volver a llamar el lunes)..."
          value={note}
          onChange={(e) => {
            setNote(e.target.value);
            if (error) setError(null);
          }}
          disabled={submitting}
          className="w-full rounded-md border border-border bg-zinc-950/40 p-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
        />

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting || !note.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-4 py-2 text-xs font-bold text-white hover:bg-violet-500 disabled:pointer-events-none disabled:opacity-50 transition shadow-sm"
          >
            {submitting ? (
              <>
                <CircularLoader size="xs" glow={false} />
                Guardando...
              </>
            ) : (
              <>
                <Send className="h-3.5 w-3.5" />
                Agregar Nota
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
