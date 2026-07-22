'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { Filter, Search, SlidersHorizontal, X } from 'lucide-react';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { CRM_STAGES, CRM_STATUSES, getStageLabel, getStatusLabel } from './config/crm-display';

const ADVANCED_FILTERS = ['source', 'campaign', 'has_phone', 'has_email', 'date_from', 'date_to', 'sort_by', 'sort_order'] as const;
const FILTER_LABELS: Record<string, string> = {
  search: 'Búsqueda',
  stage_key: 'Etapa',
  status: 'Estado',
  source: 'Origen',
  campaign: 'Campaña',
  has_phone: 'Teléfono',
  has_email: 'Correo',
  date_from: 'Desde',
  date_to: 'Hasta',
  sort_by: 'Orden',
  sort_order: 'Dirección',
};

function toDateInputValue(value: string) {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : '';
}

function displayValue(key: string, value: string) {
  if (key === 'stage_key') return getStageLabel(value);
  if (key === 'status') return getStatusLabel(value);
  if (key === 'has_phone' || key === 'has_email') return value === 'true' ? 'Sí' : 'No';
  if (key === 'sort_by') return { created_at: 'Fecha de registro', contact_name: 'Contacto', lead_score: 'Score' }[value] ?? 'Actualización';
  if (key === 'sort_order') return value === 'asc' ? 'Ascendente' : 'Descendente';
  return value;
}

