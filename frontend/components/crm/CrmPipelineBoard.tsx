'use client';

import React from 'react';
import type { PipelineBoardResponse } from '@/types/crm';
import { CrmLeadCard } from './CrmLeadCard';
import { cn } from '@/lib/utils';

type CrmPipelineBoardProps = {
  boardData: PipelineBoardResponse;
  locale: string;
  onLeadStageChange: (leadId: string, newStageKey: string) => void;
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

const STAGE_BORDER_COLORS: Record<string, string> = {
  new: 'border-t-blue-500',
  contacted: 'border-t-sky-500',
  connected: 'border-t-cyan-500',
  qualified: 'border-t-violet-500',
  scheduled: 'border-t-fuchsia-500',
  voicemail: 'border-t-indigo-500',
  follow_up: 'border-t-amber-500',
  not_interested: 'border-t-zinc-500',
  won: 'border-t-emerald-500',
  lost: 'border-t-red-500',
};

export function CrmPipelineBoard({
  boardData,
  locale,
  onLeadStageChange,
}: CrmPipelineBoardProps) {
  // Extract stages to pass down for dropdown options
  const stagesList = boardData.stages.map((stg) => ({
    key: stg.key,
    name: STAGE_TRANSLATIONS[stg.key] || stg.name,
  }));

  return (
    <div className="rounded-xl border border-border bg-card/45 p-6 shadow-sm">
      <div className="flex flex-col gap-1 mb-6">
        <h3 className="text-xl font-bold tracking-tight text-foreground">
          Embudo de Ventas (Pipeline)
        </h3>
        <p className="text-sm text-muted-foreground">
          Arrastra o mueve leads de etapa para avanzar en el embudo.
        </p>
      </div>

      {/* Horizontal scrolling lanes container */}
      <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        {boardData.stages.map((stage) => {
          const stageName = STAGE_TRANSLATIONS[stage.key] || stage.name;
          const count = stage.count;
          const leads = Array.isArray(stage.leads) ? stage.leads : [];

          return (
            <div
              key={stage.id}
              className="flex flex-col gap-3 min-w-[280px] max-w-[320px] w-full shrink-0"
            >
              {/* Column Header */}
              <div className={cn(
                'flex items-center justify-between border-t-4 bg-muted/20 px-3 py-2 rounded-md border border-border shadow-xs',
                STAGE_BORDER_COLORS[stage.key] || 'border-t-border'
              )}>
                <span className="text-xs font-bold text-foreground truncate max-w-[70%]">
                  {stageName}
                </span>
                <span className="inline-flex items-center justify-center rounded-full bg-muted/80 px-2 py-0.5 text-2xs font-semibold text-muted-foreground">
                  {count}
                </span>
              </div>

              {/* Cards Container */}
              <div className="flex flex-col gap-3 p-1 min-h-[300px] rounded-lg bg-muted/10 border border-border/30">
                {leads.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center text-2xs text-muted-foreground border border-dashed border-border/40 rounded-lg">
                    Sin leads
                  </div>
                ) : (
                  leads.map((lead) => (
                    <CrmLeadCard
                      key={lead.id}
                      lead={lead}
                      locale={locale}
                      stages={stagesList}
                      onStageChange={onLeadStageChange}
                      currentStageKey={stage.key}
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
