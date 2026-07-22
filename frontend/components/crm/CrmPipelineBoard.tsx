'use client';

import { useMemo, useState } from 'react';
import { FilterX, Search } from 'lucide-react';
import type { PipelineBoardResponse, PipelineStageLeads } from '@/types/crm';
import { CrmLeadCard } from './CrmLeadCard';
import { CrmStageBadge } from './shared/CrmStageBadge';

type Props = {
  boardData: PipelineBoardResponse;
  locale: string;
  onLeadStageChange: (leadId: string, newStageKey: string) => Promise<boolean>;
};

export function CrmPipelineBoard({ boardData, locale, onLeadStageChange }: Props) {
  const stages = useMemo(() => [...boardData.stages].sort((a, b) => a.position - b.position), [boardData.stages]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [mobileStage, setMobileStage] = useState(stages[0]?.key ?? '');
  const normalizedSearch = search.trim().toLocaleLowerCase('es');
  const activeFilters = Number(Boolean(normalizedSearch)) + Number(Boolean(status));

  const filteredStages = useMemo(() => stages.map((stage) => ({
    ...stage,
    leads: stage.leads.filter((lead) => {
      const matchesSearch = !normalizedSearch || `${lead.contact_name} ${lead.company ?? ''}`.toLocaleLowerCase('es').includes(normalizedSearch);
      return matchesSearch && (!status || lead.status === status);
    }),
  })), [stages, normalizedSearch, status]);

  const totalLeads = stages.reduce((total, stage) => total + stage.count, 0);
  const visibleLeads = filteredStages.reduce((total, stage) => total + stage.leads.length, 0);
  const selectedStage = filteredStages.find((stage) => stage.key === mobileStage) ?? filteredStages[0];
  const stageOptions = stages.map(({ key, name }) => ({ key, name }));

  if (!stages.length) {
    return <PipelineEmpty title="Pipeline no disponible" description="No hay etapas configuradas para mostrar oportunidades." />;
  }
  if (!totalLeads) {
    return <PipelineEmpty title="Pipeline vacío" description="Las etapas están configuradas, pero todavía no hay Leads para mostrar." />;
  }

  return (
    <section className="min-w-0 space-y-5" aria-labelledby="pipeline-title">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="pipeline-title" className="text-xl font-semibold tracking-tight text-foreground">Pipeline de oportunidades</h2>
          <p className="mt-1 text-sm text-muted-foreground">Mueve cada Lead mediante su menú de etapa.</p>
        </div>
        <dl className="flex gap-4 text-sm">
          <div><dt className="text-xs text-muted-foreground">Leads</dt><dd className="font-semibold">{totalLeads}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Etapas</dt><dd className="font-semibold">{stages.length}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Filtros</dt><dd className="font-semibold">{activeFilters}</dd></div>
        </dl>
      </header>

      <div className="rounded-xl border border-border bg-card p-3 sm:p-4">
        <div className="grid gap-3 md:grid-cols-[minmax(220px,1fr)_200px_auto]">
          <label className="relative block">
            <span className="sr-only">Buscar por nombre o empresa</span>
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar nombre o empresa" className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          </label>
          <label>
            <span className="sr-only">Filtrar por estado</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <option value="">Todos los estados</option><option value="open">Abierto</option><option value="won">Ganado</option><option value="lost">Perdido</option><option value="unqualified">Descalificado</option><option value="paused">Pausado</option>
            </select>
          </label>
          <button type="button" onClick={() => { setSearch(''); setStatus(''); }} disabled={!activeFilters} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"><FilterX className="size-4" />Limpiar</button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Los filtros se aplican a las tarjetas cargadas en esta vista.</p>
      </div>

      {activeFilters && visibleLeads === 0 ? (
        <PipelineEmpty title="Sin coincidencias" description="No hay Leads cargados que coincidan con los filtros actuales." action={<button type="button" onClick={() => { setSearch(''); setStatus(''); }} className="mt-3 min-h-10 rounded-md border border-border px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Limpiar filtros</button>} />
      ) : (
        <>
          <div className="hidden max-w-full gap-4 overflow-x-auto pb-4 md:flex" aria-label="Tablero kanban">
            {filteredStages.map((stage) => <PipelineColumn key={stage.id} stage={stage} stages={stageOptions} locale={locale} onStageChange={onLeadStageChange} filtered={Boolean(activeFilters)} />)}
          </div>

          <div className="space-y-4 md:hidden">
            <label className="block space-y-1"><span className="text-xs font-medium text-muted-foreground">Etapa visible</span><select value={selectedStage?.key ?? ''} onChange={(event) => setMobileStage(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">{filteredStages.map((stage) => <option key={stage.key} value={stage.key}>{stage.name} · {stage.leads.length}</option>)}</select></label>
            {selectedStage ? <PipelineColumn stage={selectedStage} stages={stageOptions} locale={locale} onStageChange={onLeadStageChange} filtered={Boolean(activeFilters)} mobile /> : null}
          </div>
        </>
      )}
    </section>
  );
}

function PipelineColumn({ stage, stages, locale, onStageChange, filtered, mobile = false }: { stage: PipelineStageLeads; stages: Array<{ key: string; name: string }>; locale: string; onStageChange: Props['onLeadStageChange']; filtered: boolean; mobile?: boolean }) {
  return <section className={mobile ? 'w-full' : 'w-[300px] shrink-0'} aria-labelledby={`pipeline-stage-${stage.id}`}><div className="mb-3 flex min-h-10 items-center justify-between rounded-lg border border-border bg-card px-3"><div id={`pipeline-stage-${stage.id}`}><CrmStageBadge stageKey={stage.key} stageName={stage.name} /></div><span className="text-xs font-semibold text-muted-foreground" aria-label={`${stage.leads.length} Leads visibles`}>{stage.leads.length}{!filtered && stage.count !== stage.leads.length ? ` / ${stage.count}` : ''}</span></div><div className="min-h-64 space-y-3 rounded-xl border border-border/70 bg-muted/20 p-2">{stage.leads.length ? stage.leads.map((lead) => <CrmLeadCard key={lead.id} lead={lead} locale={locale} stages={stages} onStageChange={onStageChange} currentStageKey={stage.key} />) : <PipelineEmpty title={filtered ? 'Sin coincidencias en esta etapa' : 'Etapa vacía'} description={filtered ? 'Ninguna tarjeta cargada coincide aquí.' : 'Todavía no hay Leads en esta etapa.'} compact />}</div></section>;
}

function PipelineEmpty({ title, description, action, compact = false }: { title: string; description: string; action?: React.ReactNode; compact?: boolean }) { return <div className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-border text-center ${compact ? 'min-h-56 p-4' : 'min-h-64 p-8'}`}><p className="text-sm font-semibold text-foreground">{title}</p><p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>{action}</div>; }
