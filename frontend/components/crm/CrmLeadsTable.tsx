'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ChevronLeft, ChevronRight, MoreHorizontal, ShieldAlert, Trash2 } from 'lucide-react';
import { useState, useTransition } from 'react';
import type { LeadsListResponse } from '@/types/crm';
import { deleteAllCrmLeads, deleteCrmLead } from '@/lib/api/crm';
import { canEditLead } from '@/lib/permissions/crm';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CrmMobileLeadCard } from './leads/CrmMobileLeadCard';
import { CrmStageBadge } from './shared/CrmStageBadge';
import { CrmStatusBadge } from './shared/CrmStatusBadge';

type Props = { data: LeadsListResponse; locale: string; accessToken?: string; userRole?: string };

export function CrmLeadsTable({ data, locale, accessToken, userRole }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<{ kind: 'error' | 'success'; text: string } | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<{ type: 'one'; leadId: string } | { type: 'all' } | null>(null);
  const items = Array.isArray(data?.items) ? data.items : [];
  const { page = 1, page_size = 20, total = 0, total_pages = 1 } = data ?? {};
  const canDeleteOne = Boolean(accessToken && canEditLead(userRole));
  const canDeleteAll = Boolean(accessToken && userRole === 'platform_admin');
  const hasFilters = Array.from(searchParams.keys()).some((key) => !['page', 'page_size'].includes(key));

  const formatDate = (value?: string | null) => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'America/Bogota' });
  };

  const runDelete = async () => {
    if (!deleteDialog || !accessToken) return;
    const pending = deleteDialog;
    setDeleteDialog(null);
    const result = pending.type === 'all' ? await deleteAllCrmLeads(accessToken) : await deleteCrmLead(accessToken, pending.leadId);
    if (!result.ok) return setFeedback({ kind: 'error', text: result.detail });
    setFeedback({ kind: 'success', text: pending.type === 'all' ? 'Todos los leads fueron eliminados.' : 'Lead eliminado con éxito.' });
    startTransition(() => router.refresh());
  };

  const changePage = (nextPage: number) => {
    if (nextPage < 1 || nextPage > total_pages) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set('page', String(nextPage));
    router.push(`${pathname}?${params}`);
  };

  return (
    <section aria-labelledby="leads-results-title" className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div><h2 id="leads-results-title" className="text-lg font-semibold">Leads encontrados</h2><p className="text-sm text-muted-foreground">{total} registros</p></div>
        {canDeleteAll && total > 0 ? <button type="button" onClick={() => setDeleteDialog({ type: 'all' })} className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-[var(--radius-control)] border border-destructive/30 px-3 text-sm font-medium text-destructive hover:bg-destructive/10"><Trash2 aria-hidden="true" className="size-4" />Eliminar todos</button> : null}
      </div>

      {(feedback || isPending) ? <div role="status" className={`fixed bottom-5 right-5 z-50 max-w-sm rounded-[var(--radius-control)] border bg-card p-4 text-sm shadow-lg ${feedback?.kind === 'error' ? 'text-destructive' : 'text-foreground'}`}>{isPending ? 'Actualizando datos…' : feedback?.text}</div> : null}

      {items.length === 0 ? (
        <div className="rounded-[var(--radius-card)] border border-dashed border-border bg-card px-6 py-14 text-center">
          <ShieldAlert aria-hidden="true" className="mx-auto size-8 text-muted-foreground" />
          <h3 className="mt-3 font-semibold">{hasFilters ? 'No hay resultados para estos filtros' : 'Todavía no hay leads'}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{hasFilters ? 'Prueba modificando la búsqueda o limpiando los filtros.' : 'Los leads aparecerán aquí cuando estén disponibles.'}</p>
          {hasFilters ? <button type="button" onClick={() => router.push(pathname)} className="mt-4 h-10 rounded-[var(--radius-control)] border border-border px-4 text-sm font-semibold hover:bg-muted">Limpiar filtros</button> : null}
        </div>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-[var(--radius-card)] border border-border bg-card lg:block">
            <div className="max-w-full overflow-x-auto">
              <table className="w-full min-w-[850px] text-left text-sm">
                <thead className="sticky top-16 z-10 bg-muted text-xs text-muted-foreground"><tr><th scope="col" className="px-4 py-3">Contacto</th><th scope="col" className="px-4 py-3">Etapa</th><th scope="col" className="px-4 py-3">Estado</th><th scope="col" className="px-4 py-3">Origen</th><th scope="col" className="px-4 py-3">Actualizado</th><th scope="col" className="px-4 py-3 text-right">Acciones</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {items.map((lead) => (
                    <tr key={lead.lead_id} className="h-[var(--row-height)] hover:bg-muted/50">
                      <td className="max-w-xs px-4 py-3"><Link href={`/${locale}/crm/leads/${lead.lead_id}`} className="font-semibold hover:text-[hsl(var(--brand))] hover:underline">{lead.contact_name}</Link><p className="truncate text-xs text-muted-foreground">{lead.company || 'Sin empresa registrada'}</p><p className="truncate text-xs text-muted-foreground">{[lead.contact_phone, lead.contact_email].filter(Boolean).join(' · ') || 'Sin datos de contacto'}</p></td>
                      <td className="px-4 py-3"><CrmStageBadge stageKey={lead.stage_key} stageName={lead.stage_name} /></td>
                      <td className="px-4 py-3"><CrmStatusBadge status={lead.status} /></td>
                      <td className="max-w-44 px-4 py-3"><p className="truncate text-xs font-medium">{lead.source || 'Sin origen'}</p><p className="truncate text-xs text-muted-foreground">{lead.campaign || 'Sin campaña'}</p></td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs"><p>{formatDate(lead.last_activity_at || lead.updated_at)}</p><p className="text-muted-foreground">{lead.last_activity_at ? 'Actividad' : 'Actualización'}</p></td>
                      <td className="px-4 py-3 text-right"><details className="relative inline-block text-left"><summary aria-label={`Acciones para ${lead.contact_name}`} className="inline-flex size-10 cursor-pointer list-none items-center justify-center rounded-[var(--radius-control)] hover:bg-muted"><MoreHorizontal aria-hidden="true" className="size-5" /></summary><div className="absolute right-0 z-20 mt-1 w-40 rounded-[var(--radius-control)] border border-border bg-popover p-1 shadow-lg"><Link href={`/${locale}/crm/leads/${lead.lead_id}`} className="flex min-h-10 items-center rounded px-3 text-sm hover:bg-muted">Ver detalle</Link>{canDeleteOne ? <button type="button" onClick={() => setDeleteDialog({ type: 'one', leadId: lead.lead_id })} className="flex min-h-10 w-full items-center gap-2 rounded px-3 text-sm text-destructive hover:bg-destructive/10"><Trash2 aria-hidden="true" className="size-4" />Eliminar</button> : null}</div></details></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="grid gap-3 lg:hidden">{items.map((lead) => <CrmMobileLeadCard key={lead.lead_id} lead={lead} locale={locale} canDelete={canDeleteOne} onDelete={() => setDeleteDialog({ type: 'one', leadId: lead.lead_id })} formatDate={formatDate} />)}</div>
        </>
      )}

      {total > 0 ? <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-muted-foreground">Mostrando <strong className="text-foreground">{(page - 1) * page_size + 1}–{Math.min(page * page_size, total)}</strong> de <strong className="text-foreground">{total}</strong></p><div className="flex items-center justify-between gap-3"><span className="text-xs text-muted-foreground">Página {page} de {total_pages}</span><button type="button" onClick={() => changePage(page - 1)} disabled={page <= 1} aria-label={`Ir a la página anterior, página ${page - 1}`} className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] border border-border disabled:opacity-40"><ChevronLeft aria-hidden="true" className="size-4" /></button><button type="button" onClick={() => changePage(page + 1)} disabled={page >= total_pages} aria-label={`Ir a la página siguiente, página ${page + 1}`} className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] border border-border disabled:opacity-40"><ChevronRight aria-hidden="true" className="size-4" /></button></div></div> : null}

      <Dialog open={deleteDialog !== null} onOpenChange={(open) => !open && setDeleteDialog(null)}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>{deleteDialog?.type === 'all' ? 'Eliminar todos los leads' : 'Eliminar lead'}</DialogTitle><DialogDescription>{deleteDialog?.type === 'all' ? 'Esta acción eliminará permanentemente todos los contactos, leads, tareas e historial de actividades.' : 'Esta acción eliminará este lead junto con sus tareas y actividades.'}</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" onClick={() => setDeleteDialog(null)}>Cancelar</Button><Button variant="destructive" onClick={runDelete}>Eliminar</Button></DialogFooter></DialogContent></Dialog>
    </section>
  );
}
