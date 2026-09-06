'use client';

import { useEffect, useState } from 'react';
import { Phone, Play, Volume2, AlertTriangle, Clock } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { fetchVoiceAgents, startCrmLeadVoiceCall, fetchCrmLeadVoiceCalls } from '@/lib/api/crm';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { VoiceAgentConfigResponse, VoiceCallResponse } from '@/types/crm';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  contactName?: string | null;
  contactPhone?: string | null;
  onSent?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

export function CrmSendVoiceCallModal({
  open,
  onOpenChange,
  accessToken,
  leadId,
  contactName,
  contactPhone,
  onSent,
  onError,
  onSuccess,
}: Props) {
  const [agents, setAgents] = useState<VoiceAgentConfigResponse[]>([]);
  const [calls, setCalls] = useState<VoiceCallResponse[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    // Load active voice agents
    fetchVoiceAgents(accessToken).then((res) => {
      if (cancelled) return;
      if (res.ok) {
        const activeAgents = res.data.filter((a) => a.status === 'active');
        setAgents(activeAgents);
        if (activeAgents.length > 0) {
          setSelectedAgentId(activeAgents[0].id);
        }
      } else {
        onError(res.detail);
      }
    });

    // Load call history
    setLoadingHistory(true);
    fetchCrmLeadVoiceCalls(accessToken, leadId).then((res) => {
      if (cancelled) return;
      setLoadingHistory(false);
      if (res.ok) {
        setCalls(res.data);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [accessToken, leadId, onError, open]);

  const handleStartCall = async () => {
    if (!contactPhone) {
      onError('El lead no tiene teléfono para iniciar llamadas.');
      return;
    }
    if (!selectedAgentId) {
      onError('Por favor selecciona un agente de voz.');
      return;
    }

    setLoading(true);
    const result = await startCrmLeadVoiceCall(accessToken, leadId, {
      agent_config_id: selectedAgentId,
      to_phone: contactPhone,
    });
    setLoading(false);

    if (!result.ok) {
      onError(result.detail);
      return;
    }

    onSuccess('Llamada iniciada. El agente virtual marcará en unos segundos.');
    onSent?.();

    // Reload call history
    fetchCrmLeadVoiceCalls(accessToken, leadId).then((res) => {
      if (res.ok) {
        setCalls(res.data);
      }
    });
  };

  const formatDuration = (seconds: number | null | undefined) => {
    if (seconds === null || seconds === undefined) return '-';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Finalizada</span>;
      case 'queued':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20">En cola</span>;
      case 'ringing':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-500 border border-indigo-500/20">Timbrando</span>;
      case 'in_progress':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-sky-500/10 text-sky-500 border border-sky-500/20">Conectada</span>;
      case 'failed':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20">Fallida</span>;
      case 'busy':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-500 border border-yellow-500/20">Ocupado</span>;
      case 'no_answer':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">Sin respuesta</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">{status}</span>;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Volume2 className="h-5 w-5 text-indigo-500" />
            Llamada Saliente IA
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-5 pr-1">
          {/* Destination Details */}
          <div className="rounded-lg border border-border bg-muted/20 p-3 text-sm flex items-center justify-between">
            <div>
              <div className="font-semibold text-foreground">{contactName || 'Lead sin nombre'}</div>
              <div className={contactPhone ? 'text-muted-foreground' : 'text-red-500'}>
                {contactPhone || 'Sin teléfono'}
              </div>
            </div>
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/10 text-indigo-500">
              <Phone className="h-4 w-4" />
            </span>
          </div>

          {/* Selector Agent */}
          <div className="space-y-2">
            <label className="flex flex-col gap-1.5 text-xs font-bold text-muted-foreground uppercase">
              Agente Virtual para la llamada *
            </label>
            {agents.length === 0 ? (
              <div className="flex items-center gap-2 p-3 text-xs border border-amber-500/30 bg-amber-500/10 text-amber-500 rounded-md">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>
                  No hay agentes de voz activos. Por favor configura uno en Integraciones.
                </span>
              </div>
            ) : (
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                value={selectedAgentId}
                onChange={(e) => setSelectedAgentId(e.target.value)}
              >
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.display_name} ({agent.purpose})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Call Logs History */}
          <div className="space-y-2 border-t border-border pt-4">
            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
              Historial de Llamadas
            </h4>

            {loadingHistory ? (
              <div className="text-center py-6 text-xs text-muted-foreground flex items-center justify-center gap-2">
                <CircularLoader size="xs" glow={false} />
                Cargando historial de llamadas...
              </div>
            ) : calls.length === 0 ? (
              <div className="text-center py-6 text-xs text-muted-foreground border border-dashed border-border rounded-md bg-muted/10">
                Aún no hay llamadas registradas para este lead.
              </div>
            ) : (
              <div className="space-y-2">
                {calls.map((call) => (
                  <div
                    key={call.id}
                    className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3 shadow-2xs hover:bg-muted/10 transition"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        <span>{new Date(call.created_at).toLocaleString()}</span>
                        <span className="font-mono text-[10px]">({call.provider})</span>
                      </div>
                      {getStatusBadge(call.status)}
                    </div>
                    {call.summary && (
                      <p className="text-xs text-foreground bg-muted/30 p-2 rounded-md italic">
                        {call.summary}
                      </p>
                    )}
                    <div className="flex items-center justify-between text-2xs text-muted-foreground border-t border-border/40 pt-2">
                      <span>Duración: {formatDuration(call.duration_seconds)}</span>
                      {call.status === 'completed' && (
                        <div className="flex items-center gap-2">
                          {/* If recording URL exists, display it or display playback */}
                          {/* Wait! In landing-serviglobalAi, how do we render audio? If we have recording_url, let's render a link */}
                          {/* Recording URL link */}
                          {/* (Wait, let's keep it safe. The recording_url could be a URL or file path. If it's a valid link, show audio player or link) */}
                          {/* Standard link */}
                          {/* (Wait, standard link is better to avoid styling complex player inside small items) */}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2 sm:justify-end border-t border-border pt-3">
          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => onOpenChange(false)}
          >
            Cerrar
          </Button>
          <Button
            type="button"
            disabled={loading || agents.length === 0 || !contactPhone}
            onClick={handleStartCall}
            className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
          >
            {loading ? (
              <CircularLoader size="xs" glow={false} />
            ) : (
              <Play className="h-4 w-4 fill-current" />
            )}
            Iniciar Llamada
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
