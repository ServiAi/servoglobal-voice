'use client';

import React, { useState, useCallback } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { Search, Filter, X } from 'lucide-react';

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

const STAGES = Object.entries(STAGE_TRANSLATIONS).map(([key, name]) => ({ key, name }));

function toDateInputValue(value: string) {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : '';
}

function toStartOfDayUtc(date: string) {
  return date ? `${date}T00:00:00Z` : '';
}

function toEndOfDayUtc(date: string) {
  return date ? `${date}T23:59:59Z` : '';
}

export function CrmLeadFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Local state for the filter fields
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [stageKey, setStageKey] = useState(searchParams.get('stage_key') || '');
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [source, setSource] = useState(searchParams.get('source') || '');
  const [campaign, setCampaign] = useState(searchParams.get('campaign') || '');
  const [hasPhone, setHasPhone] = useState(searchParams.get('has_phone') || '');
  const [hasEmail, setHasEmail] = useState(searchParams.get('has_email') || '');
  const [sortBy, setSortBy] = useState(searchParams.get('sort_by') || 'updated_at');
  const [sortOrder, setSortOrder] = useState(searchParams.get('sort_order') || 'desc');
  const [dateFrom, setDateFrom] = useState(toDateInputValue(searchParams.get('date_from') || ''));
  const [dateTo, setDateTo] = useState(toDateInputValue(searchParams.get('date_to') || ''));

  const createQueryString = useCallback(
    (params: Record<string, string>) => {
      const newSearchParams = new URLSearchParams(searchParams.toString());
      // Reset page when filters change
      newSearchParams.delete('page');

      Object.entries(params).forEach(([name, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          newSearchParams.set(name, value);
        } else {
          newSearchParams.delete(name);
        }
      });

      return newSearchParams.toString();
    },
    [searchParams]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(
      `${pathname}?${createQueryString({
        search,
        stage_key: stageKey,
        status,
        source,
        campaign,
        has_phone: hasPhone,
        has_email: hasEmail,
        sort_by: sortBy,
        sort_order: sortOrder,
        date_from: toStartOfDayUtc(dateFrom),
        date_to: toEndOfDayUtc(dateTo),
      })}`
    );
  };

  const handleReset = () => {
    setSearch('');
    setStageKey('');
    setStatus('');
    setSource('');
    setCampaign('');
    setHasPhone('');
    setHasEmail('');
    setSortBy('updated_at');
    setSortOrder('desc');
    setDateFrom('');
    setDateTo('');
    router.push(pathname);
  };

  return (
    <div className="rounded-xl border border-border bg-card/65 p-5 shadow-xs">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider pb-2 border-b border-border/60">
          <Filter className="h-4 w-4 text-violet-500" />
          <span>Filtros Avanzados</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Search bar */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="search" className="text-xs font-medium text-muted-foreground">
              Buscar contacto / empresa
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                type="text"
                id="search"
                placeholder="Nombre, teléfono..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-md border border-border bg-zinc-950/40 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
              />
            </div>
          </div>

          {/* Stage Key select */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="stageKey" className="text-xs font-medium text-muted-foreground">
              Etapa del embudo
            </label>
            <select
              id="stageKey"
              value={stageKey}
              onChange={(e) => setStageKey(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            >
              <option value="">Todas las etapas</option>
              {STAGES.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {/* Status select */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="status" className="text-xs font-medium text-muted-foreground">
              Estado del lead
            </label>
            <select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            >
              <option value="">Todos los estados</option>
              <option value="open">Abierto</option>
              <option value="won">Ganado</option>
              <option value="lost">Perdido</option>
              <option value="unqualified">Descalificado</option>
              <option value="paused">Pausado</option>
            </select>
          </div>

          {/* Source input */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="source" className="text-xs font-medium text-muted-foreground">
              Origen (Source)
            </label>
            <input
              type="text"
              id="source"
              placeholder="Ej: web, ultravox"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            />
          </div>

          {/* Campaign input */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="campaign" className="text-xs font-medium text-muted-foreground">
              Campaña
            </label>
            <input
              type="text"
              id="campaign"
              placeholder="Ej: ads_facebook"
              value={campaign}
              onChange={(e) => setCampaign(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            />
          </div>

          {/* Contact filtering checkboxes */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="hasPhone" className="text-xs font-medium text-muted-foreground">
              Tiene Teléfono
            </label>
            <select
              id="hasPhone"
              value={hasPhone}
              onChange={(e) => setHasPhone(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            >
              <option value="">Cualquiera</option>
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="hasEmail" className="text-xs font-medium text-muted-foreground">
              Tiene Email
            </label>
            <select
              id="hasEmail"
              value={hasEmail}
              onChange={(e) => setHasEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
            >
              <option value="">Cualquiera</option>
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          </div>

          {/* Date From */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="dateFrom" className="text-xs font-medium text-muted-foreground">
              Fecha desde
            </label>
            <input
              type="date"
              id="dateFrom"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all cursor-pointer"
            />
          </div>

          {/* Date To */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="dateTo" className="text-xs font-medium text-muted-foreground">
              Fecha hasta
            </label>
            <input
              type="date"
              id="dateTo"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all cursor-pointer"
            />
          </div>

          {/* Sorting */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Ordenar por
            </label>
            <div className="flex gap-2">
              <select
                id="sortBy"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="w-2/3 rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
              >
                <option value="updated_at">Última actualización</option>
                <option value="created_at">Fecha de registro</option>
                <option value="contact_name">Nombre de contacto</option>
                <option value="lead_score">Lead Score</option>
              </select>
              <select
                id="sortOrder"
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
                className="w-1/3 rounded-md border border-border bg-zinc-950/40 py-2 px-3 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
              >
                <option value="desc">Desc</option>
                <option value="asc">Asc</option>
              </select>
            </div>
          </div>
        </div>

        {/* Buttons */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground transition-all"
          >
            <X className="h-3.5 w-3.5" />
            Limpiar
          </button>
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-5 py-2 text-xs font-bold text-white hover:bg-violet-500 transition-all shadow-md shadow-violet-500/10"
          >
            Aplicar Filtros
          </button>
        </div>
      </form>
    </div>
  );
}
