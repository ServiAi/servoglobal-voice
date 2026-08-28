'use client';

import { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle2, Copy, Phone, Plus, Edit2, RotateCw, Router } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FieldHelp } from './FieldHelp';
import type {
  VoiceProviderConfigRequest,
  VoiceProviderConfigResponse,
  VoiceAgentConfigRequest,
  VoiceAgentConfigResponse,
  VoiceOutboundCountry,
} from '@/types/crm';
import {
  configureVoice,
  testVoiceConnection,
  fetchVoiceAgents,
  createVoiceAgent,
  updateVoiceAgent,
  configureAdminTenantVoice,
  testAdminTenantVoice,
  fetchAdminTenantVoiceAgents,
  createAdminTenantVoiceAgent,
  updateAdminTenantVoiceAgent,
} from '@/lib/api/crm';

type Props = {
  accessToken: string;
  initialConfig?: VoiceProviderConfigResponse;
  initialAgents?: VoiceAgentConfigResponse[];
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

const FIELD_CLASS = 'min-h-10 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

const COUNTRY_SELECT_OPTIONS = [['CO', 'Colombia'], ['MX', 'México'], ['AR', 'Argentina'], ['PA', 'Panamá'], ['CL', 'Chile'], ['EC', 'Ecuador'], ['PE', 'Perú'], ['US', 'Estados Unidos']] as const;
const COUNTRY_CHIP_OPTIONS = [['CO', 'Colombia'], ['MX', 'México'], ['AR', 'Argentina'], ['PA', 'Panamá'], ['CL', 'Chile'], ['EC', 'Ecuador'], ['PE', 'Perú'], ['US', 'EE. UU.']] as const;

const PURPOSE_LABELS: Record<string, string> = {
  'Atención al Cliente': 'Atención',
  'Call Centers y Soporte Técnico': 'Soporte',
  'Cobranza y Recuperación de Pagos': 'Cobranza',
  'Ventas y Generación de Leads': 'Ventas',
  'Reclutamiento y Selección': 'Reclutamiento',
  'Reservaciones y Agendamiento': 'Agendamiento',
  'E-commerce y Tiendas Online': 'E-commerce',
};

function getAgentInitials(name: string): string {
  const letters = name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]?.toUpperCase() ?? '');
  return letters.join('') || '—';
}

