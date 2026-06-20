'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import type { PipelineBoardLeadItem } from '@/types/crm';
import { Card } from '../ui/card';
import { Eye, Phone, Building, Calendar, ArrowRightLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

type CrmLeadCardProps = {
  lead: PipelineBoardLeadItem;
  locale: string;
  stages: { key: string; name: string }[];
  onStageChange: (leadId: string, newStageKey: string) => void;
  currentStageKey: string;
};

export function CrmLeadCard({
  lead,
  locale,
  stages,
  onStageChange,
  currentStageKey,
}: CrmLeadCardProps) {
  const [updating, setUpdating] = useState(false);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'open':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'won':
        return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
      case 'lost':
        return 'bg-destructive/10 text-destructive border-destructive/20';
      case 'unqualified':
        return 'bg-orange-500/10 text-orange-500 border-orange-500/20';
      case 'paused':
        return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
      default:
        return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'open':
        return 'Abierto';
      case 'won':
        return 'Ganado';
      case 'lost':
        return 'Perdido';
      case 'unqualified':
        return 'Descalificado';
      case 'paused':
        return 'Pausado';
      default:
        return status;
    }
  };

  const handleStageSelect = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newStage = e.target.value;
    if (!newStage || newStage === currentStageKey) return;
    setUpdating(true);
    try {
      await onStageChange(lead.id, newStage);
    } catch (err) {
      console.error(err);
    } finally {
      setUpdating(false);
    }
  };

  const formatActivityDate = (dateStr?: string | null) => {
    if (!dateStr) return 'Sin actividad';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return 'Sin actividad';
    return date.toLocaleDateString('es-ES', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Card className={cn(
      'p-4 bg-card border border-border/80 hover:border-violet-500/50 shadow-sm transition-all duration-300 relative group flex flex-col gap-3',
      updating && 'opacity-60 pointer-events-none'
    )}>
      {/* Name and Status */}
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-semibold text-sm text-foreground leading-tight truncate max-w-[70%]">
          {lead.contact_name}
        </h4>
        <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border', getStatusColor(lead.status))}>
          {getStatusLabel(lead.status)}
        </span>
      </div>

      {/* Company / Phone info */}
      <div className="flex flex-col gap-1 text-xs text-muted-foreground">
        {lead.company && (
          <div className="flex items-center gap-1.5 truncate">
            <Building className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
            <span className="truncate">{lead.company}</span>
          </div>
        )}
        {lead.phone && (
          <div className="flex items-center gap-1.5 truncate">
            <Phone className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
            <span className="font-mono">{lead.phone}</span>
          </div>
        )}
      </div>

      {/* Short Summary */}
      {lead.short_summary && (
        <p className="text-xs text-muted-foreground line-clamp-2 bg-muted/30 p-2 rounded border border-border/40">
          {lead.short_summary}
        </p>
      )}

      {/* Last activity */}
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <Calendar className="h-3 w-3 text-zinc-500" />
        <span>Actividad: {formatActivityDate(lead.last_activity_at)}</span>
      </div>

      <div className="h-px bg-border/60" />

      {/* Actions: Stage selection and View Detail Link */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <div className="relative flex items-center gap-1 text-xs max-w-[60%] border border-border/80 rounded bg-muted/20 px-1 py-0.5">
          <ArrowRightLeft className="h-3 w-3 text-violet-500 shrink-0" />
          <select
            value={currentStageKey}
            onChange={handleStageSelect}
            className="bg-transparent border-none text-[11px] text-muted-foreground focus:outline-none cursor-pointer max-w-[80px] truncate"
            title="Mover etapa"
            disabled={updating}
          >
            {stages.map((stg) => (
              <option key={stg.key} value={stg.key} className="bg-card text-foreground">
                {stg.name}
              </option>
            ))}
          </select>
        </div>

        <Link
          href={`/${locale}/crm/leads/${lead.id}`}
          className="inline-flex items-center justify-center gap-1 rounded bg-violet-600 px-2 py-1 text-xs font-semibold text-white transition hover:bg-violet-500 shadow-sm"
        >
          <Eye className="h-3 w-3" />
          Ver
        </Link>
      </div>
    </Card>
  );
}