export function CrmLeadFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const formId = useId();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const queryKey = searchParams.toString();
  const advancedCount = ADVANCED_FILTERS.filter((key) => {
    const value = searchParams.get(key);
    return Boolean(value && !((key === 'sort_by' && value === 'updated_at') || (key === 'sort_order' && value === 'desc')));
  }).length;
  const activeFilters = Array.from(searchParams.entries()).filter(([key, value]) =>
    Boolean(FILTER_LABELS[key] && value && key !== 'page' && key !== 'page_size' && !((key === 'sort_by' && value === 'updated_at') || (key === 'sort_order' && value === 'desc')))
  );

  const navigate = (params: URLSearchParams) => {
    params.delete('page');
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const params = new URLSearchParams(searchParams.toString());
    Object.keys(FILTER_LABELS).forEach((key) => params.delete(key));

    data.forEach((rawValue, key) => {
      const value = String(rawValue).trim();
      if (!value) return;
      if (key === 'date_from') params.set(key, `${value}T00:00:00Z`);
      else if (key === 'date_to') params.set(key, `${value}T23:59:59Z`);
      else if (!((key === 'sort_by' && value === 'updated_at') || (key === 'sort_order' && value === 'desc'))) params.set(key, value);
    });
    setAdvancedOpen(false);
    navigate(params);
  };

  const removeFilter = (key: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete(key);
    navigate(params);
  };

  return (
    <div className="space-y-3">
      <form id={formId} key={queryKey} onSubmit={handleSubmit} className="rounded-[var(--radius-card)] border border-border bg-card p-3 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(16rem,1fr)_12rem_12rem_auto_auto]">
          <label className="relative sm:col-span-2 xl:col-span-1">
            <span className="sr-only">Buscar leads</span>
            <Search aria-hidden="true" className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input name="search" defaultValue={searchParams.get('search') ?? ''} placeholder="Buscar leads..." className="h-[var(--control-height)] w-full rounded-[var(--radius-control)] border border-input bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground" />
          </label>
          <label>
            <span className="sr-only">Etapa</span>
            <select name="stage_key" defaultValue={searchParams.get('stage_key') ?? ''} className="h-[var(--control-height)] w-full rounded-[var(--radius-control)] border border-input bg-background px-3 text-sm">
              <option value="">Todas las etapas</option>
              {CRM_STAGES.map((stage) => <option key={stage.key} value={stage.key}>{stage.label}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Estado</span>
            <select name="status" defaultValue={searchParams.get('status') ?? ''} className="h-[var(--control-height)] w-full rounded-[var(--radius-control)] border border-input bg-background px-3 text-sm">
              <option value="">Todos los estados</option>
              {CRM_STATUSES.map((status) => <option key={status.key} value={status.key}>{status.label}</option>)}
            </select>
          </label>
          <Dialog.Root open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <Dialog.Trigger asChild>
              <button type="button" className="inline-flex h-[var(--control-height)] items-center justify-center gap-2 rounded-[var(--radius-control)] border border-border px-3 text-sm font-medium hover:bg-muted">
                <SlidersHorizontal aria-hidden="true" className="size-4" /> Más filtros
                {advancedCount > 0 ? <span className="rounded-full bg-[hsl(var(--brand))] px-2 py-0.5 text-xs text-[hsl(var(--brand-foreground))]">{advancedCount}</span> : null}
              </button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-50 bg-[hsl(var(--overlay)/0.62)]" />
              <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(25rem,100vw)] overflow-y-auto border-l border-border bg-background p-5 shadow-xl">
                <div className="mb-6 flex items-start justify-between gap-4">
                  <div><Dialog.Title className="font-semibold">Filtros avanzados</Dialog.Title><Dialog.Description className="mt-1 text-sm text-muted-foreground">Refina el listado sin perder los filtros principales.</Dialog.Description></div>
                  <Dialog.Close aria-label="Cerrar filtros" className="inline-flex size-10 items-center justify-center rounded-[var(--radius-control)] hover:bg-muted"><X aria-hidden="true" className="size-5" /></Dialog.Close>
                </div>
                <div className="space-y-4">
                  <FilterField label="Origen"><input form={formId} name="source" defaultValue={searchParams.get('source') ?? ''} placeholder="Ej. web" className="crm-filter-control" /></FilterField>
                  <FilterField label="Campaña"><input form={formId} name="campaign" defaultValue={searchParams.get('campaign') ?? ''} placeholder="Ej. demo-crm" className="crm-filter-control" /></FilterField>
                  <FilterField label="Tiene teléfono"><select form={formId} name="has_phone" defaultValue={searchParams.get('has_phone') ?? ''} className="crm-filter-control"><option value="">Cualquiera</option><option value="true">Sí</option><option value="false">No</option></select></FilterField>
                  <FilterField label="Tiene correo"><select form={formId} name="has_email" defaultValue={searchParams.get('has_email') ?? ''} className="crm-filter-control"><option value="">Cualquiera</option><option value="true">Sí</option><option value="false">No</option></select></FilterField>
                  <div className="grid grid-cols-2 gap-3">
                    <FilterField label="Desde"><input form={formId} name="date_from" type="date" defaultValue={toDateInputValue(searchParams.get('date_from') ?? '')} className="crm-filter-control" /></FilterField>
                    <FilterField label="Hasta"><input form={formId} name="date_to" type="date" defaultValue={toDateInputValue(searchParams.get('date_to') ?? '')} className="crm-filter-control" /></FilterField>
                  </div>
                  <FilterField label="Ordenar por"><select form={formId} name="sort_by" defaultValue={searchParams.get('sort_by') ?? 'updated_at'} className="crm-filter-control"><option value="updated_at">Última actualización</option><option value="created_at">Fecha de registro</option><option value="contact_name">Contacto</option><option value="lead_score">Lead score</option></select></FilterField>
                  <FilterField label="Dirección"><select form={formId} name="sort_order" defaultValue={searchParams.get('sort_order') ?? 'desc'} className="crm-filter-control"><option value="desc">Descendente</option><option value="asc">Ascendente</option></select></FilterField>
                </div>
                <div className="sticky bottom-0 mt-6 flex gap-2 border-t border-border bg-background pt-4">
                  <button type="button" onClick={() => router.push(pathname)} className="h-10 flex-1 rounded-[var(--radius-control)] border border-border text-sm font-medium hover:bg-muted">Limpiar</button>
                  <button type="submit" form={formId} className="h-10 flex-1 rounded-[var(--radius-control)] bg-[hsl(var(--brand))] text-sm font-semibold text-[hsl(var(--brand-foreground))]">Aplicar</button>
                </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <button type="submit" className="inline-flex h-[var(--control-height)] items-center justify-center gap-2 rounded-[var(--radius-control)] bg-[hsl(var(--brand))] px-4 text-sm font-semibold text-[hsl(var(--brand-foreground))]">
            <Filter aria-hidden="true" className="size-4" /> Aplicar
          </button>
        </div>
      </form>

      {activeFilters.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtros activos">
          {activeFilters.map(([key, value]) => (
            <span key={key} className="inline-flex min-h-8 items-center gap-1 rounded-full border border-border bg-muted px-3 text-xs font-medium">
              {FILTER_LABELS[key]}: {displayValue(key, value)}
              <button type="button" onClick={() => removeFilter(key)} aria-label={`Quitar filtro ${FILTER_LABELS[key]}`} className="ml-1 inline-flex size-6 items-center justify-center rounded-full hover:bg-background"><X aria-hidden="true" className="size-3" /></button>
            </span>
          ))}
          <button type="button" onClick={() => router.push(pathname)} className="min-h-8 px-2 text-xs font-semibold text-[hsl(var(--brand))] hover:underline">Limpiar todos</button>
        </div>
      ) : null}
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-1.5 text-xs font-medium text-muted-foreground"><span>{label}</span>{children}</label>;
}
