'use client';

import React, { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import {
  MessageSquare,
  MessageCircle,
  Phone,
  Calendar,
  Mail,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ShieldAlert,
  Loader2,
} from 'lucide-react';
import {
  leadActionWhatsapp,
  leadActionCall,
  leadActionSchedule,
  changeCrmLeadStage,
  leadActionChatwoot,
  leadActionEmail,
} from '@/lib/api/crm';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { canUseOutboundActions, canChangeTerminalStage } from '@/lib/permissions/crm';

type CrmLeadQuickActionsProps = {
  leadId: string;
  accessToken: string;
  currentStageKey: string;
  onActionComplete?: () => void;
  userRole?: string;
};

export function CrmLeadQuickActions({
  leadId,
  accessToken,
  currentStageKey,
  onActionComplete,
  userRole,
}: CrmLeadQuickActionsProps) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [terminalStage, setTerminalStage] = useState<'won' | 'lost' | 'not_interested' | null>(null);
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const canAct = canUseOutboundActions(userRole);

  const triggerStatus = (type: 'error' | 'success', msg: string) => {
    if (type === 'error') {
      setErrorMsg(msg);
      setTimeout(() => setErrorMsg(null), 5000);
    } else {
      setSuccessMsg(msg);
      setTimeout(() => setSuccessMsg(null), 4000);
    }
  };

  const handleOutboundAction = async (type: 'whatsapp' | 'call' | 'schedule' | 'chatwoot' | 'email') => {
    if (!canAct) {
      triggerStatus('error', 'No tienes permisos para realizar esta acción.');
      return;
    }

    setLoadingAction(type);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      let res;
      if (type === 'whatsapp') {
        res = await leadActionWhatsapp(accessToken, leadId);
      } else if (type === 'call') {
        res = await leadActionCall(accessToken, leadId);
      } else if (type === 'schedule') {
        res = await leadActionSchedule(accessToken, leadId);
      } else if (type === 'chatwoot') {
        res = await leadActionChatwoot(accessToken, leadId);
      } else {
        res = await leadActionEmail(accessToken, leadId);
      }

      if (res.ok) {
        triggerStatus('success', 'Acción completada con éxito.');
      } else {
        triggerStatus('error', res.detail || 'Error al ejecutar la acción.');
      }

      startTransition(() => {
        router.refresh();
        if (onActionComplete) onActionComplete();
      });
    } catch (err) {
      console.error(err);
      triggerStatus('error', 'Ocurrió un error inesperado al conectar con el servidor.');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleTerminalStageSubmit = async () => {
    if (!canChangeTerminalStage(userRole)) {
      triggerStatus('error', 'No tienes permisos para realizar esta acción.');
      return;
    }

    if (!reason.trim()) {
      setValidationError('La razón o motivo del cambio es obligatoria.');
      return;
    }
    if (!terminalStage) return;

    setLoadingAction(terminalStage);
    setValidationError(null);
    setErrorMsg(null);
    setSuccessMsg(null);

    const fullReason = notes.trim()
      ? `${reason.trim()}\n\nNotas adicionales: ${notes.trim()}`
      : reason.trim();

    try {
      const res = await changeCrmLeadStage(accessToken, leadId, {
        stage_key: terminalStage,
        reason: fullReason,
      });

      if (res.ok) {
        triggerStatus(
          'success',
          `El lead ha sido marcado como ${
            terminalStage === 'won'
              ? 'GANADO'
              : terminalStage === 'lost'
              ? 'PERDIDO'
              : 'NO INTERESADO'
          }.`
        );
        setTerminalStage(null);
        setReason('');
        setNotes('');
        startTransition(() => {
          router.refresh();
          if (onActionComplete) onActionComplete();
        });
      } else {
        triggerStatus('error', res.detail || 'Error al cambiar de etapa.');
      }
    } catch (err) {
      console.error(err);
      triggerStatus('error', 'Ocurrió un error inesperado.');
    } finally {
      setLoadingAction(null);
    }
  };

  const getTerminalStageLabel = () => {
    switch (terminalStage) {
      case 'won': return 'Ganado';
      case 'lost': return 'Perdido';
      case 'not_interested': return 'No Interesado';
      default: return '';
    }
  };

  if (!canAct && !canChangeTerminalStage(userRole)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card/65 p-5 shadow-xs">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <h4 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
          Acciones Rápidas (Outbound)
        </h4>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2">
        {canAct && (
          <>
            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null}
              onClick={() => handleOutboundAction('whatsapp')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-emerald-500/10 hover:text-emerald-500 hover:border-emerald-500/20 transition cursor-pointer"
            >
              {loadingAction === 'whatsapp' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MessageSquare className="h-4 w-4 text-emerald-500" />
              )}
              <span className="truncate">Enviar WhatsApp</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null}
              onClick={() => handleOutboundAction('chatwoot')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-sky-500/10 hover:text-sky-500 hover:border-sky-500/20 transition cursor-pointer"
            >
              <MessageCircle className="h-4 w-4 text-sky-500" />
              <span className="truncate">Chatwoot</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null}
              onClick={() => handleOutboundAction('call')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-blue-500/10 hover:text-blue-500 hover:border-blue-500/20 transition cursor-pointer"
            >
              {loadingAction === 'call' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Phone className="h-4 w-4 text-blue-500" />
              )}
              <span className="truncate">Llamar de nuevo</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null}
              onClick={() => handleOutboundAction('schedule')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-fuchsia-500/10 hover:text-fuchsia-500 hover:border-fuchsia-500/20 transition cursor-pointer"
            >
              {loadingAction === 'schedule' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Calendar className="h-4 w-4 text-fuchsia-500" />
              )}
              <span className="truncate">Agendar reunión</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null}
              onClick={() => handleOutboundAction('email')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-amber-500/10 hover:text-amber-500 hover:border-amber-500/20 transition cursor-pointer col-span-2 sm:col-span-4 lg:col-span-2"
            >
              <Mail className="h-4 w-4 text-amber-500" />
              <span className="truncate">Enviar resumen Email</span>
            </Button>
          </>
        )}
      </div>

      {canChangeTerminalStage(userRole) && (
        <>
          <div className="col-span-2 sm:col-span-4 lg:col-span-2 border-t border-border/40 my-1"></div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2">
            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null || currentStageKey === 'won'}
              onClick={() => setTerminalStage('won')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-emerald-500/10 hover:text-emerald-500 hover:border-emerald-500/20 transition cursor-pointer"
            >
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="truncate">Marcar Ganado</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null || currentStageKey === 'lost'}
              onClick={() => setTerminalStage('lost')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-red-500/10 hover:text-red-500 hover:border-red-500/20 transition cursor-pointer"
            >
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="truncate">Marcar Perdido</span>
            </Button>

            <Button
              variant="outline" size="sm"
              disabled={loadingAction !== null || currentStageKey === 'not_interested'}
              onClick={() => setTerminalStage('not_interested')}
              className="flex items-center justify-start gap-2 bg-zinc-950/20 text-foreground hover:bg-zinc-500/15 hover:text-zinc-400 hover:border-zinc-500/20 transition cursor-pointer col-span-2 sm:col-span-4 lg:col-span-2"
            >
              <AlertCircle className="h-4 w-4 text-zinc-400" />
              <span className="truncate">No Interesado</span>
            </Button>
          </div>
        </>
      )}

      {errorMsg && (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-500">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{errorMsg}</span>
        </div>
      )}

      {successMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-500 animate-fadeIn">
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
          <span>{successMsg}</span>
        </div>
      )}

      <Dialog open={terminalStage !== null} onOpenChange={(open) => !open && setTerminalStage(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {terminalStage === 'won' ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              ) : terminalStage === 'lost' ? (
                <XCircle className="h-5 w-5 text-red-500" />
              ) : (
                <AlertCircle className="h-5 w-5 text-zinc-400" />
              )}
              Marcar Lead como: {getTerminalStageLabel()}
            </DialogTitle>
            <DialogDescription>
              Para mover el lead a esta etapa terminal, por favor indica el motivo o justificación. Esto quedará registrado en la línea de tiempo.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="reason" className="text-xs font-bold text-muted-foreground uppercase">
                Motivo / Justificación *
              </label>
              <textarea
                id="reason" rows={3}
                placeholder="Indica el motivo (ej: Cliente firmó contrato, Presupuesto no califica, No atiende llamadas...)"
                value={reason}
                onChange={(e) => { setReason(e.target.value); if (validationError) setValidationError(null); }}
                className="w-full rounded-md border border-border bg-zinc-950/40 p-2.5 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition"
              />
              {validationError && (
                <span className="text-2xs font-semibold text-red-500">{validationError}</span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="notes" className="text-xs font-bold text-muted-foreground uppercase">
                Notas adicionales (Opcional)
              </label>
              <textarea
                id="notes" rows={2}
                placeholder="Cualquier nota extra relevante para el historial comercial..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full rounded-md border border-border bg-zinc-950/40 p-2.5 text-sm text-foreground focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:justify-end">
            <Button type="button" variant="outline" disabled={loadingAction !== null}
              onClick={() => { setTerminalStage(null); setReason(''); setNotes(''); setValidationError(null); }}>
              Cancelar
            </Button>
            <Button type="button" disabled={loadingAction !== null}
              onClick={handleTerminalStageSubmit} className="bg-violet-600 hover:bg-violet-500 text-white font-bold">
              {loadingAction !== null ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Guardar Cambios
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