export function VoiceIntegrationCard({
  accessToken,
  initialConfig,
  initialAgents = [],
  mode = 'tenant',
  tenantId,
}: Props) {
  const [config, setConfig] = useState<VoiceProviderConfigResponse | undefined>(initialConfig);
  const [agents, setAgents] = useState<VoiceAgentConfigResponse[]>(initialAgents);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [testing, setTesting] = useState(false);

  // Agent form state
  const [editingAgent, setEditingAgent] = useState<VoiceAgentConfigResponse | null>(null);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [savingAgent, setSavingAgent] = useState(false);

  const [agentForm, setAgentForm] = useState<VoiceAgentConfigRequest>({
    provider_agent_id: '',
    display_name: '',
    description: '',
    purpose: 'Atención al Cliente',
    default_language: 'es',
    default_timezone: 'America/Bogota',
    default_voice: 'standard-female',
    status: 'active',
  });

  const [configForm, setConfigForm] = useState<VoiceProviderConfigRequest>({
    provider: 'ultravox',
    display_name: config?.display_name ?? 'Ultravox Voice Service',
    base_url: config?.base_url ?? 'https://api.ultravox.ai',
    default_voice_agent_id: config?.default_voice_agent_id ?? '',
    default_from_number: config?.default_from_number ?? '',
    default_language: config?.default_language ?? 'es',
    default_timezone: config?.default_timezone ?? 'America/Bogota',
    status: config?.status ?? 'active',
    sip_route: {
      status: config?.sip_route?.status ?? 'inactive',
      pbx_host: config?.sip_route?.pbx_host ?? '',
      pbx_port: config?.sip_route?.pbx_port ?? 5060,
      caller_id: config?.sip_route?.caller_id ?? '',
      default_country: config?.sip_route?.default_country ?? 'CO',
      allowed_countries: config?.sip_route?.allowed_countries ?? ['CO'],
      max_concurrent_calls: config?.sip_route?.max_concurrent_calls ?? 1,
    },
  });

  const isActive = config?.status === 'active';

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // Load agents on mount if not provided or empty
  useEffect(() => {
    if (initialAgents.length > 0) return;

    async function load() {
      setLoadingAgents(true);
      const res =
        mode === 'admin' && tenantId
          ? await fetchAdminTenantVoiceAgents(accessToken, tenantId)
          : await fetchVoiceAgents(accessToken);
      setLoadingAgents(false);
      if (res.ok) {
        setAgents(res.data);
      }
    }
    load();
  }, [accessToken, initialAgents.length, mode, tenantId]);

  const updateConfigField = (key: keyof VoiceProviderConfigRequest, value: string) => {
    setConfigForm((curr) => ({ ...curr, [key]: value }));
  };

  const updateSipRouteField = <K extends keyof NonNullable<VoiceProviderConfigRequest['sip_route']>>(
    key: K,
    value: NonNullable<VoiceProviderConfigRequest['sip_route']>[K],
  ) => {
    setConfigForm((current) => ({
      ...current,
      sip_route: { ...current.sip_route!, [key]: value },
    }));
  };

  const handleSaveConfig = async () => {
    const sipRoute = configForm.sip_route;
    const sipRouteHasInput = Boolean(
      sipRoute?.pbx_host?.trim() || sipRoute?.caller_id?.trim() || sipRoute?.sip_password?.trim(),
    );
    const sipRouteComplete = Boolean(sipRoute?.pbx_host?.trim() && sipRoute?.caller_id?.trim());

    if (sipRouteHasInput && !sipRouteComplete) {
      notify('error', 'Completa Host PBX y Caller ID para guardar la ruta SIP, o deja esos campos vacíos.');
      return;
    }

    setSavingConfig(true);
    const payload = {
      ...configForm,
      api_key: configForm.api_key?.trim() || null,
      webhook_secret: configForm.webhook_secret?.trim() || null,
      sip_route: sipRouteComplete ? {
        ...sipRoute!,
        sip_password: sipRoute!.sip_password?.trim() || null,
      } : null,
    };
    const result =
      mode === 'admin' && tenantId
        ? await configureAdminTenantVoice(accessToken, tenantId, payload)
        : await configureVoice(accessToken, payload);
    setSavingConfig(false);

    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    setConfig(result.data);
    setConfigForm((current) => ({
      ...current,
      sip_route: current.sip_route
        ? { ...current.sip_route, sip_password: undefined }
        : current.sip_route,
    }));
    notify('success', 'Configuración de proveedor de voz guardada exitosamente.');
  };

  const handleCopySipUsername = async () => {
    const username = config?.sip_route?.sip_username;
    if (!username) return;
    try {
      await navigator.clipboard.writeText(username);
      notify('success', 'Usuario SIP copiado.');
    } catch {
      notify('error', 'No se pudo copiar el usuario SIP.');
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    const result =
      mode === 'admin' && tenantId
        ? await testAdminTenantVoice(accessToken, tenantId)
        : await testVoiceConnection(accessToken);
    setTesting(false);

    if (!result.ok) {
      notify('error', `Error en la conexión: ${result.detail}`);
      return;
    }
    notify('success', 'La prueba de conexión fue exitosa. Servidor activo.');
  };

  const handleAddAgentClick = () => {
    setEditingAgent(null);
    setAgentForm({
      provider_agent_id: '',
      display_name: '',
      description: '',
      purpose: 'Atención al Cliente',
      default_language: 'es',
      default_timezone: 'America/Bogota',
      default_voice: 'standard-female',
      status: 'active',
    });
    setShowAgentForm(true);
  };

  const handleEditAgentClick = (agent: VoiceAgentConfigResponse) => {
    setEditingAgent(agent);
    setAgentForm({
      provider_agent_id: agent.provider_agent_id,
      display_name: agent.display_name,
      description: agent.description,
      purpose: agent.purpose,
      default_language: agent.default_language,
      default_timezone: agent.default_timezone,
      default_voice: agent.default_voice,
      status: agent.status,
    });
    setShowAgentForm(true);
  };

  const handleSaveAgent = async () => {
    if (!agentForm.provider_agent_id.trim()) {
      notify('error', 'El Agent ID del proveedor es obligatorio.');
      return;
    }
    if (!agentForm.display_name.trim()) {
      notify('error', 'El nombre para mostrar es obligatorio.');
      return;
    }

    setSavingAgent(true);
    const payload = {
      ...agentForm,
      provider_config_id: config?.id || null,
      provider: 'ultravox',
    };

    const result = editingAgent
      ? mode === 'admin' && tenantId
        ? await updateAdminTenantVoiceAgent(accessToken, tenantId, editingAgent.id, payload)
        : await updateVoiceAgent(accessToken, editingAgent.id, payload)
      : mode === 'admin' && tenantId
      ? await createAdminTenantVoiceAgent(accessToken, tenantId, payload)
      : await createVoiceAgent(accessToken, payload);

    setSavingAgent(false);

    if (!result.ok) {
      notify('error', result.detail);
      return;
    }

    // Refresh agent list
    const listRes =
      mode === 'admin' && tenantId
        ? await fetchAdminTenantVoiceAgents(accessToken, tenantId)
        : await fetchVoiceAgents(accessToken);
    if (listRes.ok) {
      setAgents(listRes.data);
    }

    setShowAgentForm(false);
    setEditingAgent(null);
    notify('success', `Agente de voz ${editingAgent ? 'actualizado' : 'creado'} exitosamente.`);
  };

  const isSipActive = configForm.sip_route?.status === 'active';
  const sipProvisionStatus = config?.sip_route?.provision_status ?? 'disabled';
  const sipProvisionLabel = {
    active: 'Aplicada en Asterisk',
    pending: 'Pendiente de aplicar',
    failed: 'Error al aplicar',
    disabled: 'No aprovisionada',
  }[sipProvisionStatus];
  const sipProvisionTone = {
    active: 'text-emerald-600 dark:text-emerald-400',
    pending: 'text-amber-600 dark:text-amber-400',
    failed: 'text-red-600 dark:text-red-400',
    disabled: 'text-muted-foreground',
  }[sipProvisionStatus];
  const activeAgentCount = agents.filter((agent) => agent.status === 'active').length;

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="voice-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500">
            <Phone className="h-5 w-5" />
          </span>
          <div>
            <h2 id="voice-integration-title" className="text-lg font-semibold text-foreground">Agentes de Voz AI</h2>
            <p className="text-sm text-muted-foreground">
              Configuración de telefonía y agentes virtuales (Ultravox / PBX)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-semibold ${
              isActive ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
            }`}
          >
            {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            {isActive ? 'Activa' : config?.status ?? 'Sin configurar'}
          </span>
        </div>
      </div>

      <div className="grid gap-0 lg:grid-cols-[420px_1fr]">
        {/* Left Side: Provider Credentials Config */}
        <div className="space-y-5 border-b border-border p-5 lg:border-b-0 lg:border-r">
          {/* Step 1: credentials */}
          <div>
            <div className="mb-0.5 flex items-center gap-2">
              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground">1</span>
              <h3 className="text-[13px] font-semibold text-foreground">Credenciales del proveedor</h3>
            </div>
            <p className="mb-3 pl-7 text-xs leading-5 text-muted-foreground">Se configuran una sola vez para conectar Ultravox.</p>
            <div className="space-y-3 pl-7">
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Nombre descriptivo <FieldHelp label="Nombre descriptivo de voz" required={false}>Es un nombre interno para reconocer esta configuración; no se obtiene del proveedor.</FieldHelp></span>
                <input
                  type="text"
                  className={FIELD_CLASS}
                  value={configForm.display_name ?? ''}
                  onChange={(e) => updateConfigField('display_name', e.target.value)}
                />
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">API Key <FieldHelp label="Ultravox API Key" required={!config?.has_secret}>Créala en el panel de Ultravox → Settings → API Keys. Solo es obligatoria la primera vez.</FieldHelp></span>
                  <input
                    type="password"
                    placeholder={config?.has_secret ? '••••••••••••••••••••' : 'uvx_api_...'}
                    className={FIELD_CLASS}
                    onChange={(e) => updateConfigField('api_key', e.target.value)}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Webhook Secret <FieldHelp label="Webhook Secret" required={false}>Créalo como una cadena secreta y configura el mismo valor en el webhook del proveedor.</FieldHelp></span>
                  <input
                    type="password"
                    placeholder={config?.has_webhook_secret ? '••••••••••••••••••••' : 'Secreto opcional'}
                    className={FIELD_CLASS}
                    onChange={(e) => updateConfigField('webhook_secret', e.target.value)}
                  />
                </label>
              </div>

              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Base URL Proveedor <FieldHelp label="Base URL Proveedor" required>Usa la URL base oficial del proveedor; para Ultravox es https://api.ultravox.ai.</FieldHelp></span>
                <input
                  type="text"
                  className={FIELD_CLASS}
                  value={configForm.base_url ?? ''}
                  onChange={(e) => updateConfigField('base_url', e.target.value)}
                />
              </label>
            </div>
          </div>

          {/* Step 2: SIP route — elevated */}
          <div className="rounded-lg border border-border bg-muted/30">
            <div className="flex items-center justify-between gap-2 px-4 pt-3.5">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground">2</span>
                <Router className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                <h3 className="text-[13px] font-semibold text-foreground">Ruta SIP saliente por tenant</h3>
              </div>
              <span className={`inline-flex shrink-0 items-center gap-1.5 text-[11px] font-semibold ${isSipActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${isSipActive ? 'bg-emerald-500' : 'bg-muted-foreground/50'}`} aria-hidden="true" />
                {isSipActive ? 'Activa' : 'Inactiva'}
              </span>
            </div>
            <p className="px-4 pb-3.5 pl-11 pt-1.5 text-xs leading-5 text-muted-foreground">
              Credencial del endpoint de este tenant en Asterisk. IDT Express permanece como troncal compartida.
            </p>
            <div className="space-y-3 px-4 pb-4 pl-11">
              {config?.sip_route && (
                <div className={`rounded-md border border-border bg-background px-3 py-2 text-xs ${sipProvisionTone}`} role="status">
                  <span className="font-semibold">{sipProvisionLabel}</span>
                  <span className="ml-2 text-muted-foreground">
                    Revisión {config.sip_route.applied_revision}/{config.sip_route.desired_revision}
                  </span>
                  {sipProvisionStatus === 'pending' && (
                    <p className="mt-1 text-muted-foreground">El agente del PBX aplicará el cambio automáticamente. Las llamadas salientes permanecen bloqueadas hasta su confirmación.</p>
                  )}
                  {sipProvisionStatus === 'failed' && (
                    <p className="mt-1">No se pudo aplicar la configuración ({config.sip_route.provision_error_code ?? 'apply_failed'}). Revisa el servicio aprovisionador en Asterisk.</p>
                  )}
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-[1fr_96px]">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Host PBX <FieldHelp label="Host PBX" required>Dominio o IP pública de Asterisk, sin protocolo ni puerto.</FieldHelp></span>
                  <input className={FIELD_CLASS} value={configForm.sip_route?.pbx_host ?? ''} onChange={(event) => updateSipRouteField('pbx_host', event.target.value)} placeholder="pbx.example.com" />
                </label>
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span>Puerto</span>
                  <input type="number" min={1} max={65535} className={FIELD_CLASS} value={configForm.sip_route?.pbx_port ?? 5060} onChange={(event) => updateSipRouteField('pbx_port', Number(event.target.value))} />
                </label>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Usuario SIP <FieldHelp label="Usuario SIP" required={false}>El sistema lo genera con el identificador estable de la ruta para que Asterisk reconozca el endpoint del tenant.</FieldHelp></span>
                  <div className="flex min-w-0 gap-2">
                    <input
                      className={`${FIELD_CLASS} min-w-0 font-mono text-xs`}
                      value={config?.sip_route?.sip_username ?? ''}
                      placeholder="Se genera al guardar"
                      readOnly
                      aria-label="Usuario SIP generado automáticamente"
                    />
                    <button
                      type="button"
                      className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={handleCopySipUsername}
                      disabled={!config?.sip_route?.sip_username}
                      aria-label="Copiar usuario SIP"
                      title="Copiar usuario SIP"
                    >
                      <Copy className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </div>
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Contraseña SIP <FieldHelp label="Contraseña SIP" required={!config?.sip_route?.has_sip_password}>Se cifra en el backend y nunca vuelve a mostrarse.</FieldHelp></span>
                  <input type="password" className={FIELD_CLASS} placeholder={config?.sip_route?.has_sip_password ? '••••••••••••••••' : 'Mínimo 8 caracteres'} onChange={(event) => updateSipRouteField('sip_password', event.target.value)} autoComplete="new-password" />
                </label>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Caller ID autorizado <FieldHelp label="Caller ID autorizado" required>Número previamente autorizado por IDT Express, en formato internacional.</FieldHelp></span>
                  <input type="tel" className={FIELD_CLASS} value={configForm.sip_route?.caller_id ?? ''} onChange={(event) => updateSipRouteField('caller_id', event.target.value)} placeholder="+57..." />
                </label>
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span>País predeterminado</span>
                  <select className={FIELD_CLASS} value={configForm.sip_route?.default_country ?? 'CO'} onChange={(event) => updateSipRouteField('default_country', event.target.value as VoiceOutboundCountry)}>
                    {COUNTRY_SELECT_OPTIONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                  </select>
                </label>
              </div>
              <div>
                <span className="text-xs font-medium text-muted-foreground">Países habilitados</span>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {COUNTRY_CHIP_OPTIONS.map(([code, label]) => {
                    const enabled = configForm.sip_route?.allowed_countries.includes(code) ?? false;
                    return (
                      <button
                        key={code}
                        type="button"
                        aria-pressed={enabled}
                        onClick={() => updateSipRouteField(
                          'allowed_countries',
                          enabled
                            ? (configForm.sip_route?.allowed_countries ?? []).filter((item) => item !== code)
                            : [...(configForm.sip_route?.allowed_countries ?? []), code],
                        )}
                        className={`inline-flex h-[30px] items-center rounded-full border px-3 text-xs font-medium transition ${
                          enabled
                            ? 'border-indigo-500/50 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
                            : 'border-border bg-background text-foreground hover:bg-accent'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span>Máx. llamadas simultáneas</span>
                  <input type="number" min={1} max={100} className={FIELD_CLASS} value={configForm.sip_route?.max_concurrent_calls ?? 1} onChange={(event) => updateSipRouteField('max_concurrent_calls', Number(event.target.value))} />
                </label>
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span>Estado de ruta</span>
                  <select className={FIELD_CLASS} value={configForm.sip_route?.status ?? 'inactive'} onChange={(event) => updateSipRouteField('status', event.target.value as 'active' | 'inactive')}>
                    <option value="inactive">Inactiva</option>
                    <option value="active">Activa</option>
                  </select>
                </label>
              </div>
            </div>
          </div>

          {/* Step 3: defaults */}
          <div>
            <div className="mb-3.5 flex items-center gap-2">
              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground">3</span>
              <h3 className="text-[13px] font-semibold text-foreground">Comportamiento por defecto</h3>
            </div>
            <div className="space-y-3 pl-7">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Default Agent ID <FieldHelp label="Default Agent ID" required={false}>Copia el ID del agente predeterminado desde el panel de Ultravox. Puede quedar vacío si se selecciona por otra regla.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="ID de agente por defecto"
                    className={FIELD_CLASS}
                    value={configForm.default_voice_agent_id ?? ''}
                    onChange={(e) => updateConfigField('default_voice_agent_id', e.target.value)}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Outgoing Number (SIP) <FieldHelp label="Outgoing Number SIP" required={false}>Es el número saliente asignado por tu operador SIP/PBX, en formato internacional.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="+57..."
                    className={FIELD_CLASS}
                    value={configForm.default_from_number ?? ''}
                    onChange={(e) => updateConfigField('default_from_number', e.target.value)}
                  />
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Idioma <FieldHelp label="Idioma predeterminado de voz" required>Selecciona el idioma principal que usará la integración.</FieldHelp></span>
                  <select
                    className={FIELD_CLASS}
                    value={configForm.default_language}
                    onChange={(e) => updateConfigField('default_language', e.target.value)}
                  >
                    <option value="es">Español</option>
                    <option value="en">Inglés</option>
                  </select>
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Zona horaria <FieldHelp label="Zona horaria de voz" required>Usa una zona IANA como America/Bogota para interpretar horarios correctamente.</FieldHelp></span>
                  <input
                    type="text"
                    className={FIELD_CLASS}
                    value={configForm.default_timezone}
                    onChange={(e) => updateConfigField('default_timezone', e.target.value)}
                  />
                </label>
              </div>

              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Estado de Integración <FieldHelp label="Estado de integración de voz" required>Activa la integración solo cuando las credenciales y la conexión estén listas.</FieldHelp></span>
                <select
                  className={FIELD_CLASS}
                  value={configForm.status}
                  onChange={(e) => updateConfigField('status', e.target.value)}
                >
                  <option value="active">Activo</option>
                  <option value="inactive">Inactivo</option>
                </select>
              </label>
            </div>
          </div>

          <div className="flex flex-col gap-2 border-t border-border pt-4 sm:flex-row">
            <Button
              type="button"
              onClick={handleSaveConfig}
              disabled={savingConfig}
              className="w-full text-xs"
            >
              {savingConfig ? 'Guardando...' : 'Guardar Config'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={testing || !config?.has_secret}
              className="w-full text-xs"
            >
              {testing ? <RotateCw className="h-3 w-3 animate-spin mr-1" /> : null}
              Probar
            </Button>
          </div>
        </div>

        {/* Right Side: Agents Management list */}
        <div className="min-w-0 space-y-4 p-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-[13px] font-semibold text-foreground">Agentes configurados</h3>
              {agents.length > 0 && (
                <p className="mt-0.5 text-xs text-muted-foreground">{agents.length} {agents.length === 1 ? 'agente' : 'agentes'} · {activeAgentCount} activos</p>
              )}
            </div>
            {!showAgentForm && (
              <Button
                type="button"
                size="sm"
                onClick={handleAddAgentClick}
                className="h-8 gap-1 text-xs"
              >
                <Plus className="h-3.5 w-3.5" /> Agregar Agente
              </Button>
            )}
          </div>

          {showAgentForm ? (
            <div className="space-y-4 rounded-lg border border-border bg-muted/30 p-4">
              <h4 className="text-sm font-semibold text-foreground">
                {editingAgent ? 'Editar Agente de Voz' : 'Nuevo Agente de Voz'}
              </h4>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Provider Agent ID * <FieldHelp label="Provider Agent ID" required>Copia el ID único del agente desde el panel del proveedor de voz.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="wk-xxxx..."
                    className={FIELD_CLASS}
                    value={agentForm.provider_agent_id}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, provider_agent_id: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Nombre descriptivo * <FieldHelp label="Nombre descriptivo del agente" required>Escribe un nombre interno que permita identificar el agente dentro del CRM.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Ej. Agente Comercial"
                    className={FIELD_CLASS}
                    value={agentForm.display_name}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, display_name: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-2">
                  <span className="flex items-center gap-1">Descripción <FieldHelp label="Descripción del agente" required={false}>Resume el objetivo del agente para que el equipo pueda reconocerlo.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Objetivo principal del agente virtual"
                    className={FIELD_CLASS}
                    value={agentForm.description ?? ''}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, description: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Caso de Uso / Propósito <FieldHelp label="Caso de uso del agente" required>Selecciona la función comercial principal que cumplirá el agente.</FieldHelp></span>
                  <select
                    className={FIELD_CLASS}
                    value={agentForm.purpose}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, purpose: e.target.value }))}
                  >
                    <option value="Atención al Cliente">Atención al Cliente</option>
                    <option value="Call Centers y Soporte Técnico">Soporte Técnico</option>
                    <option value="Cobranza y Recuperación de Pagos">Cobranza</option>
                    <option value="Ventas y Generación de Leads">Ventas</option>
                    <option value="Reclutamiento y Selección">Reclutamiento</option>
                    <option value="Reservaciones y Agendamiento">Agendamiento</option>
                    <option value="E-commerce y Tiendas Online">E-commerce</option>
                  </select>
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Voz por defecto <FieldHelp label="Voz por defecto" required={false}>Copia el identificador de voz admitido por el proveedor; si se omite se usa su voz predeterminada.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Ej. standard-female"
                    className={FIELD_CLASS}
                    value={agentForm.default_voice ?? ''}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, default_voice: e.target.value }))}
                  />
                </label>

                <div className="grid gap-3 sm:grid-cols-2 sm:col-span-2">
                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    <span className="flex items-center gap-1">Idioma <FieldHelp label="Idioma del agente" required>Selecciona el idioma principal del agente.</FieldHelp></span>
                    <select
                      className={FIELD_CLASS}
                      value={agentForm.default_language}
                      onChange={(e) => setAgentForm((curr) => ({ ...curr, default_language: e.target.value }))}
                    >
                      <option value="es">Español</option>
                      <option value="en">Inglés</option>
                    </select>
                  </label>

                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    <span className="flex items-center gap-1">Estado agente <FieldHelp label="Estado del agente" required>Selecciona Activo cuando el agente esté listo para usarse.</FieldHelp></span>
                    <select
                      className={FIELD_CLASS}
                      value={agentForm.status}
                      onChange={(e) => setAgentForm((curr) => ({ ...curr, status: e.target.value }))}
                    >
                      <option value="active">Activo</option>
                      <option value="inactive">Inactivo</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border mt-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowAgentForm(false)}
                  className="text-xs"
                >
                  Cancelar
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={handleSaveAgent}
                  disabled={savingAgent}
                  className="text-xs"
                >
                  {savingAgent ? 'Guardando...' : 'Guardar Agente'}
                </Button>
              </div>
            </div>
          ) : (
            <div>
              {loadingAgents ? (
                <div className="text-center py-6 text-sm text-muted-foreground">
                  Cargando lista de agentes de voz...
                </div>
              ) : agents.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border bg-muted/20 py-8 text-center">
                  <p className="text-sm text-muted-foreground">No hay agentes de voz registrados para este tenant.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <div role="table" aria-label="Agentes de voz configurados" className="min-w-[640px]">
                    <div role="rowgroup">
                      <div role="row" className="grid grid-cols-[34px_1fr_auto_auto_84px_32px] items-center gap-3 px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                        <span role="columnheader" className="sr-only">Avatar</span>
                        <span role="columnheader">Agente</span>
                        <span role="columnheader">Propósito</span>
                        <span role="columnheader">Voz</span>
                        <span role="columnheader">Estado</span>
                        <span role="columnheader" className="sr-only">Acciones</span>
                      </div>
                    </div>
                    <div role="rowgroup" className="space-y-0.5">
                      {agents.map((agent) => {
                        const active = agent.status === 'active';
                        return (
                          <div key={agent.id} role="row" className="grid grid-cols-[34px_1fr_auto_auto_84px_32px] items-center gap-3 rounded-md p-2.5 hover:bg-accent">
                            <span role="cell" aria-hidden="true" className="flex h-[30px] w-[30px] items-center justify-center rounded-md bg-muted text-[11px] font-semibold text-foreground">
                              {getAgentInitials(agent.display_name)}
                            </span>
                            <span role="cell" className="min-w-0">
                              <div className="truncate text-[13px] font-medium text-foreground">{agent.display_name}</div>
                              {agent.description && (
                                <div className="truncate text-[11.5px] text-muted-foreground">{agent.description}</div>
                              )}
                            </span>
                            <span role="cell" className="inline-flex h-[22px] items-center whitespace-nowrap rounded-full border border-border px-2.5 text-[11px] font-medium text-muted-foreground">
                              {PURPOSE_LABELS[agent.purpose] ?? agent.purpose}
                            </span>
                            <span role="cell" className="whitespace-nowrap font-mono text-[11px] text-muted-foreground">
                              {agent.default_voice || 'default'}
                            </span>
                            <span role="cell" className={`inline-flex items-center gap-1.5 text-[11px] font-semibold ${active ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-emerald-500' : 'bg-muted-foreground/50'}`} aria-hidden="true" />
                              {active ? 'Activo' : 'Inactivo'}
                            </span>
                            <span role="cell">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-[30px] w-[30px]"
                                onClick={() => handleEditAgentClick(agent)}
                                aria-label={`Editar ${agent.display_name}`}
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </Button>
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {config?.last_error_message && (
        <div role="alert" className="mx-5 mb-5 rounded-md border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          <strong>Último error de conexión:</strong> {config.last_error_message}
        </div>
      )}

      {message && (
        <div
          role="status"
          className={`mx-5 mb-5 rounded-md border p-3 text-sm ${
            message.type === 'success'
              ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
              : 'border-destructive/20 bg-destructive/10 text-destructive'
          }`}
        >
          {message.text}
        </div>
      )}
    </section>
  );
}
