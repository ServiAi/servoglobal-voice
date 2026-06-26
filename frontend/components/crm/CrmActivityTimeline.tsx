'use client';

import React from 'react';
import type { ActivitySchema } from '@/types/crm';
import { Phone, FileText, ArrowRightLeft, PenTool, CheckCircle, HelpCircle, MessageSquare, Calendar, MessageCircle, Mail } from 'lucide-react';
import { cn } from '@/lib/utils';

type CrmActivityTimelineProps = {
  activities: ActivitySchema[];
};

const ACTIVITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  call_started: Phone,
  call_completed: Phone,
  call_joined: Phone,
  call_ended: Phone,
  call_billed: Phone,
  stage_changed: ArrowRightLeft,
  lead_updated: PenTool,
  note: FileText,
  task_completed: CheckCircle,
  task_created: CheckCircle,
  task_updated: PenTool,
  booking_detected: Calendar,
  whatsapp_action_requested: MessageSquare,
  chatwoot_action_requested: MessageCircle,
  email_action_requested: Mail,
  call_requested: Phone,
  schedule_requested: Calendar,
};

const ACTIVITY_COLORS: Record<string, string> = {
  call_started: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  call_completed: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  call_joined: 'bg-indigo-500/10 text-indigo-500 border-indigo-500/20',
  call_ended: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  call_billed: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  stage_changed: 'bg-violet-500/10 text-violet-500 border-violet-500/20',
  lead_updated: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  note: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  task_completed: 'bg-teal-500/10 text-teal-500 border-teal-500/20',
  task_created: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  task_updated: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  booking_detected: 'bg-fuchsia-500/10 text-fuchsia-500 border-fuchsia-500/20',
  whatsapp_action_requested: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  chatwoot_action_requested: 'bg-sky-500/10 text-sky-500 border-sky-500/20',
  email_action_requested: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  call_requested: 'bg-sky-500/10 text-sky-500 border-sky-500/20',
  schedule_requested: 'bg-fuchsia-500/10 text-fuchsia-500 border-fuchsia-500/20',
};

export function CrmActivityTimeline({ activities }: CrmActivityTimelineProps) {
  const formatDate = (dateStr: string) => {
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

  const sortedActivities = [...activities].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  );

  return (
    <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-6">
      <div className="flex flex-col gap-1 border-b border-border/60 pb-3">
        <h3 className="text-base font-bold text-foreground">
          Línea de Tiempo (Actividades)
        </h3>
        <p className="text-xs text-muted-foreground">
          Registro completo de llamadas de voz, notas, tareas y cambios de etapa.
        </p>
      </div>

      {sortedActivities.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          No hay actividades registradas en este lead.
        </p>
      ) : (
        <div className="relative pl-6 border-l border-border/80 flex flex-col gap-6 ml-2 py-2">
          {sortedActivities.map((act) => {
            const IconComponent = ACTIVITY_ICONS[act.activity_type] || HelpCircle;
            const colorClass = ACTIVITY_COLORS[act.activity_type] || 'bg-zinc-500/10 text-zinc-500 border-zinc-500/20';

            return (
              <div key={act.id} className="relative group">
                {/* Timeline Bullet/Icon */}
                <div className={cn(
                  'absolute -left-[35px] top-0 flex h-7 w-7 items-center justify-center rounded-full border bg-card shadow-2xs transition-all duration-300 group-hover:scale-110',
                  colorClass
                )}>
                  <IconComponent className="h-3.5 w-3.5" />
                </div>

                {/* Event Content */}
                <div className="flex flex-col gap-1.5 bg-muted/20 hover:bg-muted/30 border border-border/40 p-4 rounded-lg transition-all duration-200">
                  <div className="flex items-start justify-between gap-4">
                    <span className="text-xs font-bold text-foreground leading-tight">
                      {act.title}
                    </span>
                    <span className="text-[10px] text-muted-foreground shrink-0 font-mono">
                      {formatDate(act.occurred_at)}
                    </span>
                  </div>

                  {act.description && (
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                      {act.description}
                    </p>
                  )}

                  {/* Summary / Transcript data */}
                  {act.short_summary && (
                    <div className="bg-zinc-950/20 p-2.5 rounded border border-border/30 text-xs">
                      <span className="font-bold text-[10px] uppercase text-violet-500 tracking-wider block mb-1">
                        Resumen Corto:
                      </span>
                      <p className="text-muted-foreground">{act.short_summary}</p>
                    </div>
                  )}

                  {act.summary && (
                    <div className="bg-zinc-950/20 p-2.5 rounded border border-border/30 text-xs">
                      <span className="font-bold text-[10px] uppercase text-violet-500 tracking-wider block mb-1">
                        Resumen Completo:
                      </span>
                      <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{act.summary}</p>
                    </div>
                  )}

                  {/* Call outcome details */}
                  {act.outcome && (
                    <div className="text-2xs text-muted-foreground border-l-2 border-border/80 pl-2">
                      <span className="font-bold text-foreground">Resultado:</span> {act.outcome}
                    </div>
                  )}

                  {/* Call stats details */}
                  {(act.normalized_status || act.duration_seconds !== undefined || act.billed_minutes !== undefined) && (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 bg-zinc-950/15 p-2 rounded border border-border/20 text-2xs text-muted-foreground">
                      {act.normalized_status && (
                        <div>
                          <span className="font-semibold text-foreground">Estado:</span>{' '}
                          <span className="capitalize">{act.normalized_status}</span>
                        </div>
                      )}
                      {act.duration_seconds !== undefined && act.duration_seconds !== null && (
                        <div>
                          <span className="font-semibold text-foreground">Duración:</span>{' '}
                          <span>{act.duration_seconds}s</span>
                        </div>
                      )}
                      {act.billed_minutes !== undefined && act.billed_minutes !== null && (
                        <div>
                          <span className="font-semibold text-foreground">Facturado:</span>{' '}
                          <span>{act.billed_minutes} min</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Call Recording Audio Player */}
                  {act.recording_url && (
                    <div className="mt-2 flex flex-col gap-1 bg-muted/40 p-2 rounded border border-border/50">
                      <span className="text-[10px] font-bold text-foreground">
                        Grabación de la Llamada:
                      </span>
                      <audio
                        src={act.recording_url}
                        controls
                        className="w-full h-8 mt-1 text-xs"
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
