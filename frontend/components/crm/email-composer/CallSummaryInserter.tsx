'use client';

import { FileText, PlusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { CallSummaryResponse } from '@/types/crm';

type Props = {
  summary: CallSummaryResponse | null;
  disabled: boolean;
  onInsert: (variant: 'full' | 'short') => void;
};

export function CallSummaryInserter({ summary, disabled, onInsert }: Props) {
  const available = summary?.status === 'available';
  return (
    <section className="grid gap-2 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-foreground">Resumen de llamada</div>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
          {available ? 'Disponible' : 'No disponible'}
        </span>
      </div>
      {!available && <p className="text-xs text-muted-foreground">No hay resumen de llamada disponible para este lead.</p>}
      {available && (
        <div className="grid gap-2">
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onInsert('full')} className="justify-start gap-2">
            <FileText className="h-4 w-4" />
            Insertar resumen
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onInsert('short')} className="justify-start gap-2">
            <PlusCircle className="h-4 w-4" />
            Insertar version corta
          </Button>
        </div>
      )}
    </section>
  );
}
