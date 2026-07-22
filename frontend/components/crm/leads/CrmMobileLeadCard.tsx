import Link from 'next/link';
import { MoreHorizontal, Trash2 } from 'lucide-react';
import type { LeadListItem } from '@/types/crm';
import { CrmStageBadge } from '../shared/CrmStageBadge';
import { CrmStatusBadge } from '../shared/CrmStatusBadge';

type Props = { lead: LeadListItem; locale: string; canDelete: boolean; onDelete: () => void; formatDate: (value?: string | null) => string };

export function CrmMobileLeadCard({ lead, locale, canDelete, onDelete, formatDate }: Props) {
  return (
    <article className="rounded-[var(--radius-card)] border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><h3 className="truncate text-sm font-semibold">{lead.contact_name}</h3><p className="truncate text-xs text-muted-foreground">{lead.company || 'Sin empresa registrada'}</p></div>
        <details className="relative">
          <summary aria-label={`Acciones para ${lead.contact_name}`} className="flex size-10 cursor-pointer list-none items-center justify-center rounded-[var(--radius-control)] hover:bg-muted"><MoreHorizontal aria-hidden="true" className="size-5" /></summary>
          <div className="absolute right-0 z-10 mt-1 w-40 rounded-[var(--radius-control)] border border-border bg-popover p-1 shadow-lg">
            <Link href={`/${locale}/crm/leads/${lead.lead_id}`} className="flex min-h-10 items-center rounded px-3 text-sm hover:bg-muted">Ver detalle</Link>
            {canDelete ? <button type="button" onClick={onDelete} className="flex min-h-10 w-full items-center gap-2 rounded px-3 text-sm text-destructive hover:bg-destructive/10"><Trash2 aria-hidden="true" className="size-4" />Eliminar</button> : null}
          </div>
        </details>
      </div>
      <div className="mt-3 flex flex-wrap gap-2"><CrmStageBadge stageKey={lead.stage_key} stageName={lead.stage_name} /><CrmStatusBadge status={lead.status} /></div>
      <dl className="mt-4 grid gap-2 text-xs">
        <div><dt className="text-muted-foreground">Contacto</dt><dd className="truncate">{lead.contact_phone || lead.contact_email || 'Sin datos de contacto'}</dd></div>
        <div className="grid grid-cols-2 gap-3"><div><dt className="text-muted-foreground">Origen</dt><dd className="truncate">{lead.source || 'Sin origen'}</dd></div><div><dt className="text-muted-foreground">Actualizado</dt><dd>{formatDate(lead.updated_at)}</dd></div></div>
      </dl>
      <Link href={`/${locale}/crm/leads/${lead.lead_id}`} className="mt-4 inline-flex h-10 w-full items-center justify-center rounded-[var(--radius-control)] border border-border text-sm font-semibold hover:bg-muted">Ver detalle</Link>
    </article>
  );
}
