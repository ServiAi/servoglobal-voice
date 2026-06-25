'use client';

import React, { useState } from 'react';
import type { LeadDetailResponse, LeadUpdateRequest } from '@/types/crm';
import { Card } from '../ui/card';
import { User, Phone, Mail, Building, PenTool, Save, CheckCircle, AlertCircle } from 'lucide-react';

type CrmLeadDetailPanelProps = {
  lead: LeadDetailResponse;
  onSave: (payload: LeadUpdateRequest) => Promise<void>;
};

export function CrmLeadDetailPanel({
  lead,
  onSave,
}: CrmLeadDetailPanelProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Form states
  const [interest, setInterest] = useState(lead.interest || '');
  const [industry, setIndustry] = useState(lead.industry || '');
  const [useCase, setUseCase] = useState(lead.use_case || '');
  const [volume, setVolume] = useState(lead.volume || '');
  const [painPoint, setPainPoint] = useState(lead.pain_point || '');
  const [budgetRange, setBudgetRange] = useState(lead.budget_range || '');
  const [intentLevel, setIntentLevel] = useState(lead.intent_level || '');
  const [nextAction, setNextAction] = useState(lead.next_action || '');
  const [leadScore, setLeadScore] = useState<string>(lead.lead_score !== undefined && lead.lead_score !== null ? String(lead.lead_score) : '');
  const [status, setStatus] = useState(lead.status || 'open');
  const [source, setSource] = useState(lead.source || '');
  const [campaign, setCampaign] = useState(lead.campaign || '');

  const handleCancel = () => {
    // Reset fields to props
    setInterest(lead.interest || '');
    setIndustry(lead.industry || '');
    setUseCase(lead.use_case || '');
    setVolume(lead.volume || '');
    setPainPoint(lead.pain_point || '');
    setBudgetRange(lead.budget_range || '');
    setIntentLevel(lead.intent_level || '');
    setNextAction(lead.next_action || '');
    setLeadScore(lead.lead_score !== undefined && lead.lead_score !== null ? String(lead.lead_score) : '');
    setStatus(lead.status || 'open');
    setSource(lead.source || '');
    setCampaign(lead.campaign || '');
    setError(null);
    setIsEditing(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    // Validation
    const parsedScore = leadScore !== '' ? parseInt(leadScore, 10) : undefined;
    if (parsedScore !== undefined && (isNaN(parsedScore) || parsedScore < 0 || parsedScore > 100)) {
      setError('El Lead Score debe ser un número entero entre 0 y 100.');
      return;
    }

    const allowedStatuses = ['open', 'won', 'lost', 'unqualified', 'paused'];
    if (!allowedStatuses.includes(status)) {
      setError('Estado no válido.');
      return;
    }

    setSubmitting(true);
    try {
      const payload: LeadUpdateRequest = {
        interest: interest.trim() || null,
        industry: industry.trim() || null,
        use_case: useCase.trim() || null,
        volume: volume.trim() || null,
        pain_point: painPoint.trim() || null,
        budget_range: budgetRange.trim() || null,
        intent_level: intentLevel.trim() || null,
        next_action: nextAction.trim() || null,
        lead_score: parsedScore !== undefined ? parsedScore : null,
        status,
        source: source.trim() || null,
        campaign: campaign.trim() || null,
      };

      await onSave(payload);
      setSuccess(true);
      setIsEditing(false);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Error al guardar los cambios.');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusLabel = (s: string) => {
    switch (s) {
      case 'open': return 'Abierto';
      case 'won': return 'Ganado';
      case 'lost': return 'Perdido';
      case 'unqualified': return 'Descalificado';
      case 'paused': return 'Pausado';
      default: return s;
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Contact card (left column, 1 span) */}
      <Card className="lg:col-span-1 p-6 flex flex-col gap-6 border-border bg-card">
        <div className="border-b border-border/60 pb-3">
          <h3 className="text-base font-bold text-foreground">Información de Contacto</h3>
        </div>

        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="size-8 rounded-full bg-violet-500/10 flex items-center justify-center text-violet-500 shrink-0">
              <User className="h-4.5 w-4.5" />
            </div>
            <div className="truncate">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Nombre</span>
              <span className="text-sm font-semibold text-foreground truncate block">{lead.contact.name}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="size-8 rounded-full bg-violet-500/10 flex items-center justify-center text-violet-500 shrink-0">
              <Phone className="h-4.5 w-4.5" />
            </div>
            <div className="truncate">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Teléfono</span>
              {lead.contact.phone ? (
                <span className="text-sm font-mono text-foreground block">{lead.contact.phone}</span>
              ) : (
                <span className="text-sm text-muted-foreground/45 block">No registrado</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="size-8 rounded-full bg-violet-500/10 flex items-center justify-center text-violet-500 shrink-0">
              <Mail className="h-4.5 w-4.5" />
            </div>
            <div className="truncate">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Email</span>
              {lead.contact.email ? (
                <span className="text-sm text-foreground truncate block">{lead.contact.email}</span>
              ) : (
                <span className="text-sm text-muted-foreground/45 block">No registrado</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="size-8 rounded-full bg-violet-500/10 flex items-center justify-center text-violet-500 shrink-0">
              <Building className="h-4.5 w-4.5" />
            </div>
            <div className="truncate">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Empresa</span>
              {lead.contact.company ? (
                <span className="text-sm text-foreground block">{lead.contact.company}</span>
              ) : (
                <span className="text-sm text-muted-foreground/45 block">-</span>
              )}
            </div>
          </div>
        </div>

        {/* Short Summary & Full Summary */}
        <div className="flex flex-col gap-4 border-t border-border/60 pt-4 mt-2">
          {lead.short_summary && (
            <div className="flex flex-col gap-1">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Resumen Corto</span>
              <p className="text-xs text-muted-foreground leading-relaxed bg-muted/40 p-2.5 rounded border border-border/40">
                {lead.short_summary}
              </p>
            </div>
          )}
          {lead.summary && (
            <div className="flex flex-col gap-1">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Resumen Completo</span>
              <p className="text-xs text-muted-foreground leading-relaxed bg-muted/40 p-2.5 rounded border border-border/40 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {lead.summary}
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* Lead Qualification Details / Form (right column, 2 spans) */}
      <Card className="lg:col-span-2 p-6 border-border bg-card">
        <div className="border-b border-border/60 pb-3 flex items-center justify-between">
          <h3 className="text-base font-bold text-foreground">Calificación e Interés</h3>
          {!isEditing && (
            <button
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition"
            >
              <PenTool className="h-3.5 w-3.5" />
              Editar Lead
            </button>
          )}
        </div>

        {isEditing ? (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-4">
            {error && (
              <div className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Interest */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Interés</label>
                <input
                  type="text"
                  value={interest}
                  onChange={(e) => setInterest(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Use Case */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Caso de Uso</label>
                <input
                  type="text"
                  value={useCase}
                  onChange={(e) => setUseCase(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Industry */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Industria</label>
                <input
                  type="text"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Volume */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Volumen</label>
                <input
                  type="text"
                  value={volume}
                  onChange={(e) => setVolume(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Budget Range */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Presupuesto</label>
                <input
                  type="text"
                  value={budgetRange}
                  onChange={(e) => setBudgetRange(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Intent Level */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Nivel de Intención (Intent)</label>
                <input
                  type="text"
                  value={intentLevel}
                  onChange={(e) => setIntentLevel(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Lead Score */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Lead Score (0-100)</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={leadScore}
                  onChange={(e) => setLeadScore(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Status */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Estado del Lead</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                >
                  <option value="open">Abierto (Open)</option>
                  <option value="won">Ganado (Won)</option>
                  <option value="lost">Perdido (Lost)</option>
                  <option value="unqualified">Descalificado</option>
                  <option value="paused">Pausado</option>
                </select>
              </div>

              {/* Source */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Origen (Source)</label>
                <input
                  type="text"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>

              {/* Campaign */}
              <div className="flex flex-col gap-1">
                <label className="text-2xs font-bold text-muted-foreground uppercase">Campaña</label>
                <input
                  type="text"
                  value={campaign}
                  onChange={(e) => setCampaign(e.target.value)}
                  className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Pain Point */}
            <div className="flex flex-col gap-1">
              <label className="text-2xs font-bold text-muted-foreground uppercase">Pain Point (Dolor)</label>
              <textarea
                rows={2}
                value={painPoint}
                onChange={(e) => setPainPoint(e.target.value)}
                className="rounded-md border border-border bg-zinc-950/40 p-3 text-sm text-foreground focus:border-violet-500 focus:outline-none"
              />
            </div>

            {/* Next Action */}
            <div className="flex flex-col gap-1">
              <label className="text-2xs font-bold text-muted-foreground uppercase">Siguiente Acción (Next Action)</label>
              <input
                type="text"
                value={nextAction}
                onChange={(e) => setNextAction(e.target.value)}
                className="rounded-md border border-border bg-zinc-950/40 px-3 py-2 text-sm text-foreground focus:border-violet-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
              <button
                type="button"
                onClick={handleCancel}
                disabled={submitting}
                className="rounded-md border border-border px-4 py-2 text-xs font-semibold text-muted-foreground hover:bg-muted"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-1.5 rounded-md bg-violet-600 px-5 py-2 text-xs font-bold text-white hover:bg-violet-500 shadow-sm"
              >
                {submitting ? 'Guardando...' : (
                  <>
                    <Save className="h-3.5 w-3.5" />
                    Guardar
                  </>
                )}
              </button>
            </div>
          </form>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 mt-6">
            {/* Success toast feedback */}
            {success && (
              <div className="col-span-2 flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-500">
                <CheckCircle className="h-4 w-4 shrink-0" />
                <span>¡Cambios guardados exitosamente!</span>
              </div>
            )}

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Etapa Actual</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.stage.name}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Estado del Lead</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{getStatusLabel(lead.status)}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Interés</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.interest || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Caso de Uso</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.use_case || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Industria</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.industry || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Volumen</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.volume || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Presupuesto</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.budget_range || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Nivel de Intención (Intent)</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.intent_level || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Origen (Source)</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.source || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Campaña</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.campaign || '-'}</span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Lead Score (Prioridad)</span>
              <span className="text-sm font-semibold text-foreground block mt-1">
                {lead.lead_score !== undefined && lead.lead_score !== null ? `${lead.lead_score}/100` : '-'}
              </span>
            </div>

            <div>
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Siguiente Acción</span>
              <span className="text-sm font-semibold text-foreground block mt-1">{lead.next_action || '-'}</span>
            </div>

            <div className="col-span-2 border-t border-border/40 pt-4 mt-2">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground block">Pain Point (Dolor principal)</span>
              <p className="text-xs text-muted-foreground mt-2 leading-relaxed whitespace-pre-wrap bg-muted/20 p-3 rounded border border-border/30">
                {lead.pain_point || 'No diagnosticado.'}
              </p>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
