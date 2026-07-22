'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRightLeft, Building2, CalendarClock, Eye, Loader2 } from 'lucide-react';
import type { PipelineBoardLeadItem } from '@/types/crm';
import { formatCrmDate } from './lead-workspace/crm-format';
import { CrmStatusBadge } from './shared/CrmStatusBadge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

type Props = {
  lead: PipelineBoardLeadItem;
  locale: string;
  stages: Array<{ key: string; name: string }>;
  onStageChange: (leadId: string, newStageKey: string) => Promise<boolean>;
  currentStageKey: string;
};

export function CrmLeadCard({ lead, locale, stages, onStageChange, currentStageKey }: Props) {
  const [open, setOpen] = useState(false);
  const [selectedStage, setSelectedStage] = useState(currentStageKey);
  const [updating, setUpdating] = useState(false);
  const currentStage = stages.find((stage) => stage.key === currentStageKey);

  const moveLead = async () => {
    if (selectedStage === currentStageKey || updating) return;
    setUpdating(true);
    try {
      if (await onStageChange(lead.id, selectedStage)) setOpen(false);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <Card className="space-y-3 border-border bg-card p-4 shadow-xs transition-colors hover:border-primary/40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><h3 className="break-words text-sm font-semibold leading-5 text-foreground">{lead.contact_name}</h3>{lead.company ? <p className="mt-1 flex items-start gap-1.5 break-words text-xs text-muted-foreground"><Building2 className="mt-0.5 size-3.5 shrink-0" />{lead.company}</p> : null}</div>
        <CrmStatusBadge status={lead.status} />
      </div>

      {lead.short_summary ? <p className="line-clamp-3 rounded-md border border-border/60 bg-muted/30 p-2 text-xs leading-5 text-muted-foreground">{lead.short_summary}</p> : null}
      {lead.last_activity_at ? <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><CalendarClock className="size-3.5" />Última actividad: {formatCrmDate(lead.last_activity_at)}</p> : null}

      <div className="flex items-center gap-2 border-t border-border pt-3">
        <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => { setSelectedStage(currentStageKey); setOpen(true); }}><ArrowRightLeft className="mr-2 size-3.5" />Mover</Button>
        <Button asChild size="sm" className="flex-1"><Link href={`/${locale}/crm/leads/${lead.id}`}><Eye className="mr-2 size-3.5" />Ver</Link></Button>
      </div>

      <Dialog open={open} onOpenChange={(nextOpen) => { if (!updating) setOpen(nextOpen); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Mover Lead</DialogTitle><DialogDescription>Etapa actual: {currentStage?.name ?? currentStageKey}. Selecciona el nuevo destino para {lead.contact_name}.</DialogDescription></DialogHeader>
          <label className="space-y-1 py-2"><span className="text-sm font-medium text-foreground">Nueva etapa</span><select value={selectedStage} onChange={(event) => setSelectedStage(event.target.value)} disabled={updating} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">{stages.map((stage) => <option key={stage.key} value={stage.key}>{stage.name}{stage.key === currentStageKey ? ' (actual)' : ''}</option>)}</select></label>
          <DialogFooter><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={updating}>Cancelar</Button><Button type="button" onClick={moveLead} disabled={updating || selectedStage === currentStageKey}>{updating ? <Loader2 className="mr-2 size-4 animate-spin motion-reduce:animate-none" /> : null}{updating ? 'Moviendo…' : 'Confirmar movimiento'}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
