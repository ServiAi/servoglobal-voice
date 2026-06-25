'use client';

import React, { useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import type { LeadsListResponse } from '@/types/crm';
import { ChevronLeft, ChevronRight, Eye, Calendar, User, Phone, Mail, Trash2, Trash, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { deleteCrmLead, deleteAllCrmLeads } from '@/lib/api/crm';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type CrmLeadsTableProps = {
  data: LeadsListResponse;
  locale: string;
  accessToken?: string;
  userRole?: string;
};

const STAGE_TRANSLATIONS: Record<string, string> = {
  new: 'Nuevo',
  contacted: 'Contactado',
  connected: 'Conectado',
  qualified: 'Calificado',
  scheduled: 'Agendado',
  voicemail: 'Buzón de voz',
  follow_up: 'En seguimiento',
  not_interested: 'No Interesado',
  won: 'Ganado',
  lost: 'Perdido',
};

const STAGE_BADGES: Record<string, string> = {
  new: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  contacted: 'bg-sky-500/10 text-sky-500 border-sky-500/20',
  connected: 'bg-cyan-500/10 text-cyan-500 border-cyan-500/20',
  qualified: 'bg-violet-500/10 text-violet-500 border-violet-500/20',
  scheduled: 'bg-fuchsia-500/10 text-fuchsia-500 border-fuchsia-500/20',
  voicemail: 'bg-indigo-500/10 text-indigo-500 border-indigo-500/20',
  follow_up: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  not_interested: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  won: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  lost: 'bg-red-500/10 text-red-500 border-red-500/20',
};

export function CrmLeadsTable({ data, locale, accessToken, userRole }: CrmLeadsTableProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<
    { type: 'one'; leadId: string } | { type: 'all' } | null
  >(null);

  const handleDeleteOne = async (leadId: string) => {
    if (!accessToken) return;

    setError(null);
    setSuccessMsg(null);
    try {
      const res = await deleteCrmLead(accessToken, leadId);
      if (res.ok) {
        setSuccessMsg('Lead eliminado con éxito.');
        startTransition(() => {
          router.refresh();
        });
        setTimeout(() => setSuccessMsg(null), 3000);
      } else {
        setError(`Error al eliminar lead: ${res.detail}`);
      }
    } catch (err) {
      console.error(err);
      setError('Ocurrió un error inesperado al eliminar el lead.');
    }
  };

  const handleDeleteAll = async () => {
    if (!accessToken) return;

    setError(null);
    setSuccessMsg(null);
    try {
      const res = await deleteAllCrmLeads(accessToken);
      if (res.ok) {
        setSuccessMsg('Todos los leads fueron eliminados.');
        startTransition(() => {
          router.refresh();
        });
        setTimeout(() => setSuccessMsg(null), 3000);
      } else {
        setError(`Error al eliminar leads: ${res.detail}`);
      }
    } catch (err) {
      console.error(err);
      setError('Ocurrió un error inesperado al eliminar todos los leads.');
    }
  };

  const handleConfirmDelete = async () => {
    const pendingDelete = deleteDialog;
    if (!pendingDelete) return;

    setDeleteDialog(null);
    if (pendingDelete.type === 'all') {
      await handleDeleteAll();
      return;
    }

    await handleDeleteOne(pendingDelete.leadId);
  };

  const items = Array.isArray(data?.items) ? data.items : [];
  const { page = 1, page_size = 20, total = 0, total_pages = 1 } = data ?? {};
  const currentStart = total === 0 ? 0 : (page - 1) * page_size + 1;
  const currentEnd = Math.min(page * page_size, total);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > total_pages) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set('page', newPage.toString());
    router.push(`${pathname}?${params.toString()}`);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'open':
        return <span className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-0.5 text-2xs font-semibold text-blue-500 border border-blue-500/20">Abierto</span>;
      case 'won':
        return <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-2xs font-semibold text-emerald-500 border border-emerald-500/20">Ganado</span>;
      case 'lost':
        return <span className="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-2xs font-semibold text-destructive border border-destructive/20">Perdido</span>;
      case 'unqualified':
        return <span className="inline-flex items-center rounded-full bg-orange-500/10 px-2 py-0.5 text-2xs font-semibold text-orange-500 border border-orange-500/20">Descalificado</span>;
      case 'paused':
        return <span className="inline-flex items-center rounded-full bg-zinc-500/10 px-2 py-0.5 text-2xs font-semibold text-zinc-400 border border-zinc-500/20">Pausado</span>;
      default:
        return <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-2xs font-semibold text-muted-foreground border border-border">{status}</span>;
    }
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleDateString('es-ES', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden shadow-xs relative">
      {/* Toast Alert Feedback */}
      {(error || successMsg || isPending) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span>Actualizando datos...</span>
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

      <div className="p-5 border-b border-border flex flex-row items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-foreground">Leads Encontrados</h3>
          <span className="text-xs text-muted-foreground">Total: {total}</span>
        </div>
        {total > 0 && accessToken && userRole === 'platform_admin' && (
          <button
            onClick={() => setDeleteDialog({ type: 'all' })}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-bold text-red-500 hover:bg-red-500/20 shadow-2xs transition cursor-pointer"
            type="button"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Eliminar todos los leads
          </button>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-muted-foreground">
          <thead className="bg-muted/50 text-2xs uppercase text-muted-foreground">
            <tr>
              <th scope="col" className="px-6 py-4 font-semibold">Contacto</th>
              <th scope="col" className="px-6 py-4 font-semibold">Empresa</th>
              <th scope="col" className="px-6 py-4 font-semibold font-mono">Teléfono</th>
              <th scope="col" className="px-6 py-4 font-semibold">Email</th>
              <th scope="col" className="px-6 py-4 font-semibold">Etapa</th>
              <th scope="col" className="px-6 py-4 font-semibold">Estado</th>
              <th scope="col" className="px-6 py-4 font-semibold">Interés</th>
              <th scope="col" className="px-6 py-4 font-semibold">Origen</th>
              <th scope="col" className="px-6 py-4 font-semibold">Fecha Registro</th>
              <th scope="col" className="px-6 py-4 font-semibold text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-6 py-16 text-center text-sm text-muted-foreground">
                  No se encontraron leads con los filtros seleccionados.
                </td>
              </tr>
            ) : (
              items.map((lead) => (
                <tr key={lead.lead_id} className="transition-colors hover:bg-muted/30">
                  {/* Name */}
                  <td className="whitespace-nowrap px-6 py-4 font-semibold text-foreground flex items-center gap-1.5">
                    <User className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
                    <span className="truncate max-w-[150px]">{lead.contact_name}</span>
                  </td>
                  {/* Company */}
                  <td className="whitespace-nowrap px-6 py-4 text-foreground truncate max-w-[120px]">
                    {lead.company || <span className="text-muted-foreground/45">-</span>}
                  </td>
                  {/* Phone */}
                  <td className="whitespace-nowrap px-6 py-4 font-mono text-xs">
                    {lead.contact_phone ? (
                      <span className="flex items-center gap-1.5">
                        <Phone className="h-3 w-3 text-zinc-500" />
                        {lead.contact_phone}
                      </span>
                    ) : (
                      <span className="text-muted-foreground/45">-</span>
                    )}
                  </td>
                  {/* Email */}
                  <td className="whitespace-nowrap px-6 py-4 truncate max-w-[160px]">
                    {lead.contact_email ? (
                      <span className="flex items-center gap-1.5 truncate">
                        <Mail className="h-3 w-3 text-zinc-500 shrink-0" />
                        <span className="truncate">{lead.contact_email}</span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground/45">-</span>
                    )}
                  </td>
                  {/* Stage */}
                  <td className="whitespace-nowrap px-6 py-4">
                    <span className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-2xs font-semibold border',
                      STAGE_BADGES[lead.stage_key] || 'bg-muted text-muted-foreground'
                    )}>
                      {STAGE_TRANSLATIONS[lead.stage_key] || lead.stage_name}
                    </span>
                  </td>
                  {/* Status */}
                  <td className="whitespace-nowrap px-6 py-4">
                    {getStatusBadge(lead.status)}
                  </td>
                  {/* Interest */}
                  <td className="whitespace-nowrap px-6 py-4 text-xs">
                    {lead.interest || <span className="text-muted-foreground/45">-</span>}
                  </td>
                  {/* Source */}
                  <td className="whitespace-nowrap px-6 py-4 text-xs font-semibold uppercase text-zinc-500">
                    {lead.source || '-'}
                  </td>
                  {/* Created At */}
                  <td className="whitespace-nowrap px-6 py-4 text-xs flex items-center gap-1.5 mt-1.5">
                    <Calendar className="h-3.5 w-3.5 text-zinc-500" />
                    <span>{formatDate(lead.created_at)}</span>
                  </td>
                  {/* Actions */}
                  <td className="whitespace-nowrap px-6 py-4 text-right flex items-center justify-end gap-2">
                    <Link
                      href={`/${locale}/crm/leads/${lead.lead_id}`}
                      className="inline-flex items-center justify-center gap-1.5 rounded-md bg-violet-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-violet-500 shadow-sm transition"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Detalle
                    </Link>
                    {accessToken && (userRole === 'platform_admin' || userRole === 'tenant_admin') && (
                      <button
                        onClick={() => setDeleteDialog({ type: 'one', leadId: lead.lead_id })}
                        className="inline-flex items-center justify-center rounded-md border border-red-500/30 bg-red-500/10 p-2 text-red-500 hover:bg-red-500/20 shadow-sm transition cursor-pointer"
                        title="Eliminar lead"
                        type="button"
                      >
                        <Trash className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <div className="flex flex-col gap-3 border-t border-border px-6 py-4 sm:flex-row sm:items-center sm:justify-between bg-muted/10">
        <p className="text-sm text-muted-foreground">
          Mostrando <span className="font-semibold text-foreground">{currentStart}</span>-
          <span className="font-semibold text-foreground">{currentEnd}</span> de{' '}
          <span className="font-semibold text-foreground">{total}</span> leads
        </p>
        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <p className="text-xs text-muted-foreground">
            Página <span className="font-semibold text-foreground">{page}</span> de{' '}
            <span className="font-semibold text-foreground">{total_pages}</span>
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted disabled:pointer-events-none disabled:opacity-50 transition"
              aria-label="Página anterior"
              type="button"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= total_pages}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted disabled:pointer-events-none disabled:opacity-50 transition"
              aria-label="Página siguiente"
              type="button"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      <Dialog open={deleteDialog !== null} onOpenChange={(open) => !open && setDeleteDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-red-500/10 text-red-500">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <DialogTitle className="text-center">
              {deleteDialog?.type === 'all' ? 'Eliminar todos los leads' : 'Eliminar lead'}
            </DialogTitle>
            <DialogDescription className="text-center">
              {deleteDialog?.type === 'all'
                ? 'Esta acción eliminará permanentemente todos los contactos, leads, tareas e historial de actividades.'
                : 'Esta acción eliminará este lead junto con sus tareas y actividades.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:justify-center">
            <Button type="button" variant="outline" onClick={() => setDeleteDialog(null)}>
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
