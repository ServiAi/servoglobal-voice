'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, Braces, Headphones, Mic, MicOff, Phone, PhoneOff, Radio, Search, Wrench } from 'lucide-react';
import {
  createVoiceTestSessionAction,
  createVoiceTestTokenAction,
  fetchVoiceQaContextPreviewAction,
  fetchVoiceQaLeadsAction,
  fetchVoiceTestEventsAction,
  type QaContextMode,
  type VoiceQaEvent,
  type VoiceQaEventsResponse,
} from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { LiveKitVoiceRuntimeAdapter } from '@/lib/voice-runtime/livekit-adapter';
import type { AgentToolBinding, AgentToolCatalogEntry } from '@/types/agents';
import type { LeadListItem } from '@/types/crm';

type Transport = 'webrtc' | 'sip';
type Stage = 'config' | 'preparing' | 'live' | 'ended' | 'error';
type PublishedAgentInfo = { id: string; version: number; provider: string; runtimeEngine: string; pipelineType: string };

const TERMINAL = new Set(['ended', 'failed', 'cancelled']);
const INPUT = 'h-10 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/15';

export function AgentVoiceTest({ agentId, agentName, published, toolCatalog, toolBindings }: { agentId: string; agentName: string; published: PublishedAgentInfo; toolCatalog: AgentToolCatalogEntry[]; toolBindings: AgentToolBinding[] }) {
  const adapter = useRef<LiveKitVoiceRuntimeAdapter | null>(null);
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<Stage>('config');
  const [transport, setTransport] = useState<Transport>('webrtc');
  const [contextMode, setContextMode] = useState<QaContextMode>('preloaded');
  const [callerPhone, setCallerPhone] = useState('');
  const [toPhone, setToPhone] = useState('');
  const [contactId, setContactId] = useState('');
  const [leadId, setLeadId] = useState('');
  const [variablesText, setVariablesText] = useState('{}');
  const [service, setService] = useState('');
  const [location, setLocation] = useState('');
  const [preferredDate, setPreferredDate] = useState('');
  const [preferredTime, setPreferredTime] = useState('');
  const [notes, setNotes] = useState('');
  const [contextPreview, setContextPreview] = useState<Record<string, unknown> | null>(null);
  const [contextPreviewError, setContextPreviewError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [leadSearch, setLeadSearch] = useState('');
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [session, setSession] = useState<VoiceQaEventsResponse | null>(null);
  const [events, setEvents] = useState<VoiceQaEvent[]>([]);
  const [microphoneActive, setMicrophoneActive] = useState(false);
  const [connected, setConnected] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    void adapter.current?.disconnect();
    adapter.current = null;
    setStage('config');
    setSession(null);
    setEvents([]);
    setConnected(false);
    setMicrophoneActive(false);
    setAudioBlocked(false);
    setError(null);
  }, []);

  useEffect(() => () => void adapter.current?.disconnect(), []);

  useEffect(() => {
    if (!open || stage !== 'config' || contextMode === 'conversation') return;
    const timer = window.setTimeout(async () => {
      const result = await fetchVoiceQaLeadsAction(leadSearch.trim());
      if (result.ok) setLeads(result.data);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [contextMode, leadSearch, open, stage]);

  useEffect(() => {
    if (!open || stage !== 'config') return;
    setContextPreview(null);
    let variables: Record<string, unknown> = {};
    if (contextMode === 'preloaded') {
      try {
        const parsed: unknown = JSON.parse(variablesText);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
        variables = parsed as Record<string, unknown>;
        for (const [key, value] of Object.entries({ service, location, preferred_date: preferredDate, preferred_time: preferredTime, notes })) {
          if (value.trim()) variables[key] = value.trim();
          else delete variables[key];
        }
      } catch {
        setContextPreview(null);
        setContextPreviewError('Las variables deben ser un objeto JSON válido.');
        return;
      }
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      const result = await fetchVoiceQaContextPreviewAction({
        context_mode: contextMode,
        transport,
        caller_phone: callerPhone.trim() || undefined,
        lead_id: leadId || undefined,
        contact_id: contactId.trim() || undefined,
        to_phone: toPhone.trim() || undefined,
        variables,
      });
      if (!active) return;
      if (result.ok) {
        setContextPreview(result.data);
        setContextPreviewError(null);
      } else {
        setContextPreview(null);
        setContextPreviewError(result.detail);
      }
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [callerPhone, contactId, contextMode, leadId, location, notes, open, preferredDate, preferredTime, service, stage, toPhone, transport, variablesText]);

  useEffect(() => {
    const sessionId = session?.session.id;
    if (!sessionId || (stage !== 'live' && stage !== 'preparing')) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      const result = await fetchVoiceTestEventsAction(sessionId);
      if (cancelled) return;
      if (!result.ok) {
        setError(result.detail);
        timer = window.setTimeout(poll, 1000);
        return;
      }
      setSession(result.data);
      setEvents((current) => {
        const byId = new Map(current.map((event) => [event.event_id, event]));
        result.data.events.forEach((event) => byId.set(event.event_id, event));
        return [...byId.values()].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
      });
      if (TERMINAL.has(result.data.session.status)) {
        setStage('ended');
        setConnected(false);
        return;
      }
      timer = window.setTimeout(poll, 1000);
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [session?.session.id, stage]);

  const start = useCallback(async () => {
    setError(null);
    const hasPreloadedContext = contextMode === 'preloaded';
    let variables: Record<string, unknown> = {};
    if (hasPreloadedContext) {
      try {
        variables = JSON.parse(variablesText) as Record<string, unknown>;
        if (!variables || Array.isArray(variables) || typeof variables !== 'object') throw new Error();
        for (const [key, value] of Object.entries({ service, location, preferred_date: preferredDate, preferred_time: preferredTime, notes })) {
          if (value.trim()) variables[key] = value.trim();
          else delete variables[key];
        }
      } catch {
        setError('Las variables deben ser un objeto JSON válido.');
        return;
      }
    }
    if (transport === 'sip' && !toPhone.trim()) {
      setError('El número de destino es obligatorio para SIP.');
      return;
    }
    setStage('preparing');
    const result = await createVoiceTestSessionAction(agentId, crypto.randomUUID(), {
      transport,
      context_mode: contextMode,
      caller_phone: hasPreloadedContext ? callerPhone.trim() || undefined : undefined,
      contact_id: hasPreloadedContext ? contactId.trim() || undefined : undefined,
      lead_id: hasPreloadedContext ? leadId || undefined : undefined,
      to_phone: toPhone.trim() || undefined,
      variables: hasPreloadedContext ? variables : {},
    });
    if (!result.ok || result.data.status === 'failed') {
      setError(result.ok ? result.data.error_code ?? 'No fue posible iniciar la sesión.' : result.detail);
      setStage('error');
      return;
    }
    const initial: VoiceQaEventsResponse = {
      session: result.data,
      context: { caller_phone: null, contact_id: null, lead_id: null, variables },
      events: [],
    };
    setSession(initial);
    setStage('live');
    if (transport === 'sip') {
      setConnected(true);
      return;
    }
    const token = await createVoiceTestTokenAction(result.data.id);
    if (!token.ok) {
      setError(token.detail);
      setStage('error');
      return;
    }
    const { LiveKitVoiceRuntimeAdapter } = await import('@/lib/voice-runtime/livekit-adapter');
    const runtime = new LiveKitVoiceRuntimeAdapter({
      onMicrophoneChange: setMicrophoneActive,
      onAgentSpeakingChange: () => undefined,
      onAudioPlaybackBlocked: () => setAudioBlocked(true),
    });
    adapter.current = runtime;
    try {
      await runtime.connect({ serverUrl: token.data.server_url, participantToken: token.data.participant_token }, (state) => {
        setConnected(state === 'connected');
        if (state === 'ended') setStage('ended');
        if (state === 'error') setError('La conexión WebRTC terminó con un error.');
      });
    } catch {
      setError('No fue posible conectar con LiveKit.');
      setStage('error');
    }
  }, [agentId, callerPhone, contactId, contextMode, leadId, location, notes, preferredDate, preferredTime, service, toPhone, transport, variablesText]);

  const transcripts = useMemo(() => events.filter((event) => event.event_type === 'voice.transcript.final'), [events]);
  const tools = useMemo(() => events.filter((event) => event.event_type === 'session.context.tool_used'), [events]);
  const enabledBindings = toolBindings.filter((binding) => binding.enabled);
  const enabledTools = enabledBindings.map((binding) => ({ binding, definition: toolCatalog.find((tool) => tool.key === binding.key) }));
  const toolsReady = enabledTools.every(({ binding, definition }) => definition?.status === 'available' && definition.available && (!definition.configuration_required || Object.keys(binding.config ?? {}).length > 0));
  const preflightReady = Boolean(contextPreview) && !contextPreviewError && Boolean(published.provider) && published.runtimeEngine === 'livekit' && published.pipelineType === 'realtime' && toolsReady;
  const selectedLead = leads.find((lead) => lead.lead_id === leadId);
  const resolvedContact = contextPreview?.contact as Record<string, unknown> | null | undefined;

  return (
    <>
      <Button type="button" size="sm" onClick={() => { reset(); setOpen(true); }}>
        <Headphones className="mr-1.5 size-4" aria-hidden="true" /> Probar agente
      </Button>
      <Dialog open={open} onOpenChange={(next) => { if (!next) reset(); setOpen(next); }}>
        <DialogContent className="grid max-h-[92dvh] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 sm:max-w-4xl">
          <DialogHeader className="border-b border-border bg-muted/25 px-6 py-5">
            <DialogTitle>QA de voz · {agentName}</DialogTitle>
            <DialogDescription>Versión {published.version} · {published.provider} · {published.runtimeEngine} · {published.pipelineType}</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            {stage === 'config' ? (
              <div className="space-y-5">
                <div className="grid grid-cols-2 gap-2 rounded-xl bg-muted p-1" role="radiogroup" aria-label="Transporte">
                  {(['webrtc', 'sip'] as const).map((value) => (
                    <button key={value} type="button" role="radio" aria-checked={transport === value} onClick={() => setTransport(value)} className={`rounded-lg px-4 py-3 text-sm font-semibold transition ${transport === value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'}`}>
                      {value === 'webrtc' ? 'WebRTC · navegador' : 'SIP · llamada real'}
                    </button>
                  ))}
                </div>
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-900 dark:text-amber-200">
                  <div className="flex gap-3"><AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" /><p><strong>Prueba con efectos reales.</strong> El agente puede crear citas, enviar mensajes de WhatsApp y, en SIP, realizar una llamada telefónica real.</p></div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Modo de contexto QA">
                  {([
                    ['preloaded', 'Con contexto precargado', 'Simula una llamada donde la plataforma ya conoce información del usuario, como caller, contacto, lead o variables.'],
                    ['conversation', 'Sin contexto precargado', 'El agente inicia sin Contact, Lead ni variables de negocio y deberá recopilar la información durante la conversación.'],
                  ] as const).map(([value, title, description]) => (
                    <button key={value} type="button" role="radio" aria-checked={contextMode === value} onClick={() => setContextMode(value)} className={`rounded-xl border p-4 text-left transition ${contextMode === value ? 'border-cyan-500 bg-cyan-500/10 ring-2 ring-cyan-500/15' : 'border-border bg-background hover:bg-muted/40'}`}>
                      <span className="block text-sm font-semibold">{title}</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span>
                    </button>
                  ))}
                </div>
                {transport === 'sip' ? <label className="block space-y-1.5 text-sm font-medium"><span>Número a llamar</span><input className={INPUT} value={toPhone} onChange={(event) => setToPhone(event.target.value)} placeholder="+57…" required /></label> : null}
                {contextMode === 'conversation' ? (
                  <div className="space-y-3 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-4 text-sm">
                    <p><strong>El agente iniciará sin contexto de negocio precargado.</strong> Deberá solicitar durante la conversación los datos necesarios para completar su tarea.</p>
                    <p className="text-muted-foreground">Esta prueba no modifica el prompt ni agrega instrucciones ocultas al agente. Verifica que las instrucciones publicadas indiquen cómo recopilar los datos necesarios.</p>
                    {transport === 'webrtc' ? <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-amber-900 dark:text-amber-200">En WebRTC no existe una identidad telefónica confiable de transporte. El agente puede recopilar información durante la conversación, pero las herramientas que requieran caller_phone seguirán necesitando una identidad de sesión confiable. Para probar el flujo completo de creación de lead desde una llamada sin contexto, utiliza SIP.</p> : null}
                  </div>
                ) : (
                  <>
                    <label className="block space-y-1.5 text-sm font-medium"><span>Teléfono del caller (contexto)</span><input className={INPUT} value={callerPhone} onChange={(event) => setCallerPhone(event.target.value)} placeholder="+57…" /></label>
                    <div className="space-y-2">
                      <label className="relative block"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden="true" /><input className={`${INPUT} pl-9`} value={leadSearch} onChange={(event) => setLeadSearch(event.target.value)} placeholder="Buscar lead por nombre, teléfono o correo" /></label>
                      <select className={INPUT} value={leadId} onChange={(event) => { setLeadId(event.target.value); if (event.target.value) setContactId(''); }} aria-label="Lead para contexto QA">
                        <option value="">Sin lead seleccionado</option>
                        {leads.map((lead) => <option key={lead.lead_id} value={lead.lead_id}>{lead.contact_name} · {lead.contact_phone ?? 'sin teléfono'} · {lead.contact_email ?? 'sin correo'}</option>)}
                      </select>
                      {selectedLead ? <div className="grid gap-2 rounded-lg bg-muted/30 p-3 text-xs sm:grid-cols-2"><p><strong>Lead:</strong> {selectedLead.contact_name} · {selectedLead.lead_id}</p><p><strong>Teléfono:</strong> {selectedLead.contact_phone ?? '—'}</p><p><strong>Correo:</strong> {selectedLead.contact_email ?? '—'}</p><p><strong>Contact resuelto:</strong> {String(resolvedContact?.id ?? '—')} · {String(resolvedContact?.name ?? '')}</p></div> : null}
                      <p className="text-xs text-muted-foreground">Al seleccionar un lead, el backend deriva su contacto tenant-scoped y rechaza combinaciones incompatibles.</p>
                    </div>
                    <section className="space-y-3 rounded-xl border border-border p-4">
                      <h3 className="text-sm font-semibold">Contexto de negocio</h3>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <label className="space-y-1 text-xs font-medium">Servicio / intención<input className={INPUT} value={service} onChange={(event) => setService(event.target.value)} /></label>
                        <label className="space-y-1 text-xs font-medium">Sede<input className={INPUT} value={location} onChange={(event) => setLocation(event.target.value)} /></label>
                        <label className="space-y-1 text-xs font-medium">Fecha preferida<input className={INPUT} type="date" value={preferredDate} onChange={(event) => setPreferredDate(event.target.value)} /></label>
                        <label className="space-y-1 text-xs font-medium">Hora preferida<input className={INPUT} type="time" value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} /></label>
                        <label className="space-y-1 text-xs font-medium sm:col-span-2">Notas<input className={INPUT} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
                      </div>
                    </section>
                    <section className="space-y-2 rounded-xl border border-border bg-muted/15 p-4">
                      <h3 className="text-sm font-semibold">Contexto que recibirá el agente</h3>
                      {contextPreview ? <pre className="max-h-56 overflow-auto rounded-lg bg-background p-3 text-xs">{JSON.stringify(contextPreview, null, 2)}</pre> : <p className="text-xs text-muted-foreground">{contextPreviewError ?? 'Resolviendo contexto…'}</p>}
                    </section>
                    <section className="space-y-3 rounded-xl border border-border p-4">
                      <h3 className="text-sm font-semibold">Herramientas habilitadas</h3>
                      {enabledTools.length ? enabledTools.map(({ binding, definition }) => <article key={binding.key} className="rounded-lg border border-border bg-muted/15 p-3 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2"><strong>{binding.key}</strong><span className={definition?.available ? 'text-emerald-700 dark:text-emerald-300' : 'text-destructive'}>{definition?.available ? 'Habilitada' : 'Integración o tool no disponible'}</span></div>
                        <p className="mt-1 text-muted-foreground">{definition?.source ?? 'desconocido'} · {definition?.required_integration ?? 'sin integración requerida'}</p>
                        <div className="mt-3 grid gap-2 sm:grid-cols-3"><ToolMetadata title="Argumentos LLM" items={Object.keys(((definition?.input_schema.properties ?? {}) as Record<string, unknown>))} /><ToolMetadata title="Contexto de sesión" items={(definition?.context_requirements ?? []).map((requirement) => `${requirement.path}${requirement.required ? ' · requerido' : ''}`)} /><ToolMetadata title="Configuración fija" items={Object.entries(binding.config ?? {}).map(([key, value]) => `${key}: ${JSON.stringify(sanitizeConfigValue(key, value))}`)} /></div>
                      </article>) : <p className="text-xs text-muted-foreground">No hay tools publicadas habilitadas para este agente.</p>}
                    </section>
                    <section className="space-y-2 rounded-xl border border-border bg-muted/15 p-4 text-xs">
                      <h3 className="text-sm font-semibold">Preparación de la prueba</h3>
                      <p>{published.provider ? '✓ Agente publicado y proveedor configurado' : '✕ Proveedor de voz no configurado'}</p>
                      <p>{published.runtimeEngine === 'livekit' ? '✓ Runtime LiveKit seleccionado' : '✕ Runtime LiveKit no disponible'}</p>
                      <p>{contextPreview && !contextPreviewError ? '✓ SessionContext resuelto' : `✕ SessionContext: ${contextPreviewError ?? 'pendiente de resolución'}`}</p>
                      <p>{toolsReady ? '✓ Tools publicadas e integraciones disponibles' : '✕ Verifica las tools habilitadas, su configuración e integración requerida'}</p>
                      <p className="text-muted-foreground">La conectividad real de LiveKit se confirma al conectar; esta pantalla no hace una llamada de prueba al proveedor.</p>
                    </section>
                    <button type="button" className="text-sm font-semibold text-cyan-700 dark:text-cyan-300" onClick={() => setAdvanced((value) => !value)}>{advanced ? 'Ocultar configuración avanzada' : 'Mostrar configuración avanzada'}</button>
                    {advanced ? (
                      <div className="grid gap-4 rounded-xl border border-border bg-muted/20 p-4 md:grid-cols-2">
                        <label className="space-y-1.5 text-sm font-medium"><span>Contact ID manual</span><input className={INPUT} value={contactId} disabled={Boolean(leadId)} onChange={(event) => setContactId(event.target.value)} /></label>
                        <label className="space-y-1.5 text-sm font-medium md:col-span-2"><span className="flex items-center gap-2"><Braces className="size-4" /> Variables adicionales de SessionContext</span><textarea className={`${INPUT} min-h-28 py-2 font-mono`} value={variablesText} onChange={(event) => setVariablesText(event.target.value)} spellCheck={false} /><span className="text-xs text-muted-foreground">Se inyectan como contexto confiable de la sesión; no son argumentos generados por el LLM.</span></label>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            ) : <QaConsole agentName={agentName} transport={transport} contextMode={contextMode} session={session} transcripts={transcripts} tools={tools} connected={connected} microphoneActive={microphoneActive} stage={stage} />}
            {audioBlocked ? <Button type="button" variant="outline" className="mt-4 w-full" onClick={async () => { await adapter.current?.enableAudio(); setAudioBlocked(false); }}>Activar audio</Button> : null}
            {error ? <p role="alert" className="mt-4 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{error}</p> : null}
          </div>
          <DialogFooter className="border-t border-border px-6 py-4">
            {stage === 'config' ? <Button type="button" onClick={start} disabled={!preflightReady}>Iniciar prueba {transport.toUpperCase()}</Button> : null}
            {stage !== 'config' ? <Button type="button" variant="destructive" onClick={() => { reset(); setOpen(false); }}><PhoneOff className="mr-2 size-4" />Finalizar</Button> : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function QaConsole({ agentName, transport, contextMode, session, transcripts, tools, connected, microphoneActive, stage }: { agentName: string; transport: Transport; contextMode: QaContextMode; session: VoiceQaEventsResponse | null; transcripts: VoiceQaEvent[]; tools: VoiceQaEvent[]; connected: boolean; microphoneActive: boolean; stage: Stage }) {
  const context = session?.context;
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Status icon={Radio} label="Conexión" value={connected ? 'Conectada' : stage === 'preparing' ? 'Preparando' : session?.session.status ?? 'Desconectada'} active={connected} />
        <Status icon={transport === 'webrtc' ? (microphoneActive ? Mic : MicOff) : Phone} label={transport === 'webrtc' ? 'Micrófono' : 'Canal'} value={transport === 'webrtc' ? (microphoneActive ? 'Activo' : 'Inactivo') : 'SIP'} active={microphoneActive || transport === 'sip'} />
        <Status icon={Activity} label="Estado terminal" value={TERMINAL.has(session?.session.status ?? '') ? session?.session.status ?? '—' : 'En curso'} active={false} />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <section className="min-h-64 rounded-xl border border-border bg-muted/15 p-4">
          <h3 className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Conversación</h3>
          <div className="mt-4 space-y-3" aria-live="polite">
            {transcripts.length ? transcripts.map((event) => <div key={event.event_id} className={`max-w-[88%] rounded-xl px-4 py-3 text-sm ${event.payload.speaker === 'assistant' ? 'ml-auto bg-cyan-600 text-white' : 'bg-background shadow-sm ring-1 ring-border'}`}><p className="mb-1 text-[10px] font-bold uppercase opacity-70">{event.payload.speaker === 'assistant' ? agentName : 'Usuario'}</p><p>{String(event.payload.text ?? '')}</p></div>) : <p className="text-sm text-muted-foreground">Esperando transcripción final…</p>}
          </div>
        </section>
        <div className="space-y-5">
          <section className="rounded-xl border border-border p-4"><h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground"><Wrench className="size-4" /> Tools</h3><div className="mt-3 space-y-2">{tools.length ? tools.map((event) => <ToolRow key={event.event_id} event={event} />) : <p className="text-sm text-muted-foreground">Sin ejecuciones todavía.</p>}</div></section>
          <section className="rounded-xl border border-border p-4 text-sm"><h3 className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Contexto resuelto</h3><dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 break-all"><dt className="text-muted-foreground">Context mode</dt><dd>{contextMode === 'conversation' ? 'Conversacional' : 'Precargado'}</dd><dt className="text-muted-foreground">Caller</dt><dd>{context?.caller_phone ?? '—'}</dd><dt className="text-muted-foreground">Contact</dt><dd>{context?.contact_id ?? '—'}</dd><dt className="text-muted-foreground">Lead</dt><dd>{context?.lead_id ?? '—'}</dd><dt className="text-muted-foreground">Session</dt><dd>{session?.session.id ?? '—'}</dd><dt className="text-muted-foreground">Version</dt><dd>{session?.session.agent_version_id ?? '—'}</dd><dt className="text-muted-foreground">Runtime</dt><dd>{session ? `${session.session.provider} · ${session.session.runtime_engine} · ${session.session.pipeline_type}` : '—'}</dd></dl></section>
        </div>
      </div>
    </div>
  );
}

function ToolRow({ event }: { event: VoiceQaEvent }) {
  const failed = event.payload.status === 'error';
  const detail = event.payload.error_code === 'lead_context_required'
    ? 'lead_context_required — la sesión no tiene un lead resuelto'
    : String(event.payload.error_code ?? event.payload.summary ?? '');
  return <div className={`rounded-lg border px-3 py-2 text-sm ${failed ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-muted/25'}`}><p className="font-semibold">{String(event.payload.tool_key ?? 'tool')}</p><p className={failed ? 'text-destructive' : 'text-muted-foreground'}>{String(event.payload.status ?? 'unknown')} · {String(event.payload.duration_ms ?? 0)} ms · {detail}</p></div>;
}

function ToolMetadata({ title, items }: { title: string; items: string[] }) {
  return <div className="rounded-md bg-background p-2"><p className="font-semibold">{title}</p>{items.length ? <ul className="mt-1 space-y-1 text-muted-foreground">{items.map((item) => <li key={item} className="break-all">{item}</li>)}</ul> : <p className="mt-1 text-muted-foreground">—</p>}</div>;
}

function sanitizeConfigValue(key: string, value: unknown): unknown {
  if (/secret|token|password|credential|authorization|api.?key|phone|email/i.test(key)) return '[oculto]';
  if (Array.isArray(value)) return value.map((item) => sanitizeConfigValue('', item));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([childKey, child]) => [childKey, sanitizeConfigValue(childKey, child)]));
  return value;
}

function Status({ icon: Icon, label, value, active }: { icon: typeof Radio; label: string; value: string; active: boolean }) {
  return <div className="flex items-center gap-3 rounded-xl border border-border bg-background p-3"><span className={`flex size-9 items-center justify-center rounded-lg ${active ? 'bg-emerald-500/15 text-emerald-600' : 'bg-muted text-muted-foreground'}`}><Icon className="size-4" aria-hidden="true" /></span><div><p className="text-xs text-muted-foreground">{label}</p><p className="text-sm font-semibold" aria-live="polite">{value}</p></div></div>;
}
